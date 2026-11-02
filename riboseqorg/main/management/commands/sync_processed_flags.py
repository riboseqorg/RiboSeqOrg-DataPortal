'''
Set Sample.processed ("Processed by RDP pipeline" on /samples) from a text
file listing one processed run accession per line.

Dry run by default:

    python manage.py sync_processed_flags processed_runs.txt
    python manage.py sync_processed_flags processed_runs.txt --apply
    python manage.py sync_processed_flags mouse_runs.txt --apply --merge

The default --apply mode treats the file as the complete authoritative list
and resets other flags. Use --merge for a partial list: it only marks the
listed runs and preserves existing flags.
'''
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import Sample

BATCH = 500


class Command(BaseCommand):
    help = 'Set Sample.processed from a list of run accessions (dry run unless --apply)'

    def add_arguments(self, parser):
        parser.add_argument('runs_file', help='File with one run accession per line')
        parser.add_argument('--apply', action='store_true',
                            help='Write to the database (default: report only)')
        parser.add_argument('--merge', action='store_true',
                            help='Only mark listed runs; preserve other processed flags')

    def handle(self, *args, **options):
        try:
            with open(options['runs_file']) as fh:
                runs = {line.strip() for line in fh if line.strip()}
        except OSError as e:
            raise CommandError(e)

        known = set(Sample.objects.values_list('Run', flat=True))
        missing = runs - known
        self.stdout.write(f'{len(runs)} runs listed, {len(runs & known)} in the database, '
                          f'{len(missing)} not found')
        if missing:
            self.stdout.write('Not in database (first 10): ' + ', '.join(sorted(missing)[:10]))

        if not options['apply']:
            mode = 'merge' if options['merge'] else 'replace'
            self.stdout.write(self.style.WARNING(
                f'Dry run ({mode}): nothing written (use --apply)'))
            return

        found = sorted(runs & known)
        with transaction.atomic():
            if not options['merge']:
                Sample.objects.filter(processed=True).update(processed=False)
            for i in range(0, len(found), BATCH):
                Sample.objects.filter(Run__in=found[i:i + BATCH]).update(processed=True)
        mode = 'merged into' if options['merge'] else 'replaced from'
        self.stdout.write(self.style.SUCCESS(
            f'{mode} list; updated Sample.processed'))
