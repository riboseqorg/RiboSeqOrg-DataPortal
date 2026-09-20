"""
Turn raw SraRunInfo records into one value per portal column.

This replaces Metadata-Curation/metadata_cleanup_columns.R. That script joined
synonymous source columns with paste(sep = "_"), which writes a missing value
as "NA", and then tried to strip the NAs again with a regex. The regex cannot
undo the join, which is where the NA_x, xNA, x_x and glued "xy" values in the
portal came from. Here values are cleaned *before* they are combined, empty
values are dropped, repeats are removed, and distinct values are joined with
"; " so they stay readable.
"""
import csv
import re
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent / 'resources'

# Values meaning "no value". Compared case-insensitively after trimming.
# "0.0" and "NANA" are artefacts of the old pipeline, never real SRA values.
MISSING = {
    '', 'na', 'n/a', 'n.a.', 'nan', 'nana', 'none', 'null', 'missing',
    'not applicable', 'not available', 'not collected', 'not determined',
    'not provided', 'unknown', 'unspecified', '-', '--', '.', '?', '0.0',
    '<na>', 'restricted access', 'unclassified',
}

# Source columns the curation sheets map to the wrong portal column. They are
# dropped from the mapping (the values stay available as study OpenColumns).
MAPPING_EXCLUSIONS = {
    'TIMEPOINT': {'na constructs', 'triton addition', 'passages',
                  'activation stage', 'cell line source',
                  'harvest_condition'},
}

# SRA run-info fields, copied as-is (not merged from attributes).
RUNINFO_FIELDS = [
    'Run', 'spots', 'bases', 'avgLength', 'size_MB', 'Experiment',
    'LibraryName', 'LibraryStrategy', 'LibrarySelection', 'LibrarySource',
    'LibraryLayout', 'InsertSize', 'InsertDev', 'Platform', 'Model',
    'SRAStudy', 'BioProject', 'Study_Pubmed_id', 'ProjectID', 'Sample',
    'BioSample', 'SampleType', 'TaxID', 'ScientificName', 'SampleName',
    'CenterName', 'Submission', 'MONTH', 'YEAR', 'AUTHOR', 'sample_source',
    'sample_title', 'GEO', 'experiment_title', 'design_description',
    'library_construction_protocol',
]

# Same identifier columns metadata_cleanup_columns.R removed.
IDENTIFIER_COLUMNS = re.compile(
    r'^ENA |^ENA-|^INSDC |date|GEO Accession|Experiment Date')

WHITESPACE = re.compile(r'\s+')


def clean_value(value) -> str:
    """Trim, collapse whitespace, and map missing-value markers to ''."""
    if value is None:
        return ''
    value = WHITESPACE.sub(' ', str(value)).strip()
    return '' if value.casefold() in MISSING else value


def combine(values) -> str:
    """
    Combine values from several source columns into one field.

    Missing values are dropped and repeats removed (ignoring case), so
    'sty1delta' twice stays 'sty1delta', and two different values are kept
    apart as 'a; b' rather than glued together.
    """
    seen, out = set(), []
    for value in values:
        for part in str(value).split('; ') if value else ():
            part = clean_value(part)
            key = part.casefold()
            if part and key not in seen:
                seen.add(key)
                out.append(part)
    return '; '.join(out)


# --- column mapping (Core.csv / Open.csv / Technical.csv) -------------------

def _names(cell: str):
    """Parse a sheet cell like '"cell line", "cell_line"' into names."""
    return [n for n in re.findall(r'"([^"]*)"', cell or '') if n.strip()]


def load_mapping(resources: Path = RESOURCES):
    """
    Ordered list of (portal column, [source column names]).

    Order matters, as in the R script: a source column is used by the first
    rule that names it, so e.g. 'cell type' feeds CELL_LINE, not TISSUE.
    """
    rules = []
    with open(resources / 'Core.csv', newline='') as fh:
        for row in list(csv.reader(fh))[1:]:
            rules.append((row[1], _names(row[2]) + _names(row[3])))
    for sheet in ('Open.csv', 'Technical.csv'):
        with open(resources / sheet, newline='') as fh:
            for row in list(csv.reader(fh))[1:]:
                rules.append((row[0].strip(), _names(row[1])))
    fixed = []
    for target, sources in rules:
        drop = MAPPING_EXCLUSIONS.get(target, set())
        fixed.append((target, [s for s in sources if s not in drop]))
    return fixed


def load_irrelevant(resources: Path = RESOURCES):
    with open(resources / 'Irrelevant.csv', newline='') as fh:
        return {r['Delete'] for r in csv.DictReader(fh) if r.get('Delete')}


class Merger:
    """Apply the column mapping to one run's attributes."""

    def __init__(self, resources: Path = RESOURCES):
        self.rules = load_mapping(resources)
        self.irrelevant = load_irrelevant(resources)
        self.targets = []
        for target, _ in self.rules:
            if target not in self.targets:
                self.targets.append(target)

    def merge(self, attributes):
        """
        attributes: list of (source column, value), repeats allowed.
        Returns ({portal column: value}, {unmapped source column: value}).
        """
        remaining = {}
        for name, value in attributes:
            if name in RUNINFO_FIELDS:
                continue
            remaining.setdefault(name, []).append(value)
        merged = {t: '' for t in self.targets}
        for target, sources in self.rules:
            values = []
            for source in sources:
                if source in remaining:
                    values += remaining.pop(source)
            if values:
                merged[target] = combine([merged[target]] + values)
        unmapped = {
            k: combine(v) for k, v in remaining.items()
            if k not in self.irrelevant and not IDENTIFIER_COLUMNS.search(k)
            and combine(v)
        }
        return merged, unmapped


# --- ORFik findFromPath port -------------------------------------------------

def _patterns(cell: str):
    """
    Split a Content.csv 'All Names' cell into regexes. Leading/trailing
    spaces are significant (' rep 1 ', ' 1$'), so only one space after each
    comma is removed; doubled backslashes come from the CSV export.
    """
    out = []
    for p in re.split(r', ?', cell or ''):
        p = p.replace('\\\\', '\\')
        if p:
            try:
                out.append(re.compile(p))
            except re.error:
                out.append(re.compile(re.escape(p)))
    return out


class Vocabulary:
    """
    Controlled names for one column, matched the way ORFik's findFromPath
    does: case-sensitive regex search, and a value is only assigned when
    exactly one name's patterns match.
    """

    def __init__(self, entries):
        self.entries = [(name, pats) for name, pats in entries if pats]
        self.names = {name for name, _ in entries}

    def find(self, text: str) -> str:
        if not text:
            return ''
        hits = {name for name, pats in self.entries
                if any(p.search(text) for p in pats)}
        return hits.pop() if len(hits) == 1 else ''


def load_vocabularies(resources: Path = RESOURCES):
    """{(column, category): Vocabulary} from Content.csv."""
    groups = {}
    with open(resources / 'Content.csv', newline='') as fh:
        for row in csv.DictReader(fh):
            key = (row['Column'].strip(), row['Category'].strip())
            name = row['Main Name'].strip()
            if key[0] and name:
                groups.setdefault(key, []).append(
                    (name, _patterns(row['All Names'])))
    return {k: Vocabulary(v) for k, v in groups.items()}


# Which merged columns each core column is standardised from, before the
# sample description columns (metadata_standardize_column_values.R).
STANDARDISE_FROM = {
    'CELL_LINE': [('CELL_LINE', 'Cell Lines')],
    'TISSUE': [('TISSUE', 'Tissue'), ('TISSUE', 'convertToTissue')],
    'INHIBITOR': [('INHIBITOR', 'Inhibitor Name')],
    'TIMEPOINT': [('TIMEPOINT', 'Timepoint')],
    'FRACTION': [('FRACTION', 'Fraction Name')],
    'REPLICATE': [('REPLICATE', 'Replicate Names')],
    'CONDITION': [('CONDITION', 'Condition Name')],
    'LIBRARYTYPE': [('LIBRARYTYPE', 'Library Names')],
}
SOURCE_COLUMNS = {
    'CELL_LINE': ['CELL_LINE', 'TISSUE'],
    'TISSUE': ['CELL_LINE', 'TISSUE'],
}
INFO_COLUMNS = ['sample_title', 'Info', 'sample_source', 'LibraryName']


class Standardiser:
    """Automatic controlled value for a core column (the old *_st values)."""

    def __init__(self, resources: Path = RESOURCES):
        self.vocab = load_vocabularies(resources)

    def standardise(self, column: str, row: dict) -> str:
        texts = [row.get(c, '') for c in
                 SOURCE_COLUMNS.get(column, [column]) + INFO_COLUMNS]
        # Each vocabulary in turn fills what the previous one left empty.
        for key in STANDARDISE_FROM[column]:
            vocab = self.vocab.get(key)
            if vocab is None:
                continue
            for text in texts:
                hit = vocab.find(text)
                if hit and hit != 'NONE':  # ORFik's "no tissue" marker
                    return hit
        return ''
