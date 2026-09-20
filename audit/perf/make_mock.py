"""
Fill the Trips/GWIPS/RiboCrypt tables of a scratch DB copy with synthetic rows
that agree with the Sample availability flags. For local perf testing only.

Usage: python make_mock.py path/to/copy.sqlite3
"""
import sqlite3
import sys
from collections import defaultdict

GWIPS_DB = {'Homo sapiens': 'hg38', 'Mus musculus': 'mm10',
            'Saccharomyces cerevisiae': 'sacCer3'}
TRIPS_TX = {'Homo sapiens': 'gencode_v25', 'Mus musculus': 'gencode_m14'}

con = sqlite3.connect(sys.argv[1])
cur = con.cursor()
for t in ('main_trips', 'main_gwips', 'main_ribocrypt'):
    cur.execute(f'DELETE FROM {t}')

rows = cur.execute(
    'SELECT Run, BioProject_id, ScientificName, trips_id, gwips_id, ribocrypt_id '
    'FROM main_sample').fetchall()

trips, ribocrypt = [], []
gwips_projects = defaultdict(set)
for i, (run, bp, org, t, g, r) in enumerate(rows, start=1):
    slug = org.lower().replace(' ', '_')
    if t:
        trips.append((bp, run, f'{i}.0', f'{run}.bam.sqlite', '', '', '', '',
                      slug, TRIPS_TX.get(org, f'{slug}_tx')))
    if g:
        gwips_projects[bp].add(org)
    if r:
        ribocrypt.append((bp, org, f'all_samples-{bp}', run))

gwips = []
for bp, orgs in gwips_projects.items():
    for org in sorted(orgs):
        slug = org.lower().replace(' ', '_')
        gwips.append((bp, org, GWIPS_DB.get(org, slug),
                      f'{bp}_{slug}_Elong', f'{bp}_{slug}_Init'))

cur.executemany(
    'INSERT INTO main_trips (BioProject, Run, Trips_id, file_name, study_name, '
    'study_srp, study_gse, PMID, organism, transcriptome) '
    'VALUES (?,?,?,?,?,?,?,?,?,?)', trips)
cur.executemany(
    'INSERT INTO main_gwips (BioProject, Organism, gwips_db, GWIPS_Elong_Suffix, '
    'GWIPS_Init_Suffix) VALUES (?,?,?,?,?)', gwips)
cur.executemany(
    'INSERT INTO main_ribocrypt (BioProject, Organism, ribocrypt_id, Run) '
    'VALUES (?,?,?,?)', ribocrypt)
con.commit()
print('trips', len(trips), 'gwips', len(gwips), 'ribocrypt', len(ribocrypt))
