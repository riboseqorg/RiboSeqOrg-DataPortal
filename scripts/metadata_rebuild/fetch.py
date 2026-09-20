"""
Fetch SRA run metadata for Ribo-seq BioProjects that have no local record yet.

Mirrors ORFik::download.SRA.metadata(rich.format = TRUE), which produced the
existing SraRunInfo_<project>.csv files, with three fixes:
  * sample/experiment attributes are attached to their own run (ORFik cbinds
    one attribute row per experiment onto one row per run, which misaligns
    experiments that have several runs);
  * PubMed links are resolved through the BioProject UID (ORFik strips the
    letters from the accession, which is only the UID for PRJNA projects);
  * a missing PubMed ID stays empty (ORFik ended up with PMID 1, whose first
    author, "Makar", then became the AUTHOR of thousands of samples).

Usage (from scripts/):
    python -m metadata_rebuild.fetch \
        --existing ~/projects/Metadata-Curation/SraRunInfo \
        --whitelist ~/projects/Metadata-Curation/resources/whitelisted_bioprojects.csv \
        --out ../build/metadata_rebuild/sra_cache
"""
import argparse
import csv
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

EUTILS = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
# Same query as Metadata-Curation/metadata_find&fetch.R
SEARCH_TERM = ('((Ribosomal footprinting) OR (Ribosome footprinting) OR '
               '(Ribosome profiling) OR ribo-seq)')
RUNINFO_FIELDS = [
    'Run', 'spots', 'bases', 'avgLength', 'size_MB', 'Experiment',
    'LibraryName', 'LibraryStrategy', 'LibrarySelection', 'LibrarySource',
    'LibraryLayout', 'InsertSize', 'InsertDev', 'Platform', 'Model',
    'SRAStudy', 'BioProject', 'Study_Pubmed_id', 'ProjectID', 'Sample',
    'BioSample', 'SampleType', 'TaxID', 'ScientificName', 'SampleName',
    'CenterName', 'Submission', 'MONTH', 'YEAR', 'AUTHOR', 'sample_source',
    'sample_title', 'GEO',
    # Evidence for the data type: often state the method per library
    'experiment_title', 'design_description', 'library_construction_protocol',
]


class Entrez:
    """Minimal E-utilities client: rate limited, retried, optional API key."""

    def __init__(self, api_key=None, email=None):
        self.api_key = api_key
        self.email = email
        self.delay = 0.11 if api_key else 0.35
        self._last = 0.0
        self._lock = threading.Lock()  # shared across worker threads

    def get(self, tool, **params):
        params.setdefault('tool', 'riboseqorg_metadata_rebuild')
        if self.api_key:
            params['api_key'] = self.api_key
        if self.email:
            params['email'] = self.email
        data = urllib.parse.urlencode(params).encode()
        for attempt in range(6):
            with self._lock:  # NCBI limit: 3 requests/s (10 with a key)
                wait = self.delay - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            try:
                with urllib.request.urlopen(EUTILS + tool, data=data,
                                            timeout=120) as r:
                    return r.read()
            except Exception as e:  # noqa: BLE001 - network: retry anything
                if attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError('unreachable')

    def xml(self, tool, **params):
        return ET.fromstring(self.get(tool, **params))


def search_bioprojects(ez):
    root = ez.xml('esearch.fcgi', db='bioproject', term=SEARCH_TERM,
                  retmax=100000)
    uids = [e.text for e in root.iter('Id')]
    accessions = []
    for i in range(0, len(uids), 400):
        summ = ez.xml('esummary.fcgi', db='bioproject',
                      id=','.join(uids[i:i + 400]))
        accessions += [d.findtext('Project_Acc')
                       for d in summ.iter('DocumentSummary')]
    return [a for a in accessions if a]


def text(node, path, default=''):
    if node is None:
        return default
    found = node.find(path)
    return (found.text or '').strip() if found is not None and \
        found.text is not None else default


def attributes(node, path):
    out = []
    if node is None:
        return out
    for a in node.findall(path):
        tag, value = text(a, 'TAG'), text(a, 'VALUE')
        if tag:
            out.append((tag, value))
    return out


def parse_package(pkg):
    """One EXPERIMENT_PACKAGE -> list of (runinfo dict, [(attr, value)])."""
    exp = pkg.find('EXPERIMENT')
    study = pkg.find('STUDY')
    sample = pkg.find('SAMPLE')
    sub = pkg.find('SUBMISSION')
    lib = exp.find('DESIGN/LIBRARY_DESCRIPTOR') if exp is not None else None
    layout = lib.find('LIBRARY_LAYOUT') if lib is not None else None
    platform = exp.find('PLATFORM') if exp is not None else None
    platform_node = platform[0] if platform is not None and len(platform) \
        else None

    bioproject = ''
    gse = ''
    for node in (study, exp.find('STUDY_REF') if exp is not None else None):
        if node is None:
            continue
        for ext in node.findall('IDENTIFIERS/EXTERNAL_ID'):
            ns = ext.get('namespace', '')
            if ns == 'BioProject' and not bioproject:
                bioproject = (ext.text or '').strip()
            if ns == 'GEO' and not gse:
                gse = (ext.text or '').strip()
    pubmed = ''
    if study is not None:
        for x in study.findall('STUDY_LINKS/STUDY_LINK/XREF_LINK'):
            if text(x, 'DB').lower() == 'pubmed' and text(x, 'ID'):
                pubmed = text(x, 'ID')
                break
    biosample = ''
    if sample is not None:
        for ext in sample.findall('IDENTIFIERS/EXTERNAL_ID'):
            if ext.get('namespace', '') == 'BioSample':
                biosample = (ext.text or '').strip()
    sample_attrs = attributes(sample, 'SAMPLE_ATTRIBUTES/SAMPLE_ATTRIBUTE')
    exp_attrs = attributes(exp, 'EXPERIMENT_ATTRIBUTES/EXPERIMENT_ATTRIBUTE')
    author = text(pkg, 'Organization/Contact/Name/Last')
    if author in ('Curators', 'GEO'):
        author = ''

    base = {
        'Experiment': text(exp, 'IDENTIFIERS/PRIMARY_ID'),
        'LibraryName': text(lib, 'LIBRARY_NAME'),
        'LibraryStrategy': text(lib, 'LIBRARY_STRATEGY'),
        'LibrarySelection': text(lib, 'LIBRARY_SELECTION'),
        'LibrarySource': text(lib, 'LIBRARY_SOURCE'),
        'LibraryLayout': layout[0].tag if layout is not None and len(layout)
        else '',
        'InsertSize': '0', 'InsertDev': '0',
        'Platform': platform_node.tag if platform_node is not None else '',
        'Model': text(platform_node, 'INSTRUMENT_MODEL'),
        'SRAStudy': text(study, 'IDENTIFIERS/PRIMARY_ID'),
        'BioProject': bioproject,
        'Study_Pubmed_id': pubmed,
        'ProjectID': '',
        'Sample': text(sample, 'IDENTIFIERS/PRIMARY_ID'),
        'BioSample': biosample,
        'SampleType': 'simple',
        'TaxID': text(sample, 'SAMPLE_NAME/TAXON_ID'),
        'ScientificName': text(sample, 'SAMPLE_NAME/SCIENTIFIC_NAME'),
        'SampleName': sample.get('alias', '') if sample is not None else '',
        'CenterName': sub.get('center_name', '') if sub is not None else '',
        'Submission': sub.get('accession', '') if sub is not None else '',
        'AUTHOR': author,
        'sample_source': '; '.join(v for t, v in sample_attrs
                                   if t == 'source_name'),
        'sample_title': text(sample, 'TITLE'),
        'GEO': gse,
        'experiment_title': text(exp, 'TITLE'),
        'design_description': text(exp, 'DESIGN/DESIGN_DESCRIPTION'),
        'library_construction_protocol':
            text(lib, 'LIBRARY_CONSTRUCTION_PROTOCOL'),
    }
    rows = []
    for run in pkg.findall('RUN_SET/RUN'):
        spots = run.get('total_spots', '') or ''
        bases = run.get('total_bases', '') or ''
        avg = ''
        read = run.find('Statistics/Read')
        if read is not None and read.get('average'):
            avg = str(int(round(float(read.get('average')))))
        elif spots and bases and int(spots) > 0:
            avg = str(int(round(int(bases) / int(spots))))
        size = run.get('size', '')
        published = run.get('published', '') or ''
        row = dict(base)
        row.update({
            'Run': run.get('accession', '') or text(run, 'IDENTIFIERS/PRIMARY_ID'),
            'spots': spots, 'bases': bases, 'avgLength': avg,
            'size_MB': str(int(size) // 1024 ** 2) if size else '',
            'MONTH': published[5:7], 'YEAR': published[:4],
        })
        rows.append((row, sample_attrs + exp_attrs))
    return rows, text(study, 'DESCRIPTOR/STUDY_ABSTRACT')


def pubmed_for_bioproject(ez, accession):
    root = ez.xml('esearch.fcgi', db='bioproject', term=f'{accession}[PRJA]')
    uids = [e.text for e in root.iter('Id')]
    if not uids:
        return ''
    link = ez.xml('elink.fcgi', dbfrom='bioproject', db='pubmed', id=uids[0])
    ids = [e.text for e in link.findall('.//LinkSetDb/Link/Id')]
    return sorted(ids, key=int)[0] if ids else ''


def first_author(ez, pmid):
    root = ez.xml('esummary.fcgi', db='pubmed', id=pmid)
    name = root.findtext(".//Item[@Name='AuthorList']/Item")
    return name.split(' ')[0] if name else ''


def fetch_project(ez, accession):
    root = ez.xml('esearch.fcgi', db='sra', term=accession, retmax=100000)
    ids = [e.text for e in root.iter('Id')]
    if not ids:
        return [], ''
    rows, abstract = [], ''
    for i in range(0, len(ids), 200):
        xml = ez.xml('efetch.fcgi', db='sra', id=','.join(ids[i:i + 200]),
                     retmode='xml')
        for pkg in xml.iter('EXPERIMENT_PACKAGE'):
            pkg_rows, pkg_abstract = parse_package(pkg)
            rows += pkg_rows
            abstract = abstract or pkg_abstract
    # ORFik drops runs with no reads (they can't be downloaded)
    rows = [(r, a) for r, a in rows if r['spots'] not in ('', '0')]
    # Keep only runs that belong to this project (esearch is a text search)
    rows = [(r, a) for r, a in rows if r['BioProject'] in ('', accession)]
    pmid = next((r['Study_Pubmed_id'] for r, _ in rows
                 if r['Study_Pubmed_id']), '')
    if not pmid:
        pmid = pubmed_for_bioproject(ez, accession)
    author = first_author(ez, pmid) if pmid else ''
    for r, _ in rows:
        r['Study_Pubmed_id'] = pmid
        r['AUTHOR'] = author  # ORFik: pubmed first author, else blank
        r['BioProject'] = r['BioProject'] or accession
    return rows, abstract


def write_runinfo(path, rows):
    attr_names = []
    for _, attrs in rows:
        for tag, _ in attrs:
            if tag not in attr_names and tag not in RUNINFO_FIELDS:
                attr_names.append(tag)
    tmp = Path(str(path) + '.part')  # rename at the end: no partial files
    with open(tmp, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(RUNINFO_FIELDS + attr_names)
        for row, attrs in rows:
            values = {}
            for tag, value in attrs:  # repeated tags are kept, '; '-joined
                if value:
                    values[tag] = f'{values[tag]}; {value}' \
                        if tag in values and value not in values[tag] \
                        else values.get(tag, value)
            w.writerow([row[f] for f in RUNINFO_FIELDS] +
                       [values.get(t, '') for t in attr_names])
    tmp.replace(path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--existing', type=Path, required=True,
                   help='Directory of already downloaded SraRunInfo_*.csv')
    p.add_argument('--also-from', type=Path,
                   help='Also (re)fetch every project with a SraRunInfo_*.csv '
                        'here, e.g. the historical Metadata-Curation folder')
    p.add_argument('--whitelist', type=Path,
                   help='CSV with an "id" column of BioProjects to include')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--api-key')
    p.add_argument('--email')
    p.add_argument('--limit', type=int, help='Fetch at most N projects')
    p.add_argument('--workers', type=int, default=4,
                   help='Concurrent projects (requests stay rate limited)')
    args = p.parse_args(argv)

    ez = Entrez(args.api_key, args.email)
    args.out.mkdir(parents=True, exist_ok=True)
    candidates = search_bioprojects(ez)
    print(f'{len(candidates)} BioProjects match the search', flush=True)
    if args.whitelist and args.whitelist.exists():
        with open(args.whitelist, newline='') as fh:
            extra = [r['id'] for r in csv.DictReader(fh) if r.get('id')]
        candidates += [a for a in extra if a not in set(candidates)]
    if args.also_from:
        old = [f.stem.replace('SraRunInfo_', '')
               for f in sorted(args.also_from.glob('SraRunInfo_*.csv'))]
        candidates += [a for a in old if a not in set(candidates)]
    with open(args.out / 'bioproject_candidates.txt', 'w') as fh:
        fh.write('\n'.join(candidates) + '\n')

    have = {f.stem.replace('SraRunInfo_', '')
            for d in (args.existing, args.out)
            for f in d.glob('SraRunInfo_*.csv')}
    log_path = args.out / 'fetch_log.csv'
    if log_path.exists():
        with open(log_path, newline='') as fh:
            have |= {r['BioProject'] for r in csv.DictReader(fh)
                     if r['status'] == 'no_runs'}
    todo = [a for a in dict.fromkeys(candidates) if a not in have]
    if args.limit:
        todo = todo[:args.limit]
    print(f'{len(todo)} projects to fetch', flush=True)

    new_log = not log_path.exists()
    with open(log_path, 'a', newline='') as log_fh, \
            ThreadPoolExecutor(args.workers) as pool:
        log = csv.writer(log_fh)
        if new_log:
            log.writerow(['BioProject', 'status', 'runs', 'detail'])
        futures = {pool.submit(fetch_project, ez, acc): acc for acc in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            acc = futures[fut]
            try:
                rows, abstract = fut.result()
            except Exception as e:  # noqa: BLE001 - log and continue
                log.writerow([acc, 'error', 0, repr(e)[:300]])
                log_fh.flush()
                print(f'[{n}/{len(todo)}] {acc}: error {e!r}', flush=True)
                continue
            if rows:
                write_runinfo(args.out / f'SraRunInfo_{acc}.csv', rows)
                with open(args.out / f'abstract_{acc}.csv', 'w',
                          newline='') as fh:
                    csv.writer(fh).writerows([['abstract'], [abstract]])
            log.writerow([acc, 'ok' if rows else 'no_runs', len(rows), ''])
            log_fh.flush()
            print(f'[{n}/{len(todo)}] {acc}: {len(rows)} runs', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
