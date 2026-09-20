"""
Detect likely problems in curated Sample metadata and propose fixes.

Nothing here writes to the database. `suggest()` turns the distinct values of
each curated column into proposals, which the `clean_metadata` management
command merges into a reviewable vocabulary CSV. Only rows a curator marks
as `approved` in that file are ever applied (with `--apply`).
"""
import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VOCABULARY_PATH = Path(__file__).resolve().parent / 'metadata_vocabulary.csv'
VOCABULARY_FIELDS = [
    'column', 'value', 'suggestion', 'rule', 'rows', 'status', 'note'
]
STATUSES = {'proposed', 'approved', 'rejected'}

# Manually curated columns (all-caps + curated extras). SRA run-info columns
# are left alone as they are copied verbatim from the archive.
CURATED_COLUMNS = [
    'LIBRARYTYPE', 'REPLICATE', 'CONDITION', 'INHIBITOR', 'BATCH',
    'TIMEPOINT', 'TISSUE', 'CELL_LINE', 'FRACTION', 'STAGE', 'GENE', 'Sex',
    'Strain', 'Age', 'Infected', 'Disease', 'Genotype', 'Feeding',
    'Temperature', 'SiRNA', 'SgRNA', 'ShRNA', 'Plasmid', 'Growth_Condition',
    'Stress', 'Cancer', 'microRNA', 'Individual', 'Antibody', 'Ethnicity',
    'Dose', 'Stimulation', 'Host', 'UMI', 'Adapter', 'Separation',
    'rRNA_depletion', 'Barcode', 'Monosome_purification', 'Nuclease', 'Kit',
]

# Columns where a literal zero could be a real measurement.
NUMERIC_COLUMNS = {'REPLICATE', 'TIMEPOINT', 'Dose', 'Temperature', 'Age'}

MISSING_MARKERS = {'0.0', 'nan', 'none', 'na', 'nana', 'n/a', 'null'}
NA_PREFIX = re.compile(r'^na_(.+)$', re.IGNORECASE)
NUMERIC_NA_SUFFIX = re.compile(r'^(\d+(?:\.\d+)?)NA$')
INTEGER_FLOAT = re.compile(r'^(\d+)\.0$')


@dataclass
class Suggestion:
    column: str
    value: str
    suggestion: str
    rule: str
    rows: int
    note: str = ''
    status: str = 'proposed'

    def key(self) -> Tuple[str, str]:
        return (self.column, self.value)


@dataclass
class ColumnReport:
    column: str
    distinct: int = 0
    rows: int = 0
    missing_rows: int = 0
    suggestions: List[Suggestion] = field(default_factory=list)


def normalise_key(value: str) -> str:
    """Key under which spelling variants of the same value collide."""
    key = ' '.join(value.split()).casefold()
    match = INTEGER_FLOAT.match(key)
    return match.group(1) if match else key


def canonical_forms(counts: Dict[str, int]) -> Dict[str, str]:
    """
    Map each variant key to its most common spelling. Ties go to the
    spelling that sorts first, so output is deterministic.
    """
    groups: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    for value, n in counts.items():
        if value.strip().casefold() in MISSING_MARKERS or not value.strip():
            continue
        groups[normalise_key(value)].append((value, n))
    canonical = {}
    for key, variants in groups.items():
        best = sorted(variants, key=lambda v: (-v[1], v[0]))[0][0]
        # Prefer '1' over '1.0': the float form is a pandas artefact.
        canonical[key] = key if INTEGER_FLOAT.match(best) else \
            ' '.join(best.split())
    return canonical


def _suggest_value(
        column: str, value: str, canonical: Dict[str, str]
        ) -> Optional[Tuple[str, str, str]]:
    """Return (suggestion, rule, note) for one value, or None if it's fine."""
    stripped = value.strip()

    if stripped.casefold() in MISSING_MARKERS:
        note = ''
        if column in NUMERIC_COLUMNS and stripped == '0.0':
            note = 'Numeric column: confirm 0.0 is not a real measurement.'
        return '', 'missing_marker', note

    # Repairs for values glued together by an earlier join step; they can
    # stack, e.g. 'NA_1NA' -> '1'.
    rules, notes, candidate = [], [], stripped
    na_prefix = NA_PREFIX.match(candidate)
    if na_prefix:
        candidate = na_prefix.group(1).strip()
        rules.append('na_prefix')
        notes.append("Looks like 'NA' joined to a value with '_'; "
                     "confirm what the prefix meant.")
    numeric_na = NUMERIC_NA_SUFFIX.match(candidate)
    if numeric_na:
        candidate = numeric_na.group(1)
        rules.append('na_suffix')
        notes.append("Looks like a value with 'NA' appended.")
    parts = candidate.split('_')
    if len(parts) > 1 and len({normalise_key(p) for p in parts}) == 1:
        candidate = parts[0].strip()
        rules.append('duplicated_join')
    rule, note = '+'.join(rules) or None, ' '.join(notes)

    # Snap to the most common spelling of the (possibly repaired) value.
    snapped = canonical.get(normalise_key(candidate), candidate)
    if rule is None:
        if snapped == value:
            return None
        rule = 'spelling_variant' if snapped != ' '.join(value.split()) \
            else 'whitespace'
        if rule == 'spelling_variant':
            note = f"Other spellings of this value exist; suggest '{snapped}'."
    return snapped, rule, note


def suggest(column: str, counts: Dict[str, int]) -> ColumnReport:
    """
    Build suggestions for one column from a {value: row_count} mapping.
    """
    canonical = canonical_forms(counts)
    report = ColumnReport(
        column=column, distinct=len(counts), rows=sum(counts.values())
    )
    for value, n in sorted(counts.items()):
        if value == '':
            report.missing_rows += n
            continue
        result = _suggest_value(column, value, canonical)
        if result is None:
            continue
        suggestion, rule, note = result
        if rule == 'missing_marker':
            report.missing_rows += n
        report.suggestions.append(
            Suggestion(column, value, suggestion, rule, n, note)
        )
    return report


def read_vocabulary(path: Path) -> List[Suggestion]:
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        rows = []
        for row in csv.DictReader(handle):
            status = (row.get('status') or 'proposed').strip().lower()
            if status not in STATUSES:
                raise ValueError(
                    f"Unknown status '{row.get('status')}' for "
                    f"{row['column']}={row['value']!r} in {path}"
                )
            rows.append(Suggestion(
                column=row['column'],
                value=row['value'],
                suggestion=row['suggestion'],
                rule=row['rule'],
                rows=int(row['rows'] or 0),
                note=row.get('note', ''),
                status=status,
            ))
        return rows


def write_vocabulary(path: Path, rows: Iterable[Suggestion]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=VOCABULARY_FIELDS)
        writer.writeheader()
        for s in sorted(rows, key=lambda s: (s.column, s.rule, s.value)):
            writer.writerow({
                'column': s.column, 'value': s.value,
                'suggestion': s.suggestion, 'rule': s.rule, 'rows': s.rows,
                'status': s.status, 'note': s.note,
            })


def merge(
        existing: List[Suggestion], detected: List[Suggestion]
        ) -> List[Suggestion]:
    """
    Combine curator-edited rows with fresh detections. Curator decisions
    (status, suggestion, note) always win; row counts are refreshed, and
    rows whose value no longer occurs keep their entry with rows=0.
    """
    current = {s.key(): s for s in detected}
    merged = {}
    for s in existing:
        fresh = current.get(s.key())
        s.rows = fresh.rows if fresh else 0
        merged[s.key()] = s
    for key, s in current.items():
        merged.setdefault(key, s)
    return list(merged.values())
