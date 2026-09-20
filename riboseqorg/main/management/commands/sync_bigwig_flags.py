'''
Set Sample.gwips_id ("Available on GWIPS-viz" on /samples) to whether the run
has a genome browser link: bigWigs on disk and a known assembly for its
organism (see main/genome_tracks.py). Keeps the filter in step with the links.

Dry run by default; run on the server, where the bigWigs are, after new
bigWigs are added:

    python manage.py sync_bigwig_flags            # report
    python manage.py sync_bigwig_flags --apply    # write
'''
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from main import genome_tracks
from main.models import Sample

BATCH = 500


class Command(BaseCommand):
    help = 'Set Sample.gwips_id from bigWig availability (dry run unless --apply)'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write to the database (default: report only)')

    def handle(self, *args, **options):
        turn_on, turn_off = [], []
        no_assembly = Counter()
        samples = Sample.objects.only('Run', 'ScientificName', 'BioProject', 'gwips_id')
        for sample in samples.iterator():
            available = genome_tracks.has_tracks(sample)
            if (not available and genome_tracks.assembly_for(sample.ScientificName) is None
                    and (sample.bigwig_forward_link or sample.bigwig_reverse_link)):
                no_assembly[sample.ScientificName] += 1
            if available and not sample.gwips_id:
                turn_on.append(sample.pk)
            elif sample.gwips_id and not available:
                turn_off.append(sample.pk)

        total = Sample.objects.count()
        unchanged = total - len(turn_on) - len(turn_off)
        self.stdout.write(f'{len(turn_on)} runs to mark available, '
                          f'{len(turn_off)} to mark unavailable, {unchanged} unchanged')
        if no_assembly:
            self.stdout.write('Runs with bigWigs but no assembly for their organism '
                              '(add to genome_tracks.GENOME_ASSEMBLIES):')
            for organism, n in no_assembly.most_common():
                self.stdout.write(f'  {n:6d}  {organism or "(no organism)"}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Dry run: nothing written (use --apply)'))
            return

        with transaction.atomic():
            for pks, value in ((turn_on, True), (turn_off, False)):
                for i in range(0, len(pks), BATCH):
                    Sample.objects.filter(pk__in=pks[i:i + BATCH]).update(gwips_id=value)
        self.stdout.write(self.style.SUCCESS('Updated Sample.gwips_id'))
