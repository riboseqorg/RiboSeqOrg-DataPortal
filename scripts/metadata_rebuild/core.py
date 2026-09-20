"""
Choose the value of each curated core column from the available sources.

Sources, per run:
  manual    human-checked rows of the RiboCrypt curation sheet (CHECKED set
            to a curator's name)
  baseline  the October 2024 portal database, the last load before the
            November 2024 regression (see audit/metadata-audit.md)
  st        the Metadata-Curation pipeline's standardised (_st) values
  auto      the same standardisation run on freshly fetched SRA records

Every candidate is mapped to its display name and validated; the first valid
one wins, and which source it came from is recorded so it can be reviewed.
"""
import csv
import re
from pathlib import Path

from .merge import RESOURCES, clean_value

CORE_COLUMNS = ['LIBRARYTYPE', 'REPLICATE', 'CONDITION', 'INHIBITOR',
                'TIMEPOINT', 'TISSUE', 'CELL_LINE', 'FRACTION']

DEFAULT_ORDER = ['manual', 'baseline', 'st', 'auto']
ORDER = {
    # SRA's own 'Ribo-seq' library strategy (in use since ~2024) is the last
    # resort: curators relabelled 24 of the 438 such runs they checked.
    # 'assay' = the broader rules in assay.py from the run's own text (98.5%
    # agreement with curators); 'assay_study' = inferred from the study text
    # only (~93.5%), so it comes last and goes to the review queue.
    'LIBRARYTYPE': ['manual', 'baseline', 'st', 'auto', 'assay', 'strategy',
                    'assay_study'],
    # Curators used REPLICATE for their own grouping: where they disagree with
    # the baseline and the title names a replicate, the title backs the
    # baseline 248 times to 4. So the manual sheet is the last resort here.
    'REPLICATE': ['baseline', 'st', 'auto', 'manual'],
}
# Projects whose historical attribute columns were misaligned (ORFik
# rich.format bug): baseline and st were derived from shifted attributes, so
# the freshly derived value is trusted before them.
MISALIGNED_ORDER = ['manual', 'auto', 'assay', 'baseline', 'st',
                    'strategy', 'assay_study']
MISALIGNED_ORDER_REPLICATE = ['auto', 'baseline', 'st', 'manual']

# Placeholders that were never real values.
PLACEHOLDERS = {
    'CONDITION': {'test'},  # Nov 2024 load filled blanks with "Test"
    'CELL_LINE': {'none'},
    'TISSUE': {'none'},
}

# Strains that ended up in CELL_LINE. They move to Strain when it's empty.
STRAINS = re.compile(
    r'^(C57B[lL][/_ ]?6\w*|BY474[1-3]|S288C|SK1|W303\S*|BALB/c|CD-1)$')

# Leftovers of the old paste(sep = "_") + regex step.
ARTEFACT = re.compile(
    r'^NA_|_NA_|_NA$|NANA|(?<=[a-z0-9)])NA$|^NA(?=[a-z0-9])|_time point')
# Repairs for those leftovers where the real value is still recoverable:
# 'NA2hr' -> '2hr', 'CT00NA' -> 'CT00', 'stationary_NA' -> 'stationary'.
# 'NA' next to a capital letter is left alone (mRNA, NAT10).
NA_PREFIX = re.compile(r'^(?:NA_?)+(?=[a-z0-9_ ]|$)')
NA_SUFFIX = re.compile(r'(?<=[a-z0-9)_ ])(?:NA)+$')

LIBRARYTYPE_VOCAB = {
    'Ribo-Seq', 'RNA-Seq', 'RMS', 'LSU', 'SSU', 'RiboTag', 'RiboMeth',
    'RIP', 'tRNA', 'QTI-Seq', 'CLIP', 'CAGE-Seq', 'CRAC', 'TRAP',
    'miRNA-Seq', 'Disome-Seq', 'ATAC-Seq', 'ChIP-Seq', 'GRO-Seq',
    'PAL-Seq', 'PAS-Seq', 'PRPF', 'SHAPE',
    # from assay.py
    'Ribo-tRNA-Seq', 'tRNA-Seq', 'Mito-Ribo-Seq', 'Polysome-Seq', 'RMS',
    'Selective Ribo-Seq',
}
# Cellular fractions, plus the treatments ORFik's fraction slot has always
# carried (Content.csv); anything else is not a fraction.
FRACTION_VOCAB = {
    'Cytoplasmic', 'Nuclear', 'Mitochondrial', 'Endoplasmic reticulum',
    'Membrane', 'Monosome', 'Disome', 'Polysome', 'DMSO', 'Auxin',
    'Thapsigargin', 'Silvestrol', 'Fasting', 'DTT',
}
STRICT = {'LIBRARYTYPE': LIBRARYTYPE_VOCAB, 'FRACTION': FRACTION_VOCAB}

REPLICATE_WORDS = re.compile(
    r'^(?:(?:bio(?:logical)?|tech(?:nical)?)?\s*(?:rep(?:licate)?)?\s*[_#-]?'
    r'\s*)(\d{1,2})(?:\s*(?:bio(?:logical)?\s*)?(?:rep(?:licate)?)?)?$',
    re.IGNORECASE)


def load_display_names(resources: Path = RESOURCES):
    """{column: {value: display}} from display_names.csv."""
    out = {}
    with open(resources / 'display_names.csv', newline='') as fh:
        for row in csv.DictReader(fh):
            out.setdefault(row['column'], {})[row['value']] = row['display']
    return out


def repair(value: str) -> str:
    """Undo the old pipeline's NA joins and 'x_x' repeats, if possible."""
    for _ in range(3):
        before = value
        value = NA_SUFFIX.sub('', NA_PREFIX.sub('', value))
        value = value.strip('_ ')
        parts = value.split('_')
        if len(parts) > 1 and len({re.sub(r'\.0$', '', p).casefold()
                                   for p in parts}) == 1:
            value = parts[0]
        if value == before:
            break
    return clean_value(value)


def normalise_replicate(value: str) -> str:
    """'1.0', 'Rep 2', 'biological 3', '2biological replicate' -> digits."""
    value = re.sub(r'^(\d+)\.0$', r'\1', value.strip())
    match = REPLICATE_WORDS.match(value)
    if match and 0 < int(match.group(1)) <= 50:
        return str(int(match.group(1)))
    return ''


class CoreResolver:

    def __init__(self, resources: Path = RESOURCES):
        self.display = load_display_names(resources)
        self.lower_display = {
            col: {k.casefold(): v for k, v in m.items()}
            for col, m in self.display.items()
        }

    def to_display(self, column: str, value: str) -> str:
        value = clean_value(value)
        if not value:
            return ''
        exact = self.display.get(column, {}).get(value)
        if exact:
            return exact
        return self.lower_display.get(column, {}).get(value.casefold(), value)

    def validate(self, column: str, value: str) -> str:
        """Return the cleaned display value, or '' if it isn't acceptable."""
        value = self.to_display(column, repair(clean_value(value)))
        if not value or ARTEFACT.search(value):
            return ''
        if value.casefold() in PLACEHOLDERS.get(column, set()):
            return ''
        if column == 'REPLICATE':
            return normalise_replicate(value)
        if column == 'CELL_LINE' and STRAINS.match(value):
            return ''
        if column in STRICT and value not in STRICT[column]:
            return ''
        return value

    def resolve(self, column: str, candidates: dict, misaligned=False):
        """
        candidates: {source: raw value}. Returns (value, source, rejected)
        where rejected lists (source, value) candidates that failed checks.
        """
        if misaligned:
            order = MISALIGNED_ORDER_REPLICATE if column == 'REPLICATE' \
                else MISALIGNED_ORDER
        else:
            order = ORDER.get(column, DEFAULT_ORDER)
        rejected = []
        for source in order:
            raw = clean_value(candidates.get(source, ''))
            if not raw:
                continue
            value = self.validate(column, raw)
            if value:
                return value, source, rejected
            rejected.append((source, raw))
        return '', '', rejected

    @staticmethod
    def strain_from_cell_line(values) -> str:
        """A strain name found among CELL_LINE candidates, if any."""
        for value in values:
            value = clean_value(value)
            if value and STRAINS.match(value):
                return value
        return ''
