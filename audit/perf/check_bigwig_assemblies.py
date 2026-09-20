"""
Check that each organism's bigWigs match the assembly used for its genome
browser links (main/genome_tracks.py GENOME_ASSEMBLIES).

For each organism, reads the chromosome names and sizes from one run's
forward bigWig and compares them with the assembly's chrom.sizes. Needs
`bigWigInfo` (UCSC tools) on PATH. Run from riboseqorg/ on the server:

    python ../audit/perf/check_bigwig_assemblies.py

Links open GWIPS-viz. Where the assembly is also a standard UCSC one (hg38,
mm10, ...), chrom.sizes is downloaded from hgdownload.soe.ucsc.edu. Other
assemblies are reported with their chromosome names for a manual check (or
pass --gwips-sizes DIR containing <db>.chrom.sizes files).
"""
import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "riboseqorg.settings")
import django  # noqa: E402
django.setup()

from main.datafiles import find_run_file  # noqa: E402
from main.genome_tracks import GENOME_ASSEMBLIES  # noqa: E402
from main.models import Sample  # noqa: E402
from django.conf import settings  # noqa: E402


def bigwig_chroms(path):
    out = subprocess.run(['bigWigInfo', '-chroms', path], capture_output=True,
                         text=True, check=True).stdout
    chroms, in_list = {}, False
    for line in out.splitlines():
        if line.startswith('chromCount'):
            in_list = True
            continue
        if in_list and line.startswith('\t'):
            name, _, size = line.split()
            chroms[name] = int(size)
        elif in_list:
            break
    return chroms


def ucsc_sizes(db):
    '''
    chrom.sizes for a standard UCSC assembly, or None if UCSC doesn't have it.
    '''
    url = f'https://hgdownload.soe.ucsc.edu/goldenPath/{db}/bigZips/{db}.chrom.sizes'
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return {n: int(s) for n, s in
                    (line.split('\t') for line in r.read().decode().splitlines() if line)}
    except urllib.error.HTTPError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gwips-sizes', help='directory of <db>.chrom.sizes files')
    args = parser.parse_args()

    for organism, (browser, db) in GENOME_ASSEMBLIES.items():
        path = None
        for run in Sample.objects.filter(ScientificName=organism).values_list('Run', flat=True):
            rel = find_run_file('bigwig', run, ['.forward.bw', '_1.forward.bw'])
            if rel:
                path = os.path.join(settings.RIBOSEQORG_DATA_DIR, rel)
                break
        if not path:
            print(f'{organism:30s} {db:28s} NO BIGWIG FOUND')
            continue
        chroms = bigwig_chroms(path)
        sizes = ucsc_sizes(db)
        local = args.gwips_sizes and os.path.join(args.gwips_sizes, f'{db}.chrom.sizes')
        if not sizes and local and os.path.exists(local):
            with open(local) as f:
                sizes = {n: int(s) for n, s in (line.split()[:2] for line in f if line.strip())}
        if not sizes:
            print(f'{organism:30s} {db:28s} CHECK BY HAND  {os.path.basename(path)} '
                  f'chroms: {", ".join(f"{c}={s}" for c, s in list(chroms.items())[:6])}')
            continue
        matching = [c for c, s in chroms.items() if sizes.get(c) == s]
        wrong = [c for c, s in chroms.items() if c in sizes and sizes[c] != s]
        unknown = [c for c in chroms if c not in sizes]
        verdict = 'OK' if matching and not wrong and not unknown else 'MISMATCH'
        print(f'{organism:30s} {db:28s} {verdict:8s} {len(matching)} chroms match, '
              f'{len(wrong)} wrong size, {len(unknown)} unknown names '
              f'{unknown[:4] if unknown else ""} ({os.path.basename(path)})')


if __name__ == '__main__':
    main()
