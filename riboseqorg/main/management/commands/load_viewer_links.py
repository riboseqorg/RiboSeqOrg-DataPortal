'''
Load the Trips / GWIPS / RiboCrypt link tables used to build viewer links.

Dry run by default: reports what would be loaded and how it compares with the
Sample availability flags. With --apply, each table given is replaced in a
single transaction.

    python manage.py load_viewer_links --trips-sqlite trips.sqlite
    python manage.py load_viewer_links --trips-sqlite trips.sqlite --apply --sync-flags
    python manage.py load_viewer_links --gwips-trackdb trackdb/ --apply
    python manage.py load_viewer_links --gwips-csv gwips.csv --ribocrypt-csv ribocrypt.csv

Trips is read straight from a copy of the Trips-Viz sqlite database (public
studies and organisms only). GWIPS is read from a GWIPS-viz trackDb dump
(--gwips-trackdb), which is the native, curated study tracks GWIPS already
hosts; the per-run custom tracks built from the portal's own bigWigs are a
separate thing and need no table (see genome_tracks.py). GWIPS and RiboCrypt
can also be read from CSVs whose columns are the model fields (see
main.models.GWIPS / main.models.RiboCrypt).
'''
import csv
import os
import re
import sqlite3
import tarfile
import tempfile
from collections import Counter
from contextlib import ExitStack

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import GWIPS, RiboCrypt, Sample, Study, Trips

RUN_ACCESSION = re.compile(r'^([SED]RR\d+)')
MAX_LEN = 100  # max_length of the link model CharFields

# Study accessions as they appear in a trackDb longLabel, e.g.
# "Ribosome profiles from Cenik et al. (2015) study,  SRP055009,  added ..."
STUDY_ACCESSION = re.compile(r'\b((?:SRP|ERP|DRP)\d+|GSE\d+|PRJ[NED][ABJ]\d+)\b')
# The trackDb groups holding ribosome profiling / mRNA data, as opposed to
# annotation, gene models and comparative genomics
DATA_GROUPS = {'RP-ElongatingRibos', 'RP-InitiatingRibos',
               'Ribo-Coverage', 'mRNA-Coverage'}
ELONGATING, INITIATING = 'RP-ElongatingRibos', 'RP-InitiatingRibos'


def _clip(value) -> str:
    return '' if value is None else str(value)[:MAX_LEN]


def read_trips(path: str, file_types: list, run_projects: dict) -> tuple:
    '''
    Build Trips rows from a Trips-Viz sqlite database.

    Returns:
    - (list): unsaved Trips objects, one per (run, file type)
    - (Counter): counts of skipped files by reason
    '''
    try:
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        rows = db.execute('''
            SELECT f.file_id, f.file_name, f.file_type,
                   o.organism_name, o.transcriptome_list, o.private,
                   s.private, s.study_name, s.srp_nos, s.gse_nos, s.paper_pmid
            FROM files f
            LEFT JOIN organisms o ON o.organism_id = f.organism_id
            LEFT JOIN studies s ON s.study_id = f.study_id
            ORDER BY f.file_id''').fetchall()
    except sqlite3.Error as e:
        raise CommandError(f'Could not read Trips database {path}: {e}')

    trips, skipped, seen = [], Counter(), set()
    for (file_id, file_name, file_type, organism, transcriptome, org_private,
         study_private, study_name, srp, gse, pmid) in rows:
        if file_type not in file_types:
            skipped['other file type'] += 1
            continue
        if org_private != 0 or study_private != 0:
            skipped['private study or organism'] += 1
            continue
        match = RUN_ACCESSION.match(file_name or '')
        if not match:
            skipped['no run accession in file name'] += 1
            continue
        run = match.group(1)
        if run not in run_projects:
            skipped['run not in portal'] += 1
            continue
        if (run, file_type) in seen:
            skipped['duplicate file for run'] += 1
            continue
        seen.add((run, file_type))
        trips.append(Trips(
            BioProject=_clip(run_projects[run]), Run=run,
            Trips_id=str(file_id), file_name=_clip(file_name),
            study_name=_clip(study_name), study_srp=_clip(srp),
            study_gse=_clip(gse), PMID=_clip(pmid),
            organism=_clip(organism), transcriptome=_clip(transcriptome)))
    return trips, skipped


def study_accession_index(studies) -> dict:
    '''
    Map every accession a portal Study is known by to its BioProject.

    Arguments:
    - studies: (BioProject, SRA, GSE) tuples

    Returns:
    - (dict): accession -> BioProject. The first study to claim an accession
      keeps it, so a duplicate in the metadata can't silently move a track.
    '''
    index: dict = {}
    for bioproject, sra, gse in studies:
        for value in (bioproject, sra, gse):
            for part in re.split(r'[;,\s]+', value or ''):
                if part:
                    index.setdefault(part, bioproject)
    return index


def _trackdb_dir(path: str, stack) -> str:
    '''
    The directory holding the trackDb TSVs, extracting a .tgz if needed.
    '''
    if os.path.isdir(path):
        return path
    try:
        temp = stack.enter_context(tempfile.TemporaryDirectory())
        with tarfile.open(path) as tar:
            tar.extractall(temp)
    except (OSError, tarfile.TarError) as e:
        raise CommandError(f'Could not read trackDb dump {path}: {e}')
    # The tarball may hold the TSVs at the top level or in one directory
    if not any(n.startswith('gwips_trackDb_') for n in os.listdir(temp)):
        entries = [os.path.join(temp, n) for n in os.listdir(temp)]
        dirs = [e for e in entries if os.path.isdir(e)]
        if len(dirs) == 1:
            return dirs[0]
    return temp


def _read_tsv(path: str) -> list:
    # Some longLabel/html values carry non-UTF-8 bytes; they are only searched
    # for accessions, so replacing them is harmless
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        return list(csv.DictReader(f, delimiter='\t'))


GLOBAL_PARENT = re.compile(r'^Global', re.IGNORECASE)
PARENT = re.compile(r'^parent (\S+)', re.MULTILINE)


def _parent(row: dict) -> str:
    # trackDb settings are newline-separated, and stored here with a literal \n
    settings = (row.get('settings') or '').replace('\\n', '\n')
    match = PARENT.search(settings)
    return match.group(1) if match else ''


def _link_track(row: dict, containers: dict) -> str:
    '''
    The name to put in an hgTracks URL to turn a study's tracks on.

    hgTracks takes a track name, not a table name, and a subtrack does
    nothing while its parent is hidden. So a sample resolves to its parent, and
    a study aggregate ("<Study>_All_<type>_track", whose parent is a global
    catch-all holding every study) to the study's own container, found by
    name prefix among the study-level tracks of the group, or failing that
    the parent of the study's samples (GWIPS names a few containers
    differently from their samples, e.g. Ji_RiboProInit over Ji15_*). When
    that isn't unambiguous the aggregate's own name is all there is.

    Arguments:
    - row (dict): a trackDb row
    - containers (dict): group -> (names of the study-level tracks in it,
      (sample name, parent) pairs)
    '''
    name, parent = row['tableName'], _parent(row)
    if not parent:
        return name
    if not GLOBAL_PARENT.match(parent):
        return parent
    prefix = name.split('_All_')[0] if '_All_' in name else None
    tops, samples = containers.get(row.get('grp'), (set(), []))
    found = {c for c in tops if prefix and c.startswith(prefix)}
    if not found and prefix:
        found = {p for n, p in samples if n.startswith(prefix + '_')}
    return found.pop() if len(found) == 1 else name


def _pick_table(tables: list) -> str:
    '''
    The track to link for a group. Sorted for a stable choice between equals.
    '''
    return sorted(tables)[0] if tables else ''


def read_gwips_trackdb(path: str, study_index: dict) -> tuple:
    '''
    Build GWIPS rows from a GWIPS-viz trackDb dump.

    The dump is gwips_dbDb.tsv (assemblies) plus one gwips_trackDb_<db>.tsv
    per assembly. Study accessions are not a column: they appear in the
    longLabel of the ribo/mRNA tracks, falling back to the track's html.

    Arguments:
    - path (str): directory of TSVs, or the .tgz holding them
    - study_index (dict): accession -> BioProject (see study_accession_index)

    Returns:
    - (list): unsaved GWIPS objects, one per (study, assembly)
    - (Counter): counts of skipped track rows by reason
    '''
    with ExitStack() as stack:
        directory = _trackdb_dir(path, stack)
        names = sorted(n for n in os.listdir(directory)
                       if n.startswith('gwips_trackDb_') and n.endswith('.tsv'))
        if not names:
            raise CommandError(f'No gwips_trackDb_*.tsv files in {path}')
        organisms = {}
        dbdb = os.path.join(directory, 'gwips_dbDb.tsv')
        if os.path.exists(dbdb):
            organisms = {r['name']: r['scientificName'] for r in _read_tsv(dbdb)}

        skipped = Counter()
        # (BioProject, assembly) -> group -> table names
        found: dict = {}
        for name in names:
            assembly = name[len('gwips_trackDb_'):-len('.tsv')]
            tracks = _read_tsv(os.path.join(directory, name))
            containers: dict = {}
            for row in tracks:
                tops, samples = containers.setdefault(row.get('grp'), (set(), []))
                parent = _parent(row)
                if not parent and not GLOBAL_PARENT.match(row['tableName']):
                    tops.add(row['tableName'])
                elif parent and not GLOBAL_PARENT.match(parent):
                    samples.append((row['tableName'], parent))
            for row in tracks:
                group = (row.get('grp') or '').strip()
                if group not in DATA_GROUPS:
                    skipped['not a ribosome profiling track'] += 1
                    continue
                match = (STUDY_ACCESSION.search(row.get('longLabel') or '')
                         or STUDY_ACCESSION.search(row.get('html') or ''))
                if not match:
                    skipped['no study accession in track'] += 1
                    continue
                bioproject = study_index.get(match.group(1))
                if not bioproject:
                    skipped['study not in portal'] += 1
                    continue
                groups = found.setdefault((bioproject, assembly), {})
                groups.setdefault(group, []).append(_link_track(row, containers))

    rows = []
    for (bioproject, assembly), groups in sorted(found.items()):
        elongating = _pick_table(groups.get(ELONGATING, []))
        initiating = _pick_table(groups.get(INITIATING, []))
        if not elongating and not initiating:
            skipped['no elongating or initiating track for study'] += 1
            continue
        rows.append(GWIPS(
            BioProject=_clip(bioproject),
            Organism=_clip(organisms.get(assembly, '')),
            gwips_db=_clip(assembly),
            GWIPS_Elong_Suffix=_clip(elongating),
            GWIPS_Init_Suffix=_clip(initiating)))
    return rows, skipped


def read_csv(path: str, model) -> list:
    fields = [f.name for f in model._meta.concrete_fields if f.name != 'id']
    try:
        with open(path, newline='') as f:
            reader = csv.DictReader(f)
            missing = set(fields) - set(reader.fieldnames or [])
            if missing:
                raise CommandError(
                    f'{path} is missing columns: {", ".join(sorted(missing))}')
            return [model(**{k: _clip(row[k]) for k in fields}) for row in reader]
    except OSError as e:
        raise CommandError(f'Could not read {path}: {e}')


class Command(BaseCommand):
    help = 'Load Trips/GWIPS/RiboCrypt link tables (dry run unless --apply)'

    def add_arguments(self, parser):
        parser.add_argument('--trips-sqlite', help='Trips-Viz sqlite database')
        parser.add_argument(
            '--trips-types', default='riboseq',
            help='Comma-separated Trips file types to link (default: riboseq)')
        parser.add_argument(
            '--gwips-trackdb',
            help='GWIPS-viz trackDb dump: a directory of TSVs, or the .tgz')
        parser.add_argument('--gwips-csv', help='CSV of GWIPS rows')
        parser.add_argument('--ribocrypt-csv', help='CSV of RiboCrypt rows')
        parser.add_argument(
            '--sync-flags', action='store_true',
            help='Also set Sample.trips_id/gwips_id/ribocrypt_id from the loaded tables')
        parser.add_argument('--apply', action='store_true',
                            help='Write to the database (default: report only)')

    def handle(self, *args, **options):
        sources = ('trips_sqlite', 'gwips_trackdb', 'gwips_csv', 'ribocrypt_csv')
        if not any(options[k] for k in sources):
            raise CommandError('Give at least one of '
                               + ', '.join('--' + s.replace('_', '-') for s in sources))
        if options['gwips_trackdb'] and options['gwips_csv']:
            raise CommandError('Give only one of --gwips-trackdb and --gwips-csv')

        samples = list(Sample.objects.values_list(
            'Run', 'BioProject_id', 'ScientificName',
            'trips_id', 'gwips_id', 'ribocrypt_id'))
        run_projects = {s[0]: s[1] for s in samples}

        # model -> (rows, flag field, function giving the runs each row covers)
        loads = {}
        if options['trips_sqlite']:
            types = [t.strip() for t in options['trips_types'].split(',') if t.strip()]
            rows, skipped = read_trips(options['trips_sqlite'], types, run_projects)
            self.stdout.write(f'Trips: {len(rows)} rows from file types {types}')
            for reason, n in skipped.most_common():
                self.stdout.write(f'  skipped {n:6d}  {reason}')
            loads[Trips] = (rows, 'trips_id', {r.Run for r in rows})
        if options['gwips_trackdb']:
            index = study_accession_index(
                Study.objects.values_list('BioProject', 'SRA', 'GSE'))
            rows, skipped = read_gwips_trackdb(options['gwips_trackdb'], index)
            projects = {r.BioProject for r in rows}
            covered = {s[0] for s in samples if s[1] in projects}
            with_init = sum(1 for r in rows if r.GWIPS_Init_Suffix)
            self.stdout.write(
                f'GWIPS: {len(rows)} native track rows for {len(projects)} studies, '
                f'covering {len(covered)} runs ({with_init} with initiating tracks)')
            for reason, n in skipped.most_common():
                self.stdout.write(f'  skipped {n:6d}  {reason}')
            no_organism = [r.gwips_db for r in rows if not r.Organism]
            if no_organism:
                self.stdout.write(f'  {len(no_organism)} rows have no organism '
                                  f'(assembly missing from gwips_dbDb.tsv): '
                                  f'{sorted(set(no_organism))[:5]}')
            loads[GWIPS] = (rows, 'gwips_id', covered)
        if options['gwips_csv']:
            rows = read_csv(options['gwips_csv'], GWIPS)
            keys = {(r.BioProject, r.Organism) for r in rows}
            covered = {s[0] for s in samples if (s[1], s[2]) in keys}
            unmatched = {k for k in keys
                         if not any((s[1], s[2]) == k for s in samples)}
            self.stdout.write(f'GWIPS: {len(rows)} rows covering {len(covered)} runs')
            if unmatched:
                self.stdout.write(f'  {len(unmatched)} (BioProject, Organism) pairs '
                                  f'match no sample, e.g. {sorted(unmatched)[:5]}')
            loads[GWIPS] = (rows, 'gwips_id', covered)
        if options['ribocrypt_csv']:
            rows = read_csv(options['ribocrypt_csv'], RiboCrypt)
            unknown = {r.Run for r in rows} - set(run_projects)
            self.stdout.write(f'RiboCrypt: {len(rows)} rows')
            if unknown:
                self.stdout.write(f'  {len(unknown)} runs not in portal, '
                                  f'e.g. {sorted(unknown)[:5]}')
            loads[RiboCrypt] = (rows, 'ribocrypt_id', {r.Run for r in rows})

        flag_index = {'trips_id': 3, 'gwips_id': 4, 'ribocrypt_id': 5}
        for model, (rows, flag, runs) in loads.items():
            flagged = {s[0] for s in samples if s[flag_index[flag]]}
            self.stdout.write(
                f'{model.__name__} vs Sample.{flag}: {len(flagged & runs)} agree, '
                f'{len(runs - flagged)} would be newly available, '
                f'{len(flagged - runs)} flagged but not in table')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Dry run: nothing written (use --apply)'))
            return

        # Sample.gwips_id means "this run has bigWigs", which is what the
        # per-run custom tracks need and what sync_bigwig_flags sets. Native
        # GWIPS tracks are study-level and a different thing, so they must not
        # overwrite it.
        skip_flags = {GWIPS} if options['gwips_trackdb'] else set()
        if skip_flags and options['sync_flags']:
            self.stdout.write(self.style.WARNING(
                'Leaving Sample.gwips_id alone: it tracks bigWig availability '
                '(see sync_bigwig_flags), not native GWIPS tracks'))

        with transaction.atomic():
            for model, (rows, flag, runs) in loads.items():
                model.objects.all().delete()
                model.objects.bulk_create(rows, batch_size=500)
                if options['sync_flags'] and model not in skip_flags:
                    Sample.objects.update(**{flag: False})
                    run_list = sorted(runs)
                    for i in range(0, len(run_list), 500):
                        Sample.objects.filter(Run__in=run_list[i:i + 500]).update(**{flag: True})
        self.stdout.write(self.style.SUCCESS(
            'Loaded ' + ', '.join(f'{m.__name__} ({len(r[0])} rows)' for m, r in loads.items())
            + (' and synced flags' if options['sync_flags'] else '')))
