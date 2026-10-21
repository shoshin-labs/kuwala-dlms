"""Staff/CSRF protected proxy to the fixed local pack installation socket."""
import json
import os
import pwd
import socket
import stat
import struct

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError

from content_management.oasis_documents import PrivateCuratorAccess
from content_management.standardize_format import build_response

SOCKET = '/run/oasis-pack-installer/control.sock'
MAX_RESPONSE = 256 * 1024


def control(command):
    encoded = json.dumps(command, ensure_ascii=False, allow_nan=False).encode() + b'\n'
    if len(encoded) > 16384:
        raise ValueError('Pack request exceeds its size limit.')
    try:
        info = os.lstat(SOCKET)
        parent = os.lstat(os.path.dirname(SOCKET))
        expected = pwd.getpwnam('kuwala').pw_uid
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != expected or stat.S_IMODE(info.st_mode) != 0o660
                or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) != 0o755):
            raise ValueError('The pack installation socket has an unexpected identity.')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(25)
            connection.connect(SOCKET)
            pid, uid, gid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            # With socket activation the peer credentials belong to PID 1's
            # root-created listener. Only root can replace its parent entry.
            if uid not in {0, expected}:
                raise ValueError('The pack installer has an unexpected service identity.')
            connection.sendall(encoded)
            result = bytearray()
            while b'\n' not in result:
                chunk = connection.recv(min(16384, MAX_RESPONSE + 1 - len(result)))
                if not chunk:
                    raise ValueError('The pack installer stopped before returning a result.')
                result.extend(chunk)
                if len(result) > MAX_RESPONSE:
                    raise ValueError('Pack result exceeds its bounded page size.')
        value = json.loads(result)
        if type(value) is not dict or value.get('success') is not True:
            raise ValueError('The pack operation could not complete. Refresh packs and check the current installation status.')
        return value['data']
    except (OSError, KeyError, ValueError, TypeError):
        raise ValueError('Pack installation is unavailable. Existing books remain available; check the local installer service.') from None


@api_view(['GET', 'POST'])
@permission_classes([PrivateCuratorAccess])
def packs(request):
    if request.method == 'GET':
        if set(request.query_params) - {'page', 'pack_id'}:
            raise ValidationError('Choose a pack or a bounded page.')
        try:
            page = int(request.query_params.get('page', '1'))
            if 'pack_id' in request.query_params:
                command = {'action': 'details', 'pack_id': request.query_params['pack_id'], 'page': page}
            else:
                if not 1 <= page <= 8:
                    raise ValueError('Choose a page from 1 to 8.')
                command = {'action': 'catalogue', 'page': page}
        except ValueError as error:
            raise ValidationError(str(error))
    else:
        command = request.data
        allowed = ({'action'}, {'action', 'pack_ids', 'publication_sha256', 'request_id'},
                   {'action', 'expected_current', 'request_id'})
        if type(command) is not dict or set(command) not in allowed or command.get('action') not in {'refresh', 'install', 'rollback'}:
            raise ValidationError('Choose refresh, install or rollback with its exact reviewed parameters.')
    try:
        return build_response(control(command))
    except ValueError as error:
        if request.method == 'GET':
            return build_response({'configured': False, 'blocked_reason': str(error), 'packs': [], 'job': None})
        return build_response(status=409, success=False, error=str(error))
