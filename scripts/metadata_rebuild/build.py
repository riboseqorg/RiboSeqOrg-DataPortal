"""
Rebuild the portal's Sample, Study and OpenColumns tables.

Reads freshly fetched SRA records (fetch.py), keeps the curated work that
exists (the human-checked RiboCrypt sheet, the October 2024 database, the
pipeline's standardised values), and writes a new database next to the
current one together with CSVs and a report. The current database is never
modified.

Usage (from scripts/):
    python -m metadata_rebuild.build \
        --sra-cache ../build/metadata_rebuild/sra_cache \
        --historical-sra ~/projects/Metadata-Curation/SraRunInfo \
        --current-db ../riboseqorg/db.sqlite3 \
        --baseline-db ../build/metadata_rebuild/db_2024-10.sqlite3 \
        --manual ~/projects/Metadata-Curation/resources/RiboCrypt_Metadata_13_09_24.csv \
        --standardized ~/projects/Metadata-Curation/temp_files/standardized_columns_final_2025-08-30.csv \
        --whitelist-samples ~/projects/Metadata-Curation/resources/whitelisted_samples.csv \
        --out ../build/metadata_rebuild/output
"""
import argparse
import csv
import gzip
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import assay
from .authorship import Resolver, Web, shared_author_strings
from .core import CORE_COLUMNS, CoreResolver
from .merge import (RUNINFO_FIELDS, Merger, Standardiser, clean_value,
                    combine)
from .studies import STUDY_FIELDS, PubMed, build_study, valid_pmid

csv.field_size_limit(10 ** 9)

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'inputs'
REPO = HERE.parents[1]
DEFAULT_OUT = REPO / 'build' / 'metadata_rebuild'

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'riboseqorg'))
from main.metadata_cleaning import (CURATED_COLUMNS,  # noqa: E402
                                    canonical_forms, normalise_key, suggest)

# finding_riboseq.R: a run is a Ribo-seq candidate if any field mentions one
# of these (case-insensitive).
RIBO_TERMS = ['ribo', 'footprint', 'rpf', 'rfp', '80s', 'mnase',
              'translatome']
# Library strategies that cannot be RNA libraries. Layout and platform are
# not filters here: massiveNGSpipe's single-end/Illumina filter decides what
# it can process, not what belongs in the catalogue.
STRATEGY_EXCLUDED = {
    'WGS', 'WXS', 'WGA', 'AMPLICON', 'CHIP-SEQ', 'ATAC-SEQ',
    'BISULFITE-SEQ', 'MEDIP-SEQ', 'MBD-SEQ', 'DNASE-HYPERSENSITIVITY',
    'HI-C', 'CHIA-PET', 'TN-SEQ', 'SYNTHETIC-LONG-READ', 'CLONE',
    'POOLCLONE', 'CLONEEND', 'FINISHING', 'TARGETED-CAPTURE', 'FAIRE-SEQ',
    'MRE-SEQ', 'VALIDATION', 'WCS', 'FL-CDNA', 'EST',
}
INT_FIELDS = {'spots', 'bases', 'avgLength', 'size_MB'}
# Fetched as evidence for typing a run, never for deciding whether it belongs
# in the catalogue: the construction protocol is study-wide boilerplate and
# routinely mentions Ribo-Zero (an rRNA depletion kit) or "Ribo-seq and
# RNA-seq", which would drag in whole RNA-seq studies.
EVIDENCE_FIELDS = {'experiment_title', 'design_description',
                   'library_construction_protocol'}
# rRNA depletion is not ribosome profiling.
NOT_A_RIBO_TERM = re.compile(r'ribo[\s_-]?(zero|gold|minus|pool)|'
                             r'ribosomal rna depletion', re.IGNORECASE)
FLAG_FIELDS = ['verified', 'trips_id', 'gwips_id', 'ribocrypt_id',
               'process_status', 'FASTA_file']
BAD_AUTHORS = {'makar', '0.0', 'nan', ''}
# Column order of the published release files
# (riboseqorg/main/static/Records/RiboSeqOrg_Metadata_v*.csv)
RELEASE_FIELDS = (
    'verified trips_id gwips_id ribocrypt_id process_status FASTA_file '
    'BioProject GEO Run spots bases avgLength size_MB Experiment LibraryName '
    'LibraryStrategy LibrarySelection LibrarySource LibraryLayout InsertSize '
    'InsertDev Platform Model SRAStudy Study_Pubmed_id Sample BioSample '
    'SampleType TaxID ScientificName SampleName CenterName Submission MONTH '
    'YEAR AUTHOR sample_source sample_title LIBRARYTYPE REPLICATE CONDITION '
    'INHIBITOR BATCH TIMEPOINT TISSUE CELL_LINE FRACTION ENA_first_public '
    'ENA_last_update INSDC_center_alias INSDC_center_name INSDC_first_public '
    'INSDC_last_update INSDC_status ENA_checklist GEO_Accession '
    'Experiment_Date date_sequenced submission_date date STAGE GENE Sex '
    'Strain Age Infected Disease Genotype Feeding Temperature SiRNA SgRNA '
    'ShRNA Plasmid Growth_Condition Stress Cancer microRNA Individual '
    'Antibody Ethnicity Dose Stimulation Host UMI Adapter Separation '
    'rRNA_depletion Barcode Monosome_purification Nuclease Kit Info').split()


# --- inputs ------------------------------------------------------------------

def open_text(path: Path):
    """Open a plain or gzipped text file."""
    if str(path).endswith('.gz'):
        return gzip.open(path, 'rt', newline='')
    return open(path, newline='')


def read_runinfo(path: Path):
    """[(runinfo dict, [(attribute, value)])] keeping repeated headers."""
    with open(path, newline='') as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            return []
        rows = []
        for values in reader:
            values += [''] * (len(header) - len(values))
            info = {f: '' for f in RUNINFO_FIELDS}
            attrs = []
            for name, value in zip(header, values):
                if name in info and not info[name]:
                    info[name] = value
                elif name not in RUNINFO_FIELDS:
                    attrs.append((name, value))
            rows.append((info, attrs))
        return rows


def load_misaligned(path: Path = INPUTS / 'misaligned_projects.txt'):
    """Projects listed in inputs/, computed once by misaligned_projects()."""
    return {line.strip() for line in path.read_text().splitlines()
            if line.strip()}


def misaligned_projects(historical: Path):
    """
    Projects whose historical SraRunInfo attribute columns are shifted:
    ORFik cbinds one attribute row per experiment onto one row per run.
    """
    out = set()
    for path in historical.glob('SraRunInfo_*.csv'):
        rows = read_runinfo(path)
        if rows and rows[0][1] and \
                len({r['Experiment'] for r, _ in rows}) < len(rows):
            out.add(path.stem.replace('SraRunInfo_', ''))
    return out


def read_db(path: Path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    samples = {r['Run']: dict(r) for r in con.execute(
        'select * from main_sample order by id')}
    studies = {r['BioProject']: dict(r) for r in con.execute(
        'select * from main_study')}
    con.close()
    return samples, studies


def read_csv_by_run(path: Path, keep=None):
    out = {}
    with open_text(path) as fh:
        for row in csv.DictReader(fh):
            if keep is None or keep(row):
                out.setdefault(row['Run'], row)
    return out


# --- per-run fields ----------------------------------------------------------

def organism_name_cleanup(name: str) -> str:
    """Port of massiveNGSpipe::organism_name_cleanup (portal convention)."""
    if re.search(r'coronavirus 2|sars cov 2', name, re.IGNORECASE):
        return 'Sars cov2'
    name = re.sub(r' substr\..*', '', name)
    name = re.sub(r' (K.12|BY4741|H37Rv|PAO1|Go1)', '', name, count=1,
                  flags=re.IGNORECASE)
    name = re.sub(r' str\..*', '', name)
    return re.sub(r' subsp\..*', '', name)


def to_int(value):
    value = clean_value(value)
    try:
        return int(float(value)) if value else None
    except ValueError:
        return None


def selection(info, attrs, whitelisted: bool):
    """(include, reason)."""
    title = info['sample_title'].casefold()
    if 'is currently private' in title:
        return False, 'private on SRA'
    strategy = info['LibraryStrategy'].upper()
    if info.get('LibrarySource', '').upper() == 'GENOMIC' and \
            strategy.lower() in assay.NOT_RNA_STRATEGIES:
        return False, f'DNA library ({info["LibraryStrategy"]}, genomic)'
    if strategy in STRATEGY_EXCLUDED:
        return False, f'library strategy {info["LibraryStrategy"]}'
    if whitelisted:
        return True, 'whitelisted or manually curated'
    text = ' '.join([v for k, v in info.items()
                     if k not in EVIDENCE_FIELDS] +
                    [v for _, v in attrs])
    text = NOT_A_RIBO_TERM.sub(' ', text).casefold()
    if any(term in text for term in RIBO_TERMS):
        return True, 'Ribo-seq term in metadata'
    return False, 'no Ribo-seq term in metadata'


class Builder:

    def __init__(self, args):
        self.args = args
        self.merger = Merger()
        self.standardiser = Standardiser()
        self.core = CoreResolver()
        self.current, self.current_studies = read_db(args.current_db)
        self.baseline, self.baseline_studies = read_db(args.baseline_db)
        self.manual = read_csv_by_run(
            args.manual,
            lambda r: r.get('CHECKED', '').strip().lower() not in ('', 'auto'))
        self.st = read_csv_by_run(args.standardized)
        self.whitelist = set(read_csv_by_run(args.whitelist_samples)) \
            if args.whitelist_samples else set()
        self.misaligned = misaligned_projects(args.historical_sra) \
            if args.historical_sra else load_misaligned()
        self.report = defaultdict(Counter)
        self.examples = defaultdict(list)
        self.assay_texts = {}
        # Projects where the SRA experiment title differs between runs. GEO
        # writes the sample's own strategy there ('GSM…: …; RNA-Seq'), but
        # many ENA submissions repeat the study title on every run, so it
        # only counts as run-level evidence when it varies.
        self.per_run_experiment_title = set()

    # raw records ------------------------------------------------------------
    def load_raw(self):
        cache, hist = self.args.sra_cache, self.args.historical_sra
        status = {}
        log = cache / 'fetch_log.csv'
        if log.exists():
            with open(log, newline='') as fh:
                status = {r['BioProject']: r['status']
                          for r in csv.DictReader(fh)}
        records = {}
        project_source = {}
        for path in sorted(cache.glob('SraRunInfo_*.csv')):
            acc = path.stem.replace('SraRunInfo_', '')
            project_source[acc] = 'fetched'
            for info, attrs in read_runinfo(path):
                records.setdefault(info['Run'],
                                   (info, attrs, attrs, acc, 'fetched'))
        # Projects SRA no longer serves at all: their records are vendored
        # in inputs/legacy_runinfo so the samples are not silently lost.
        for path in sorted((INPUTS / 'legacy_runinfo').glob(
                'SraRunInfo_*.csv')):
            acc = path.stem.replace('SraRunInfo_', '')
            if acc in project_source:
                continue
            project_source[acc] = 'legacy'
            for info, attrs in read_runinfo(path):
                values = [] if acc in self.misaligned else attrs
                records.setdefault(info['Run'],
                                   (info, values, attrs, acc, 'legacy'))
        # Projects that could not be fetched this time fall back to the
        # historical file. Their attributes are dropped if that file is one
        # of the misaligned ones.
        for path in sorted(hist.glob('SraRunInfo_*.csv')) if hist else ():
            acc = path.stem.replace('SraRunInfo_', '')
            if acc in project_source:
                continue
            if status.get(acc) == 'no_runs':
                project_source[acc] = 'gone'
                continue
            project_source[acc] = 'historical'
            for info, attrs in read_runinfo(path):
                if info['Study_Pubmed_id'] in ('1', '3'):
                    info['Study_Pubmed_id'] = ''
                    info['AUTHOR'] = ''
                # Shifted attributes still say what the project is about, so
                # they count for selection, but their values are not used.
                values = [] if acc in self.misaligned else attrs
                records.setdefault(info['Run'],
                                   (info, values, attrs, acc, 'historical'))
        self.project_source = project_source
        titles = defaultdict(set)
        for info, _, _, acc, _ in records.values():
            titles[acc].add(info.get('experiment_title', ''))
        self.per_run_experiment_title = {acc for acc, values in titles.items()
                                         if len(values) > 1}
        return records

    # one run ----------------------------------------------------------------
    def build_sample(self, run, info, attrs, origin):
        cur = self.current.get(run) or {}
        base = self.baseline.get(run) or {}
        prev = cur or base
        merged, unmapped = self.merger.merge(attrs)
        s = {}
        for f in RUNINFO_FIELDS:
            if f in ('GEO',):
                continue
            s[f] = to_int(info[f]) if f in INT_FIELDS else clean_value(info[f])
        s['ScientificName'] = organism_name_cleanup(s['ScientificName'])
        s['Study_Pubmed_id'] = valid_pmid(info['Study_Pubmed_id']) or \
            valid_pmid(prev.get('Study_Pubmed_id'))
        author = clean_value(info['AUTHOR'])
        if author.casefold() in BAD_AUTHORS:
            author = next((a for a in (prev.get('AUTHOR'), base.get('AUTHOR'))
                           if clean_value(a).casefold() not in BAD_AUTHORS),
                          '')
        s['AUTHOR'] = clean_value(author)
        gse = clean_value(info.get('GEO'))
        if not gse.startswith('GSE'):
            gse = next((g for g in (cur.get('GEO'), base.get('GEO'))
                        if str(g or '').startswith('GSE')), '')
        s['GEO'] = gse
        s['BioProject'] = info['BioProject']

        # open (non-core) curated columns: rebuilt from raw attributes
        for col in CURATED_COLUMNS:
            if col not in CORE_COLUMNS:
                s[col] = merged.get(col, '')
        s['Info'] = merged.get('Info', '')
        s['BATCH'] = ''

        # core columns
        man = self.manual.get(run, {})
        st = self.st.get(run, {})
        text = dict(merged)
        text.update(sample_title=s['sample_title'],
                    sample_source=s['sample_source'],
                    LibraryName=s['LibraryName'])
        misaligned = info['BioProject'] in self.misaligned
        sources = {}
        for col in CORE_COLUMNS:
            candidates = {
                'manual': man.get(col, ''),
                'baseline': base.get(col, ''),
                'st': st.get(col + '_st', ''),
                'auto': self.standardiser.standardise(col, text),
                'strategy': 'Ribo-Seq' if col == 'LIBRARYTYPE' and
                s['LibraryStrategy'].casefold() == 'ribo-seq' else '',
            }
            if col == 'LIBRARYTYPE':
                lt_candidates = candidates  # completed after studies exist
            value, source, rejected = self.core.resolve(
                col, candidates, misaligned=misaligned)
            s[col] = value
            sources[col] = source
            for src, raw in rejected:
                self.report[f'rejected {col}'][f'{src}: {raw}'] += 1
        strain = self.core.strain_from_cell_line(
            [man.get('CELL_LINE'), base.get('CELL_LINE')])
        if strain and not s['Strain']:
            s['Strain'] = strain
            self.report['moved']['CELL_LINE strain -> Strain'] += 1
        # manual sheet extras
        if re.fullmatch(r'\d{1,2}|b\d{1,2}', man.get('BATCH', '').strip()):
            s['BATCH'] = man['BATCH'].strip()
        gene = clean_value(man.get('GENE', ''))
        if gene:
            s['GENE'] = gene

        # portal flags are carried over; they come from other resources
        for f in FLAG_FIELDS:
            s[f] = prev.get(f, '' if f == 'process_status' else 0)
            if s[f] is None:
                s[f] = '' if f == 'process_status' else 0
        for f in ('ENA_first_public', 'ENA_last_update', 'INSDC_center_alias',
                  'INSDC_center_name', 'INSDC_first_public',
                  'INSDC_last_update', 'INSDC_status', 'ENA_checklist',
                  'GEO_Accession', 'Experiment_Date', 'date_sequenced',
                  'submission_date', 'date'):
            s[f] = clean_value(prev.get(f, ''))
        s['__lt_candidates'] = lt_candidates
        self.assay_texts[run] = (
            # per-run text first; the construction protocol is usually the
            # same for every library in a submission, so it is a fallback
            [s['sample_title'], s['LibraryName']] +
            ([assay.clean_experiment_title(s['experiment_title'])]
             if s['BioProject'] in self.per_run_experiment_title else []) +
            [v for k, v in attrs if assay.ASSAY_ATTRIBUTES.match(k)],
            [s['sample_source'], s['design_description'],
             s['library_construction_protocol']] +
            ([] if s['BioProject'] in self.per_run_experiment_title
             else [assay.clean_experiment_title(s['experiment_title'])]) +
            [v for k, v in attrs if assay.CONTEXT_ATTRIBUTES.match(k)])
        s['_origin'] = origin
        s['_origin_group'] = 'current' if cur else 'oct_2024' if base \
            else 'new'
        s['_misaligned_project'] = misaligned
        for col, src in sources.items():
            s[f'_source_{col}'] = src
        return s, unmapped

    # all runs ---------------------------------------------------------------
    def run(self):
        records = self.load_raw()
        known = set(self.current) | set(self.baseline)
        samples, unmapped_by_project, exclusions = [], defaultdict(dict), []
        decisions = {}
        for run, (info, attrs, sel_attrs, acc, origin) in records.items():
            whitelisted = run in self.whitelist or run in self.manual
            decisions[run] = selection(info, sel_attrs, whitelisted)
        # A run already in the portal stays if its study has Ribo-seq runs:
        # these are the study's own controls (e.g. matched mRNA-seq), which
        # only matched the terms before through misaligned attributes.
        ribo_projects = {records[r][0]['BioProject'] for r, (keep, _)
                         in decisions.items() if keep}
        for run, (keep, reason) in decisions.items():
            info = records[run][0]
            if not keep and run in known and \
                    reason == 'no Ribo-seq term in metadata' and \
                    info['BioProject'] in ribo_projects:
                decisions[run] = (True, 'already in portal, in a Ribo-seq '
                                        'study')
        for run, (info, attrs, sel_attrs, acc, origin) in records.items():
            keep, reason = decisions[run]
            if not keep:
                if run in known:
                    exclusions.append(self._exclusion(run, info, reason))
                continue
            self.report['selected'][reason] += 1
            s, unmapped = self.build_sample(run, info, attrs, origin)
            samples.append(s)
            for k, v in unmapped.items():
                vals = unmapped_by_project[s['BioProject']].setdefault(k, [])
                if v not in vals:
                    vals.append(v)
        seen = {s['Run'] for s in samples}
        for run in known - seen - {e['Run'] for e in exclusions}:
            row = self.current.get(run) or self.baseline.get(run)
            gone = self.project_source.get(row.get('BioProject_id')) == 'gone'
            exclusions.append({
                'Run': run, 'BioProject': row.get('BioProject_id', ''),
                'reason': 'project no longer on SRA' if gone
                else 'run not found in SRA records',
                'in_current_db': run in self.current,
                'in_oct_2024_db': run in self.baseline,
                'LibraryLayout': row.get('LibraryLayout', ''),
                'Platform': row.get('Platform', ''),
                'LibraryStrategy': row.get('LibraryStrategy', ''),
            })
        self.snap_spellings(samples)
        return samples, unmapped_by_project, exclusions

    def _exclusion(self, run, info, reason):
        return {'Run': run, 'BioProject': info['BioProject'],
                'reason': reason, 'in_current_db': run in self.current,
                'in_oct_2024_db': run in self.baseline,
                'LibraryLayout': info['LibraryLayout'],
                'Platform': info['Platform'],
                'LibraryStrategy': info['LibraryStrategy']}

    def snap_spellings(self, samples):
        """Case/whitespace/'1.0' variants -> the most common spelling."""
        for col in CURATED_COLUMNS:
            counts = Counter(s[col] for s in samples if s[col])
            canonical = canonical_forms(counts)
            for s in samples:
                if s[col]:
                    snapped = canonical.get(normalise_key(s[col]), s[col])
                    if snapped != s[col]:
                        self.report['spelling'][
                            f'{col}: {s[col]} -> {snapped}'] += 1
                        s[col] = snapped

    # data type, using the study text ---------------------------------------
    def classify_assays(self, samples, studies):
        text = {st['BioProject']: ' '.join(
            st.get(f, '') for f in ('Title', 'Description', 'Study_abstract'))
            for st in studies}
        for s in samples:
            run_texts, context = self.assay_texts[s['Run']]
            label, rule = assay.classify(
                run_texts, text.get(s['BioProject'], ''),
                s['LibraryStrategy'], s['LibrarySource'], context)
            candidates = s.pop('__lt_candidates')
            candidates['assay' if rule in ('run', 'serp') else
                       'assay_study'] = label
            value, source, _ = self.core.resolve(
                'LIBRARYTYPE', candidates,
                misaligned=s['_misaligned_project'])
            if value != s['LIBRARYTYPE']:
                self.report['data type'][
                    f"{s['LIBRARYTYPE'] or '(none)'} -> {value} ({source})"] += 1
            s['LIBRARYTYPE'], s['_source_LIBRARYTYPE'] = value, source
            s['_assay_rule'] = rule
        for st in studies:
            st['seq_types'] = ';'.join(sorted(
                {s['LIBRARYTYPE'] for s in samples
                 if s['BioProject'] == st['BioProject'] and s['LIBRARYTYPE']}))

    # studies ----------------------------------------------------------------
    def build_studies(self, samples, pubmed, resolver=None):
        by_project = defaultdict(list)
        for s in samples:
            by_project[s['BioProject']].append(s)
        rows, notes = [], {}
        for acc, members in sorted(by_project.items()):
            existing = self.current_studies.get(acc) or \
                self.baseline_studies.get(acc)
            abstract_path = self.args.sra_cache / f'abstract_{acc}.csv'
            if not abstract_path.exists():
                abstract_path = INPUTS / 'legacy_runinfo' / \
                    f'abstract_{acc}.csv'
            abstract = ''
            if abstract_path.exists():
                with open(abstract_path, newline='') as fh:
                    rows_ = list(csv.reader(fh))
                    abstract = rows_[1][0] if len(rows_) > 1 and rows_[1] \
                        else ''
            row, n = build_study(acc, members, existing, abstract, pubmed,
                                 resolver)
            rows.append(row)
            if n:
                notes[acc] = n
            self.report['authorship'][row['Authorship_source'] or
                                      'none'] += 1
        return rows, notes


# --- outputs -----------------------------------------------------------------

def write_db(out_db: Path, current_db: Path, samples, studies, open_columns,
             current_ids):
    shutil.copy(current_db, out_db)
    con = sqlite3.connect(out_db)
    sample_cols = [r[1] for r in con.execute('pragma table_info(main_sample)')]
    study_cols = [r[1] for r in con.execute('pragma table_info(main_study)')]
    # The copy predates migration 0003, so add its columns here; the output
    # database is otherwise missing the authorship provenance it just built.
    with con:
        for field in STUDY_FIELDS:
            if field not in study_cols:
                con.execute(f'alter table main_study add column "{field}" '
                            "varchar(1000) not null default ''")
                study_cols.append(field)
    next_id = max(current_ids.values(), default=0) + 1
    with con:
        con.execute('delete from main_opencolumns')
        con.execute('delete from main_sample')
        con.execute('delete from main_study')
        con.executemany(
            f'insert into main_study ({",".join(study_cols)}) values '
            f'({",".join("?" * len(study_cols))})',
            [[row.get(c, '') for c in study_cols] for row in studies])
        values = []
        for s in samples:
            sid = current_ids.get(s['Run'])
            if sid is None:
                sid, next_id = next_id, next_id + 1
            row = dict(s, id=sid, BioProject_id=s['BioProject'])
            values.append([row.get(c, '') if c not in
                           ('spots', 'bases', 'avgLength', 'size_MB')
                           else row.get(c) for c in sample_cols])
        con.executemany(
            f'insert into main_sample ({",".join(sample_cols)}) values '
            f'({",".join("?" * len(sample_cols))})', values)
        con.executemany(
            'insert into main_opencolumns (column_name, bioproject, "values")'
            ' values (?, ?, ?)', open_columns)
        con.execute("update sqlite_sequence set seq = (select max(id) from "
                    "main_sample) where name = 'main_sample'")
    orphans = con.execute(
        'select count(*) from main_sample s left join main_study t on '
        's.BioProject_id = t.BioProject where t.BioProject is null'
    ).fetchone()[0]
    con.execute('vacuum')
    con.close()
    return orphans


STUDY_RIBO = re.compile(
    r'(?<![a-z])(ribo(?:some)?[\s_-]*(?:seq|profil\w*|footprint\w*)|'
    r'footprint\w*|rpf|translatome|translation(?:al)? (?:efficiency|control|'
    r'regulation|landscape)|ribosome)(?![a-z])', re.IGNORECASE)


def review_queue(samples, studies, assay_texts):
    """
    Runs whose data type needs a curator, with the evidence to decide.

    Each row carries what the rules saw, how the rest of the study is
    labelled, the read statistics, and an empty `decision` column.
    """
    study_by_id = {s['BioProject']: s for s in studies}
    study_text = {acc: ' '.join(
        st.get(f, '') for f in ('Title', 'Description', 'Study_abstract'))
        for acc, st in study_by_id.items()}
    labelled = defaultdict(Counter)
    by_project = defaultdict(list)
    for s in samples:
        labelled[s['BioProject']][s['LIBRARYTYPE'] or '(none)'] += 1
        by_project[s['BioProject']].append(s)
    out = []
    for s in samples:
        reasons = []
        acc = s['BioProject']
        if not s['LIBRARYTYPE']:
            reasons.append('no data type')
        elif s['_source_LIBRARYTYPE'] == 'assay_study':
            reasons.append('data type inferred from the study text only')
        strategy = s['LibraryStrategy'].casefold()
        if strategy == 'ribo-seq' and s['LIBRARYTYPE'] == 'RNA-Seq':
            reasons.append('SRA strategy Ribo-seq, labelled RNA-Seq')
        if not STUDY_RIBO.search(study_text.get(acc, '')) and \
                labelled[acc]['Ribo-Seq'] == 0:
            reasons.append('study shows no Ribo-seq signal')
        if not reasons:
            continue
        run_texts, context_texts = assay_texts.get(s['Run'], ([], []))
        suggestion, evidence = assay.explain(run_texts)
        if not suggestion:
            suggestion, evidence = assay.explain(context_texts)
            evidence = f'(fallback text) {evidence}' if evidence else ''
        siblings = [f'{t}: {n}' for t, n in labelled[acc].most_common()
                    if t != '(none)']
        examples = [f'{o["sample_title"][:40]} -> {o["LIBRARYTYPE"]}'
                    for o in by_project[acc]
                    if o['LIBRARYTYPE'] and o['Run'] != s['Run']][:3]
        st = study_by_id.get(acc, {})
        out.append({
            'Run': s['Run'], 'BioProject': acc,
            'decision': '', 'reasons': '; '.join(reasons),
            'LIBRARYTYPE': s['LIBRARYTYPE'],
            'source': s['_source_LIBRARYTYPE'],
            'rule': s.get('_assay_rule', ''),
            'rule_suggestion': suggestion,
            'rule_evidence': evidence,
            'LibraryStrategy': s['LibraryStrategy'],
            'LibrarySelection': s['LibrarySelection'],
            'avgLength': s['avgLength'], 'spots': s['spots'],
            'sample_title': s['sample_title'],
            'LibraryName': s['LibraryName'],
            'experiment_title': s['experiment_title'],
            'design_description': s['design_description'][:300],
            'library_construction_protocol':
                s['library_construction_protocol'][:400],
            'sample_attributes': ' | '.join(
                t for t in run_texts[3:] + context_texts if t)[:300],
            'other_types_in_study': ', '.join(siblings),
            'labelled_siblings': ' | '.join(examples),
            'study_title': st.get('Title', ''),
            'study_abstract': (st.get('Study_abstract') or
                               st.get('Paper_abstract', ''))[:400],
            'curated_before': s['_origin_group'],
            'sra_url': f'https://www.ncbi.nlm.nih.gov/sra/?term={s["Run"]}',
        })
    return out


def read_authorship_overrides(path: Path) -> dict:
    """
    Curated authorship: BioProject,PMID,Authors[,note]. These beat every
    automatic source, so this is where a curator's decision on a review row
    goes.
    """
    if not path or not Path(path).exists():
        return {}
    with open(path, newline='') as fh:
        return {r['BioProject'].strip(): r for r in csv.DictReader(fh)
                if r.get('BioProject', '').strip()}


def authorship_queue(studies, resolver):
    """
    Studies whose ownership a person still has to settle, with the evidence.

    Three kinds of row: a citing paper that could not be tied to the
    submitters, a PubMed ID nothing links to the data, and a study credited
    to nobody at all.
    """
    out = []
    for st in studies:
        acc = st['BioProject']
        ev = resolver.seen.get(acc)
        candidates = ev.candidates if ev else []
        unverified = [c for c in candidates if not c['verified']]
        reasons = []
        if st['Authorship_source'] == 'sra_pmid':
            reasons.append('PMID comes from SRA only; NCBI does not link it')
        if not st['Authors'] and unverified:
            reasons.append('a paper cites the accession but its authors are '
                           'not the submitters')
        if not st['Authors'] and not unverified:
            reasons.append('no paper and no submitter names' if not
                           st['Submitters'] else 'no paper found')
        if not reasons:
            continue
        out.append({
            'BioProject': acc, 'decision_PMID': '', 'decision_Authors': '',
            'reasons': '; '.join(reasons),
            'Name': st['Name'], 'Release_Date': st['Release_Date'][:10],
            'PMID': st['PMID'], 'PMID_source': st['PMID_source'],
            'Authors': st['Authors'],
            'Authorship_source': st['Authorship_source'],
            'Submitters': st['Submitters'], 'Institution': st['Institution'],
            'GSE': st['GSE'], 'SRA': st['SRA'],
            'study_title': st['Title'][:200],
            'candidates': ' | '.join(
                f"{c['pmid'] or c['id']} ({c['year']}) "
                f"{c['authorString'][:40]} -> {c['reason']}"
                for c in candidates[:4]),
            'bioproject_url':
                f'https://www.ncbi.nlm.nih.gov/bioproject/{acc}',
        })
    return out


def write_csv(path: Path, rows, fields):
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def residual_artefacts(samples):
    """Run the audit's detector over the rebuilt values."""
    out = Counter()
    for col in CURATED_COLUMNS:
        counts = Counter(s[col] for s in samples)
        for sug in suggest(col, counts).suggestions:
            out[sug.rule] += sug.rows
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--sra-cache', type=Path,
                   default=DEFAULT_OUT / 'sra_cache')
    p.add_argument('--historical-sra', type=Path,
                   help='Optional: the Metadata-Curation SraRunInfo folder, '
                        'used only as a fallback for projects that fail to '
                        'fetch')
    p.add_argument('--current-db', type=Path,
                   default=REPO / 'riboseqorg' / 'db.sqlite3')
    p.add_argument('--baseline-db', type=Path,
                   default=DEFAULT_OUT / 'db_2024-10.sqlite3')
    p.add_argument('--manual', type=Path,
                   default=INPUTS / 'ribocrypt_manual_curation.csv.gz')
    p.add_argument('--standardized', type=Path,
                   default=INPUTS /
                   'standardized_columns_final_2025-08-30.csv.gz')
    p.add_argument('--whitelist-samples', type=Path,
                   default=INPUTS / 'whitelisted_samples.csv.gz')
    p.add_argument('--out', type=Path, default=DEFAULT_OUT / 'output')
    p.add_argument('--authorship', type=Path,
                   default=HERE / 'resources' / 'study_authorship.csv',
                   help='Curated BioProject,PMID,Authors overrides, which '
                        'beat every automatic source')
    p.add_argument('--authorship-cache', type=Path,
                   default=DEFAULT_OUT / 'authorship_cache',
                   help='Where GEO, Europe PMC and elink answers are kept, '
                        'so a rebuild can repeat offline')
    p.add_argument('--no-europepmc', action='store_true',
                   help='Do not look for papers that cite an accession')
    p.add_argument('--offline', action='store_true',
                   help='Do not query PubMed/BioProject for study details')
    p.add_argument('--api-key')
    p.add_argument('--release', default='',
                   help='Also write RiboSeqOrg_Metadata_v<RELEASE>.csv, '
                        'e.g. 2026.09')
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    b = Builder(args)
    samples, unmapped, exclusions = b.run()
    pubmed, entrez = None, None
    if not args.offline:
        from .fetch import Entrez
        entrez = Entrez(args.api_key)
        pubmed = PubMed(entrez)
    resolver = Resolver(
        pubmed=pubmed, entrez=entrez,
        web=Web(cache_dir=args.authorship_cache, offline=args.offline),
        manual=read_authorship_overrides(args.authorship),
        use_europepmc=not args.no_europepmc)
    studies, study_notes = b.build_studies(samples, pubmed, resolver)
    b.classify_assays(samples, studies)

    authors_queue = authorship_queue(studies, resolver)
    # One stranger's author list spread over many studies is what the old
    # esearch("nan") bug looked like. Stop before writing a database.
    shared = shared_author_strings(studies)
    if shared:
        write_csv(args.out / 'studies.csv', studies, STUDY_FIELDS)
        if authors_queue:
            write_csv(args.out / 'authorship_queue.csv', authors_queue,
                      list(authors_queue[0]))
        for authors, pmids in shared.items():
            print(f'ERROR: {len(pmids)} papers share the author list '
                  f'{authors[:60]!r}: {", ".join(pmids[:5])}', file=sys.stderr)
        raise SystemExit('authorship looks contaminated: see studies.csv. '
                         'No database was written.')

    open_columns = [(k, acc, ','.join(v)) for acc, cols in
                    sorted(unmapped.items()) for k, v in cols.items()]
    current_ids = {run: r['id'] for run, r in b.current.items()}
    orphans = write_db(args.out / 'db.sqlite3', args.current_db, samples,
                       studies, open_columns, current_ids)

    sample_fields = [f for f in samples[0] if not f.startswith('_')]
    extra = [f for f in samples[0] if f.startswith('_')]
    write_csv(args.out / 'samples.csv', samples, sample_fields + extra)
    write_csv(args.out / 'studies.csv', studies, STUDY_FIELDS)
    queue = review_queue(samples, studies, b.assay_texts)
    if queue:
        write_csv(args.out / 'review_queue.csv', queue, list(queue[0]))
    if authors_queue:
        write_csv(args.out / 'authorship_queue.csv', authors_queue,
                  list(authors_queue[0]))
    if args.release:
        write_csv(args.out / f'RiboSeqOrg_Metadata_v{args.release}.csv',
                  sorted(samples, key=lambda s: (s['BioProject'], s['Run'])),
                  RELEASE_FIELDS)
    write_csv(args.out / 'excluded_runs.csv', exclusions,
              ['Run', 'BioProject', 'reason', 'in_current_db',
               'in_oct_2024_db', 'LibraryLayout', 'Platform',
               'LibraryStrategy'])
    summary = {
        'samples': len(samples),
        'studies': len(studies),
        'orphan_samples': orphans,
        'projects_by_source': Counter(b.project_source.values()),
        'samples_by_origin': Counter(s['_origin'] for s in samples),
        'samples_in_misaligned_projects':
            sum(s['_misaligned_project'] for s in samples),
        'core_sources': {c: Counter(s[f'_source_{c}'] or 'none'
                                    for s in samples) for c in CORE_COLUMNS},
        'exclusions': Counter(e['reason'] for e in exclusions),
        'residual_artefacts': residual_artefacts(samples),
        'authorship': {
            'by_source': Counter(s['Authorship_source'] or 'none'
                                 for s in studies),
            'with_pmid': sum(1 for s in studies if s['PMID']),
            'pmid_by_source': Counter(s['PMID_source'] or 'none'
                                      for s in studies),
            'with_submitters': sum(1 for s in studies if s['Submitters']),
            'credited_to_institution': sum(
                1 for s in studies if not s['Authors'] and s['Institution']),
            'no_credit': sum(1 for s in studies if not s['Authors']
                             and not s['Institution']),
            'queue': Counter(r['reasons'] for r in authors_queue),
            'lookups': resolver.web.requests,
        },
        'review_queue': Counter(r['reasons'] for r in queue),
        'review_queue_by_origin': Counter(r['curated_before']
                                          for r in queue),
        'LIBRARYTYPE_by_origin': {
            g: Counter(s['LIBRARYTYPE'] or '(none)' for s in samples
                       if s['_origin_group'] == g).most_common(8)
            for g in ('current', 'oct_2024', 'new')},
        'report': {k: dict(v.most_common(60)) for k, v in b.report.items()},
        'study_notes': study_notes,
    }
    with open(args.out / 'summary.json', 'w') as fh:
        json.dump(summary, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ('report', 'study_notes')},
                     indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
