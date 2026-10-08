"""Explicit private-testing review of the original synthetic seed fixtures only."""
import json
import hashlib
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from content_management.models import LibraryVersion
from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.oasis_indexing import catalogue_documents, original_record, staging_base


class Command(BaseCommand):
    help = 'Authorise labelled original synthetic seed PDFs for private development indexing only.'

    def handle(self, *args, **options):
        if not getattr(settings, 'OASIS_SYNTHETIC_FIXTURES', False):
            raise CommandError('Run the explicit synthetic seed first. This command cannot review real uploads.')
        version = LibraryVersion.objects.get(version_number='oasis-synthetic-preview-v1')
        expected = {
            'Sample crop record (synthetic)': 'oasis-synthetic-farming.pdf',
            'Sample water record (synthetic)': 'oasis-synthetic-water.pdf',
            'Sample learning record (synthetic)': 'oasis-synthetic-learning.pdf',
        }
        documents = []
        for document in catalogue_documents(version):
            if document.title not in expected or document.file_name != expected[document.title] or document.copyright_notes != 'Original synthetic fixture by Kuwala contributors.':
                raise CommandError('This catalogue contains a non-seed document; review its actual rights separately.')
            record = original_record(document)
            if record['sha256'] != hashlib.sha256(sample_pdf(document.title)).hexdigest():
                raise CommandError('A synthetic seed original was replaced. This helper cannot authorise replacement bytes.')
            documents.append({'id': 'synthetic-document-%s' % document.id, 'dlms_id': document.id,
                              'filename': record['filename'], 'sha256': record['sha256'], 'title': document.display_title or document.title,
                              'publisher': 'Kuwala synthetic fixture development', 'authors': 'Kuwala contributors',
                              'source_url': 'https://example.invalid/oasis-library/synthetic-fixtures',
                              'licence': 'CC0-1.0 (original synthetic fixture only)',
                              'licence_url': 'https://creativecommons.org/publicdomain/zero/1.0/',
                              'rights_notes': document.copyright_notes + ' Private development fixture; no technical advice or expert approval.',
                              'approved': True, 'reviewed_on': date.today().isoformat(),
                              'reviewer': 'Explicit synthetic seed testing command: private development scope only, not expert field review.',
                              'testing_only': True, 'rights_review_pending': True})
        if len(documents) != len(expected) or {item['title'] for item in documents} != set(expected):
            raise CommandError('The complete three original synthetic seed PDFs are required.')
        reviewed = {item['title']: item for item in documents}
        members = {
            'Farming': ['Sample crop record (synthetic)'],
            'Water': ['Sample water record (synthetic)'],
            'Learning': ['Sample water record (synthetic)', 'Sample learning record (synthetic)'],
        }
        folders = list(version.folders.all())
        roots = [folder for folder in folders if folder.parent_id is None]
        if len(roots) != 3 or {folder.folder_name for folder in roots} != set(members):
            raise CommandError('Only the original Farming, Water and Learning seed libraries can be reviewed by this helper.')
        section_names = {'Farming': 'Crop records (synthetic)', 'Water': 'Water records (synthetic)',
                         'Learning': 'Learning records (synthetic)'}
        root_names = {folder.id: folder.folder_name for folder in roots}
        children = [folder for folder in folders if folder.parent_id is not None]
        seen = set()
        for folder in children:
            parent_name = root_names.get(folder.parent_id)
            if parent_name is None or folder.folder_name != section_names[parent_name] or parent_name in seen:
                raise CommandError('Only the explicitly labelled original synthetic seed sections can be reviewed by this helper.')
            seen.add(parent_name)
            expected_ids = {reviewed[title]['dlms_id'] for title in members[parent_name]}
            if set(folder.library_content.values_list('id', flat=True)) != expected_ids:
                raise CommandError('Synthetic seed section memberships changed; this helper cannot authorise that change.')
        libraries = []
        for folder in roots:
            originals = [reviewed[title] for title in members[folder.folder_name]]
            if set(folder.library_content.values_list('id', flat=True)) != {item['dlms_id'] for item in originals}:
                raise CommandError('Synthetic seed library memberships changed; this helper cannot authorise that change.')
            libraries.append({'id': 'synthetic-library-' + folder.folder_name.lower(), 'label': folder.folder_name,
                              'dlms_folder_id': folder.id, 'document_ids': [item['id'] for item in originals]})
        base = staging_base()
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest = base / 'synthetic-reviewed-manifest.json'
        manifest.write_text(json.dumps({'version': 1, 'library_version': version.version_number,
                                        'usage_scope': 'private-development-testing', 'documents': documents,
                                        'libraries': libraries}, indent=2) + '\n')
        self.stdout.write('Synthetic private-development manifest: ' + str(manifest))
