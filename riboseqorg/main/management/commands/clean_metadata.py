from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from main.metadata_cleaning import (CURATED_COLUMNS, VOCABULARY_PATH, merge,
                                    read_vocabulary, suggest,
                                    write_vocabulary)
from main.models import Sample


class Command(BaseCommand):
    help = (
        "Scan curated Sample metadata and write suggested fixes to a "
        "vocabulary CSV for review. The database is only modified with "
        "--apply, and then only for rows marked 'approved'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--vocab', type=Path, default=VOCABULARY_PATH,
            help=f"Vocabulary CSV (default: {VOCABULARY_PATH})",
        )
        parser.add_argument(
            '--columns', nargs='+', choices=CURATED_COLUMNS,
            default=CURATED_COLUMNS, metavar='COLUMN',
            help="Limit the scan to these columns.",
        )
        parser.add_argument(
            '--apply', action='store_true',
            help="Apply rows with status 'approved' to the database.",
        )

    def handle(self, *args, **options):
        if options['apply']:
            self.apply(options['vocab'])
        else:
            self.scan(options['vocab'], options['columns'])

    def scan(self, vocab: Path, columns):
        detected, empty_columns = [], []
        by_rule = Counter()
        rows_by_rule = Counter()
        for column in columns:
            counts = {
                row[column]: row['n'] for row in
                Sample.objects.values(column).annotate(n=Count('id'))
            }
            report = suggest(column, counts)
            if report.missing_rows == report.rows:
                empty_columns.append(column)
            for s in report.suggestions:
                by_rule[s.rule] += 1
                rows_by_rule[s.rule] += s.rows
            detected.extend(report.suggestions)

        existing = read_vocabulary(vocab)
        merged = merge(existing, detected)
        write_vocabulary(vocab, merged)

        new = len({s.key() for s in merged} - {s.key() for s in existing})
        self.stdout.write(f"Wrote {len(merged)} entries to {vocab} "
                          f"({new} new). No database changes made.\n")
        self.stdout.write(f"{'rule':<18}{'values':>8}{'rows':>10}")
        for rule, n in by_rule.most_common():
            self.stdout.write(f"{rule:<18}{n:>8}{rows_by_rule[rule]:>10}")
        if empty_columns:
            self.stdout.write(
                "\nColumns with no values at all: " + ', '.join(empty_columns)
            )

    def apply(self, vocab: Path):
        if not vocab.exists():
            raise CommandError(f"{vocab} does not exist; run without --apply "
                               "first to generate it.")
        approved = [s for s in read_vocabulary(vocab)
                    if s.status == 'approved']
        if not approved:
            self.stdout.write("No approved entries; nothing to apply.")
            return
        unknown = {s.column for s in approved} - set(CURATED_COLUMNS)
        if unknown:
            raise CommandError(f"Not curated columns: {', '.join(unknown)}")

        total = 0
        with transaction.atomic():
            for s in approved:
                updated = Sample.objects.filter(**{s.column: s.value}).update(
                    **{s.column: s.suggestion}
                )
                total += updated
                self.stdout.write(
                    f"{s.column}: {s.value!r} -> {s.suggestion!r} "
                    f"({updated} rows)"
                )
        self.stdout.write(f"Applied {len(approved)} entries, "
                          f"{total} rows updated.")
