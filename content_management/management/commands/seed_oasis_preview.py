"""Explicit synthetic fixtures for the isolated local preview."""
import base64
import json
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from content_management.models import Content, LibLayoutImage, LibraryFolder, LibraryVersion, Metadata, MetadataType, User


def sample_pdf(title):
    """Small valid original PDF; no document acquisition or ingestion pipeline."""
    lines = [title, 'Synthetic Oasis Library preview fixture.', 'This is a catalogue example, not technical advice.']
    stream = 'BT /F1 16 Tf 50 740 Td ' + ' 0 -28 Td '.join('(' + line + ') Tj' for line in lines) + ' ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        ('<< /Length ' + str(len(stream.encode())) + ' >>\nstream\n' + stream + '\nendstream').encode(),
    ]
    result = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(result)
    result += b'xref\n0 6\n0000000000 65535 f \n'
    result += b''.join(('%010d 00000 n \n' % offset).encode() for offset in offsets[1:])
    result += ('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref).encode()
    return result


class Command(BaseCommand):
    help = 'Seed clearly labelled synthetic Farming, Water and Learning documents in the isolated preview.'

    def handle(self, *args, **options):
        if not hasattr(settings, 'PREVIEW_STATE_ROOT'):
            raise CommandError('Synthetic seed is available only with dlms.preview_settings.')
        types = {name: MetadataType.objects.get_or_create(name=name)[0] for name in ('Language', 'Creator', 'Keywords', 'Licence')}
        curator, _ = User.objects.get_or_create(name='Oasis Library preview fixtures')
        pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        images = {}
        for group, name in ((1, 'oasis-preview-logo.png'), (2, 'oasis-preview-banner.png')):
            image, created = LibLayoutImage.objects.get_or_create(image_group=group, image_file='images/' + ('logos/' if group == 1 else 'banners/') + name)
            if created:
                image.image_file.save(name, ContentFile(pixel), save=True)
            images[group] = image
        version, _ = LibraryVersion.objects.get_or_create(version_number='oasis-synthetic-preview-v1', defaults={
            'library_name': 'Oasis Library preview - synthetic fixtures', 'library_banner': images[2], 'created_by': curator,
        })
        documents = {}
        for library, title in (
            ('Farming', 'Sample crop record (synthetic)'),
            ('Water', 'Sample water record (synthetic)'),
            ('Learning', 'Sample learning record (synthetic)'),
        ):
            filename = 'oasis-synthetic-' + library.lower() + '.pdf'
            document, created = Content.objects.get_or_create(title=title, defaults={
                'display_title': title,
                'description': 'Synthetic preview document for the ' + library + ' library. Contains no technical advice.',
                'copyright_notes': 'Original synthetic fixture by Kuwala contributors.',
                'rights_statement': 'CC0-1.0 applies to this synthetic fixture only: https://creativecommons.org/publicdomain/zero/1.0/',
                'additional_notes': 'Preview fixture. No publication or expert-review approval is recorded.',
                'reviewed_on': None,
            })
            if created:
                document.content_file.save(filename, ContentFile(sample_pdf(title)), save=True)
                document.file_name = filename
                document.filesize = document.content_file.size
                document.save(update_fields=['file_name', 'filesize'])
            for type_name, value in (('Language', 'English'), ('Creator', 'Kuwala contributors (synthetic preview)'), ('Keywords', library.lower()), ('Licence', 'CC0-1.0 (synthetic fixture only)')):
                document.metadata.add(Metadata.objects.get_or_create(type=types[type_name], name=value)[0])
            folder, _ = LibraryFolder.objects.get_or_create(version=version, folder_name=library, parent=None, defaults={'logo_img': images[1]})
            folder.library_content.add(document)
            documents[library] = (document, folder)
        documents['Learning'][1].library_content.add(documents['Water'][0])
        Path(settings.PREVIEW_STATE_ROOT, 'synthetic-fixtures.json').write_text(json.dumps({
            'synthetic': True, 'version_id': version.id, 'version_number': version.version_number,
        }) + '\n')
        self.stdout.write(self.style.SUCCESS('Synthetic preview fixtures seeded: 3 PDFs; Farming, Water and Learning.'))
