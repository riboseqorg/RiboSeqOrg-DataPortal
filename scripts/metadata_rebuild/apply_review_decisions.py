"""
Apply curator decisions on the review queue to a finished rebuild.

    python -m scripts.metadata_rebuild.apply_review_decisions OUT_DIR          # dry run
    python -m scripts.metadata_rebuild.apply_review_decisions OUT_DIR --apply

OUT_DIR is a pipeline output directory (holds db.sqlite3, samples.csv and, for
a release build, RiboSeqOrg_Metadata_v*.csv). Decisions come from
inputs/review_decisions_2026-09.csv (Run, BioProject, LIBRARYTYPE); a
LIBRARYTYPE of EXCLUDE removes the run. Run it after the build is verified
and before --install.
"""
import argparse
import csv
import shutil
import sqlite3
import sys
from pathlib import Path

DECISIONS = Path(__file__).parent / 'inputs' / 'review_decisions_2026-09.csv'


def read_csv(path):
    with open(path, newline='') as fh:
        rd = csv.DictReader(fh)
        return list(rd), rd.fieldnames


def write_csv(path, rows, fields):
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def patch_db(db, decisions, apply):
    con = sqlite3.connect(db)
    changes, missing, links = [], [], 0
    for run, (bp, label) in decisions.items():
        row = con.execute('select LIBRARYTYPE, BioProject_id from main_sample '
                          'where Run=?', (run,)).fetchone()
        if row is None:
            missing.append(run)
            continue
        changes.append((run, bp, row[0], label))
        if not apply:
            continue
        if label == 'EXCLUDE':
            con.execute('delete from main_sample where Run=?', (run,))
            for t in ('main_trips', 'main_ribocrypt'):
                links += con.execute(f'delete from {t} where Run=?',
                                     (run,)).rowcount
        else:
            con.execute('update main_sample set LIBRARYTYPE=? where Run=?',
                        (label, run))
    if apply:
        for bp in {c[1] for c in changes}:
            types = [r[0] for r in con.execute(
                'select distinct LIBRARYTYPE from main_sample '
                "where BioProject_id=? and LIBRARYTYPE is not null "
                "and LIBRARYTYPE!=''", (bp,))]
            n = con.execute('select count(*) from main_sample '
                            'where BioProject_id=?', (bp,)).fetchone()[0]
            con.execute('update main_study set seq_types=?, Samples=? '
                        'where BioProject=?', (';'.join(sorted(types)), n, bp))
        con.commit()
    con.close()
    return changes, missing, links


def patch_csv(path, decisions, apply):
    rows, fields = read_csv(path)
    out = []
    for r in rows:
        d = decisions.get(r['Run'])
        if d and d[1] == 'EXCLUDE':
            continue
        if d:
            r['LIBRARYTYPE'] = d[1]
            if '_source_LIBRARYTYPE' in r:
                r['_source_LIBRARYTYPE'] = 'review'
        out.append(r)
    if apply:
        write_csv(path, out, fields)
    return len(rows), len(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('out', type=Path)
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    decisions = {r['Run']: (r['BioProject'], r['LIBRARYTYPE'])
                 for r in read_csv(DECISIONS)[0]}
    db = a.out / 'db.sqlite3'
    if a.apply:
        shutil.copy(db, a.out / 'db.sqlite3.pre-review-decisions')
    changes, missing, links = patch_db(
        db, {k: (v[0], v[1]) for k, v in decisions.items()}, a.apply)
    for run, bp, old, new in changes:
        print(f'{run}\t{bp}\t{old or "(none)"} -> {new}')
    print(f'{len(changes)} runs found, {len(missing)} not in this build, '
          f'{links} link rows removed')
    if missing:
        print('missing:', ' '.join(missing))
    for f in ['samples.csv', *[p.name for p in a.out.glob(
            'RiboSeqOrg_Metadata_v*.csv')]]:
        if (a.out / f).exists():
            before, after = patch_csv(a.out / f, {k: (v[0], v[1]) for k, v in decisions.items()}, a.apply)
            print(f'{f}: {before} -> {after} rows')
    print('applied' if a.apply else 'dry run; pass --apply to write')
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
