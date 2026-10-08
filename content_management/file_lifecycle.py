"""Clean up authoring originals only after database changes commit."""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def delete_file_after_commit(storage, name):
    if not name:
        return

    def cleanup():
        from content_management.models import Content
        try:
            # Defensive for legacy records that may share an original path.
            if Content.objects.filter(content_file=name).exists():
                return
            storage.delete(name)
        except Exception:
            # The record is already committed. Report cleanup failure without
            # falsely reporting that the successful document change rolled back.
            logger.exception('Unable to remove unused authoring original %s', name)

    transaction.on_commit(cleanup)
