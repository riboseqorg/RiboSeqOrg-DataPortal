import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .metadata_cleaning import Suggestion, merge, suggest
from .models import Sample


def by_value(column, counts):
    return {s.value: s for s in suggest(column, counts).suggestions}


class SuggestTests(SimpleTestCase):
    def test_missing_markers(self):
        found = by_value('INHIBITOR', {'0.0': 10, 'nan': 2, 'NANA': 1, '': 5})
        self.assertEqual(
            {v: (s.suggestion, s.rule) for v, s in found.items()},
            {'0.0': ('', 'missing_marker'), 'nan': ('', 'missing_marker'),
             'NANA': ('', 'missing_marker')},
        )
        self.assertEqual(found['0.0'].note, '')

    def test_zero_in_numeric_column_is_flagged_for_review(self):
        found = by_value('TIMEPOINT', {'0.0': 3})
        self.assertIn('confirm', found['0.0'].note)

    def test_spelling_variants_snap_to_most_common(self):
        found = by_value('CELL_LINE', {'HAP1': 9, 'hap1': 2, 'HeLa': 4})
        self.assertEqual(list(found), ['hap1'])
        self.assertEqual(found['hap1'].suggestion, 'HAP1')
        self.assertEqual(found['hap1'].rule, 'spelling_variant')

    def test_integer_float_variants(self):
        found = by_value('REPLICATE', {'1': 2, '1.0': 5, '2NA': 1})
        self.assertEqual(found['1.0'].suggestion, '1')
        self.assertEqual(found['2NA'].suggestion, '2')

    def test_whitespace(self):
        found = by_value('TISSUE', {'Liver ': 1, 'Liver': 3})
        self.assertEqual(found['Liver '].rule, 'whitespace')
        self.assertEqual(found['Liver '].suggestion, 'Liver')

    def test_na_prefix_snaps_to_existing_spelling(self):
        found = by_value('CELL_LINE', {'NA_yeast cell': 2, 'Yeast cell': 7})
        self.assertEqual(found['NA_yeast cell'].suggestion, 'Yeast cell')
        self.assertEqual(found['NA_yeast cell'].rule, 'na_prefix')

    def test_numeric_na_suffix_but_not_rna(self):
        found = by_value('TIMEPOINT', {'24NA': 1, 'mRNA': 1, 'tRNA': 1})
        self.assertEqual(list(found), ['24NA'])
        self.assertEqual(found['24NA'].suggestion, '24')

    def test_repairs_stack(self):
        found = by_value('Individual', {'NA_1NA': 4})
        self.assertEqual(found['NA_1NA'].suggestion, '1')
        self.assertEqual(found['NA_1NA'].rule, 'na_prefix+na_suffix')

    def test_duplicated_join(self):
        found = by_value('FRACTION', {'80s_80s': 3, 'Cytoplasmic': 1})
        self.assertEqual(found['80s_80s'].suggestion, '80s')

    def test_clean_values_are_left_alone(self):
        self.assertEqual(
            by_value('INHIBITOR', {'Cycloheximide': 5, 'Harringtonine': 2}),
            {},
        )


class MergeTests(SimpleTestCase):
    def test_curator_decisions_survive_rescan(self):
        edited = Suggestion('TISSUE', 'liver', 'Liver (edited)',
                            'spelling_variant', 1, 'mine', 'approved')
        gone = Suggestion('TISSUE', 'old', '', 'missing_marker', 4)
        fresh = [Suggestion('TISSUE', 'liver', 'Liver', 'spelling_variant', 6),
                 Suggestion('TISSUE', 'new', '', 'missing_marker', 1)]
        merged = {s.value: s for s in merge([edited, gone], fresh)}
        self.assertEqual(merged['liver'].suggestion, 'Liver (edited)')
        self.assertEqual(merged['liver'].status, 'approved')
        self.assertEqual(merged['liver'].rows, 6)
        self.assertEqual(merged['old'].rows, 0)
        self.assertEqual(merged['new'].status, 'proposed')


class CleanMetadataCommandTests(TestCase):
    def setUp(self):
        Sample.objects.create(Run='R1', INHIBITOR='0.0', TISSUE='liver')
        Sample.objects.create(Run='R2', INHIBITOR='Cycloheximide',
                              TISSUE='Liver')
        Sample.objects.create(Run='R3', INHIBITOR='Cycloheximide',
                              TISSUE='Liver')
        self.vocab = Path(tempfile.mkdtemp()) / 'vocab.csv'

    def run_command(self, *args):
        out = StringIO()
        call_command('clean_metadata', '--vocab', str(self.vocab),
                     '--columns', 'INHIBITOR', 'TISSUE', *args, stdout=out)
        return out.getvalue()

    def snapshot(self):
        return list(Sample.objects.order_by('Run')
                    .values_list('INHIBITOR', 'TISSUE'))

    def test_scan_writes_vocab_without_touching_db(self):
        before = self.snapshot()
        output = self.run_command()
        self.assertEqual(self.snapshot(), before)
        self.assertIn('No database changes made', output)
        with self.vocab.open() as handle:
            rows = {(r['column'], r['value']): r for r in csv.DictReader(handle)}
        self.assertEqual(rows[('INHIBITOR', '0.0')]['status'], 'proposed')
        self.assertEqual(rows[('TISSUE', 'liver')]['suggestion'], 'Liver')

    def test_apply_only_changes_approved_rows(self):
        self.run_command()
        with self.vocab.open() as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row['value'] == 'liver':
                row['status'] = 'approved'
        with self.vocab.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        self.run_command('--apply')
        self.assertEqual(self.snapshot(), [
            ('0.0', 'Liver'),
            ('Cycloheximide', 'Liver'),
            ('Cycloheximide', 'Liver'),
        ])
