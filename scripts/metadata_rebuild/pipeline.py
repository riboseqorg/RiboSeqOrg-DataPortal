"""
Rebuild the portal database end to end.

    python -m metadata_rebuild.pipeline               # fetch, build, verify
    python -m metadata_rebuild.pipeline --install     # ... and install it
    python -m metadata_rebuild.pipeline --skip-fetch  # reuse the SRA cache
    python -m metadata_rebuild.pipeline --install-only  # verify + install, no rebuild

Steps:
  baseline  extract the October 2024 database from git (the last load before
            the November 2024 regression), used as a value source
  fetch     download SRA records for every Ribo-seq BioProject (incremental:
            projects already in the cache are skipped)
  build     write the new database and reports under build/metadata_rebuild
  verify    unit tests, then checks on the built database
  install   back up the live database and put the new one in its place

Everything except `install` leaves the live database untouched.

`--install` rebuilds first, so it discards anything applied to the built
database after the build - the curator decisions from
apply_review_decisions.py, above all. Use `--install-only` to verify and
install what is already in the output directory.
"""
import argparse
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from datetime import date
from pathlib import Path

from .authorship import shared_author_strings
from .build import DEFAULT_OUT, INPUTS, REPO
from .build import main as build_main
from .fetch import main as fetch_main

# The last database load before the November 2024 regression.
BASELINE_COMMIT = 'edff627d'
LIVE_DB = REPO / 'riboseqorg' / 'db.sqlite3'


def log(step, message):
    print(f'[{step}] {message}', flush=True)


def step_baseline(out: Path) -> Path:
    path = out / 'db_2024-10.sqlite3'
    if path.exists():
        log('baseline', f'{path} exists')
        return path
    out.mkdir(parents=True, exist_ok=True)
    log('baseline', f'extracting {BASELINE_COMMIT}:riboseqorg/db.sqlite3')
    with open(path, 'wb') as fh:
        subprocess.run(
            ['git', 'show', f'{BASELINE_COMMIT}:riboseqorg/db.sqlite3'],
            cwd=REPO, stdout=fh, check=True)
    return path


def step_fetch(cache: Path, workers: int, api_key=None):
    cache.mkdir(parents=True, exist_ok=True)
    argv = ['--existing', str(cache), '--out', str(cache),
            '--whitelist', str(INPUTS / 'whitelisted_bioprojects.csv.gz'),
            '--workers', str(workers)]
    if api_key:
        argv += ['--api-key', api_key]
    fetch_main(argv)


def step_build(out: Path, baseline: Path, cache: Path, release, offline,
               api_key=None):
    argv = ['--sra-cache', str(cache), '--baseline-db', str(baseline),
            '--out', str(out / 'output')]
    if release:
        argv += ['--release', release]
    if offline:
        argv += ['--offline']
    if api_key:
        argv += ['--api-key', api_key]
    build_main(argv)


def step_verify(out: Path, live: Path):
    """Unit tests, then sanity checks on the built database."""
    from . import test_metadata_rebuild
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        test_metadata_rebuild)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    problems = [] if result.wasSuccessful() else \
        [f'{len(result.failures) + len(result.errors)} unit tests failed']

    db = out / 'output' / 'db.sqlite3'
    con = sqlite3.connect(db)
    samples, studies = (con.execute(f'select count(*) from {t}').fetchone()[0]
                        for t in ('main_sample', 'main_study'))
    checks = {
        'orphan samples': con.execute(
            'select count(*) from main_sample s left join main_study t on '
            's.BioProject_id = t.BioProject where t.BioProject is null'
        ).fetchone()[0],
        'placeholder values': con.execute(
            "select count(*) from main_sample where CELL_LINE in "
            "('0.0','<NA>','nan') or CONDITION = 'Test' or "
            "Study_Pubmed_id in ('<NA>','1') or AUTHOR = 'Makar'"
        ).fetchone()[0],
        'NA artefacts': con.execute(
            r"select count(*) from main_sample where TIMEPOINT like 'NA#_%' "
            r"escape '#' or REPLICATE like '%NA' or CELL_LINE like 'NA#_%' "
            r"escape '#'").fetchone()[0],
        'integrity_check': 0 if con.execute(
            'pragma integrity_check').fetchone()[0] == 'ok' else 1,
        # A paper with neither a PMID nor a DOI is a paper nothing can be
        # checked against: that is the shape the contaminated rows had. A
        # preprint carries a DOI instead of a PMID and is legitimate.
        'papers with no identifier': con.execute(
            "select count(*) from main_study where PMID = '' and doi = '' "
            "and (Authors != '' or Publication_title != '')").fetchone()[0],
        'authors with no recorded source': con.execute(
            "select count(*) from main_study where Authors != '' and "
            "Authorship_source = ''").fetchone()[0],
    }
    shared = shared_author_strings(
        [{'Authors': a, 'PMID': p, 'BioProject': b} for a, p, b in
         con.execute('select Authors, PMID, BioProject from main_study')])
    con.close()
    if shared:
        worst = max(shared.items(), key=lambda kv: len(kv[1]))
        checks[f'author list shared by unrelated papers '
               f'({worst[0][:40]!r})'] = len(worst[1])
    for name, count in checks.items():
        if count:
            problems.append(f'{name}: {count}')
    if live.exists():
        con = sqlite3.connect(live)
        before = con.execute('select count(*) from main_sample').fetchone()[0]
        con.close()
        log('verify', f'samples: {before} live -> {samples} new')
        if samples < before * 0.9:
            problems.append(f'sample count dropped from {before} to {samples}')
        # A jump is as suspicious as a drop: it means the selection rules
        # let something new in (they once matched 'Ribo-Zero' in a library
        # protocol and pulled in whole RNA-seq studies).
        if samples > before * 1.25:
            problems.append(f'sample count jumped from {before} to {samples}; '
                            'check what selection let in')
    log('verify', f'{samples} samples, {studies} studies, '
                  f'{len(problems)} problems')
    for problem in problems:
        log('verify', f'PROBLEM: {problem}')
    return problems


def step_install(out: Path, live: Path):
    backup = live.parent.parent / 'build' / 'metadata_rebuild' / \
        f'db.sqlite3.backup-{date.today()}-{int(time.time())}'
    shutil.copy2(live, backup)
    shutil.copy(out / 'output' / 'db.sqlite3', live)
    log('install', f'backed up to {backup}')
    log('install', f'installed {live}')
    log('install', 'run `python manage.py migrate` in riboseqorg/')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--out', type=Path, default=DEFAULT_OUT)
    p.add_argument('--cache', type=Path,
                   help='SRA cache (default: <out>/sra_cache)')
    p.add_argument('--skip-fetch', action='store_true')
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--api-key', help='NCBI API key: 3x the request rate')
    p.add_argument('--release', default=date.today().strftime('%Y.%m'),
                   help='Version for the release CSV, e.g. 2026.09')
    p.add_argument('--offline', action='store_true',
                   help='Skip PubMed/BioProject lookups for study details')
    p.add_argument('--install', action='store_true',
                   help='Rebuild, then install the result as the live database')
    p.add_argument('--install-only', action='store_true',
                   help='Verify and install the existing build without '
                        'rebuilding it, keeping any patches applied to it')
    p.add_argument('--live-db', type=Path, default=LIVE_DB)
    args = p.parse_args(argv)
    cache = args.cache or args.out / 'sra_cache'

    started = time.time()
    install = args.install or args.install_only
    if args.install_only:
        # Verify and install what is already there. Rebuilding would throw
        # away the review decisions patched in after the build.
        log('build', f'skipped; installing {args.out / "output"} as built')
    else:
        baseline = step_baseline(args.out)
        if args.skip_fetch:
            log('fetch', f'skipped; using {cache}')
        else:
            step_fetch(cache, args.workers, args.api_key)
        step_build(args.out, baseline, cache, args.release, args.offline,
                   args.api_key)
    problems = step_verify(args.out, args.live_db)
    if problems and install:
        log('install', 'skipped: verification found problems')
        return 1
    if install:
        step_install(args.out, args.live_db)
    log('done', f'{time.time() - started:.0f}s; reports in '
                f'{args.out / "output"}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
