"""Run persisted requests through existing station commands in private staging."""
import fcntl
import json
import os
import signal
import subprocess
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone

from content_management.models import LibraryVersion, OasisIndexJob
from content_management.oasis_indexing import heartbeat, job_root, maintenance_request, preflight, run_probe, staging_base, station_environment
from content_management.utils import LibraryBuildUtil


def run_command(command, config, job, label):
    log = job_root(job) / (label + '.log')
    environment = station_environment(config)
    timeout = min(3600, max(15, int(os.environ.get('OASIS_INDEXING_JOB_TIMEOUT', '1800'))))
    with log.open('wb') as output:
        process = subprocess.Popen(command, cwd=config['root'], env=environment, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        began = time.monotonic()
        try:
            while process.poll() is None:
                heartbeat()
                if time.monotonic() - began > timeout:
                    raise ValueError('Existing station command exceeded the private job time limit.')
                if log.stat().st_size > 4 * 1024 * 1024:
                    raise ValueError('Existing station command exceeded the diagnostic output limit.')
                time.sleep(0.25)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            raise
    with log.open('rb') as stream:
        stream.seek(max(0, log.stat().st_size - 16000))
        diagnostics = stream.read().decode('utf-8', errors='replace')
    if process.returncode:
        raise ValueError(label + ' failed (exit %s): ' % process.returncode + diagnostics)
    return diagnostics


def execute_job(job):
    diagnostics = []
    try:
        version = LibraryVersion.objects.get(pk=job.catalogue_version)
        config, probe, records = preflight(version, job.profile)
        if records != job.documents or probe['manifest'] != job.manifest:
            raise ValueError('Catalogue originals or reviewed manifest changed after queueing. Submit a new reviewed job.')
        root = job_root(job)
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        manifest = root / 'reviewed-manifest.json'
        manifest.write_text(json.dumps(job.manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
        bundles = root / 'bundles'
        with override_settings(BUILDS_ROOT=str(bundles)):
            result = LibraryBuildUtil(version.id).build_library()
        if result.get('result') != 'success':
            raise ValueError('Private export failed: ' + result.get('error', 'unknown export error'))
        bundle = bundles / version.version_number
        draft = root / 'draft'
        draft.mkdir(mode=0o700)
        diagnostics.append(run_command([str(config['python']), '-B', '-m', 'scripts.import_pdf_library', '--bundle', str(bundle), '--manifest', str(manifest), '--destination', str(draft)], config, job, 'import'))
        if job.profile == 'hybrid':
            diagnostics.append(run_command([str(config['python']), '-B', '-m', 'scripts.index_pdf_vectors', '--root', str(draft), '--model', config['model'], '--base-url', config['base_url'], '--keep-alive', '0'], config, job, 'vectors'))
        receipt = run_probe(config, root=draft)['receipt']
        if {(item['document_id'], item['filename'], item['sha256']) for item in receipt['documents']} != {(doc['document_id'], doc['filename'], doc['sha256']) for doc in job.documents}:
            raise ValueError('Validated draft does not match the exact queued originals.')
        if not receipt['lexical_valid'] or job.profile == 'hybrid' and not receipt['vector_valid']:
            raise ValueError('Existing station validators did not confirm complete requested indexes.')
        job.state, job.receipt = 'succeeded', receipt
        job.diagnostics = 'Validated private draft only; no publication or active library changes.\n' + '\n'.join(diagnostics)[-14000:]
    except Exception as exc:
        job.state = 'failed'
        job.diagnostics = str(exc)[-16000:]
    job.finished_on = timezone.now()
    job.save(update_fields=['state', 'receipt', 'diagnostics', 'finished_on'])


class Command(BaseCommand):
    help = 'Process the durable private draft indexing queue; never modifies a station active root.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process one queued request, then stop.')

    def handle(self, *args, **options):
        base = staging_base()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (base / 'worker.lock').open('a+b') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError('A private indexing worker is already running.')
            OasisIndexJob.objects.filter(state='running').update(state='failed', finished_on=timezone.now(), diagnostics='Worker stopped before draft validation completed. Submit a new job.')
            try:
                while True:
                    maintenance_nonce = maintenance_request()
                    if maintenance_nonce is not None:
                        heartbeat(maintenance=True, maintenance_nonce=maintenance_nonce)
                        if options['once']:
                            break
                        time.sleep(1)
                        continue
                    heartbeat()
                    with transaction.atomic():
                        job = OasisIndexJob.objects.select_for_update().filter(state='queued').order_by('created_on').first()
                        if job:
                            job.state, job.started_on = 'running', timezone.now()
                            job.save(update_fields=['state', 'started_on'])
                    if job:
                        execute_job(job)
                        self.stdout.write('%s %s' % (job.id, job.state))
                    if options['once']:
                        break
                    time.sleep(1)
            finally:
                heartbeat(active=False)
