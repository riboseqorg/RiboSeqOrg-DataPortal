"""
Study rows: repair existing ones and create rows for new BioProjects.

Existing rows keep their curated title and description. Publication fields
are not inherited: they are resolved from evidence by authorship.py, because
the old pipeline filled them from a PubMed search for the literal string
"nan" and 358 studies ended up carrying a stranger's paper.
"""
import re
import xml.etree.ElementTree as ET

from .authorship import Evidence, study_name

STUDY_FIELDS = [
    'BioProject', 'Name', 'Title', 'ScientificName', 'Samples', 'SRA',
    'Release_Date', 'Description', 'seq_types', 'GSE', 'PMID', 'Authors',
    'Study_abstract', 'Publication_title', 'doi', 'Date_published', 'PMC',
    'Journal', 'Paper_abstract', 'Email',
    # Provenance: who submitted the data, and where the credit came from
    'Submitters', 'Institution', 'Authorship_source', 'PMID_source',
]
# Fields that describe the paper. They stand or fall together with the PMID:
# filling them one by one is how partial contamination spread.
PAPER_FIELDS = ('Authors', 'Publication_title', 'doi', 'Date_published',
                'PMC', 'Journal', 'Paper_abstract')
BAD_PMIDS = {'', '<na>', 'nan', 'none', '0', '1', '3', '0.0', 'na'}
BAD_NAME = re.compile(r'^(0\.0|nan|Makar|<NA>|)\s+et al\.', re.IGNORECASE)
# Shapes this pipeline generates itself: 'Ingolia et al. 2011', 'RIKEN, 2020',
# 'Unknown 2024'. Anything else was written by a person and is left alone.
AUTO_NAME = re.compile(r'^\S+ et al\.(\s+\d{4})?$|^Unknown\b|'
                       r'^[^,]{2,60},\s*(19|20)\d\d$')
PMID_RE = re.compile(r'^\d{1,8}$')


def valid_pmid(value) -> str:
    value = str(value or '').strip()
    value = re.sub(r'\.0$', '', value)
    return '' if value.casefold() in BAD_PMIDS or not PMID_RE.match(value) \
        else value


class PubMed:
    """Cached PubMed/BioProject lookups over the fetch module's client."""

    def __init__(self, entrez):
        self.ez = entrez
        self.cache = {}

    def paper(self, pmid: str) -> dict:
        # By ID only. A search would answer with something for any string.
        pmid = valid_pmid(pmid)
        if not pmid:
            return {}
        if pmid in self.cache:
            return self.cache[pmid]
        info = {}
        try:
            root = self.ez.xml('esummary.fcgi', db='pubmed', id=pmid)
            doc = root.find('DocSum')
            if doc is not None:
                def item(name):
                    node = doc.find(f"Item[@Name='{name}']")
                    return (node.text or '') if node is not None else ''
                authors = [a.text for a in doc.findall(
                    "Item[@Name='AuthorList']/Item") if a.text]
                ids = {i.get('Name'): i.text for i in doc.findall(
                    "Item[@Name='ArticleIds']/Item")}
                info = {
                    'Authors': ', '.join(authors),
                    'Publication_title': item('Title'),
                    'doi': ids.get('doi') or item('DOI'),
                    'Date_published': item('PubDate'),
                    'PMC': ids.get('pmc', ''),
                    'Journal': item('FullJournalName'),
                }
            raw = self.ez.get('efetch.fcgi', db='pubmed', id=pmid,
                              retmode='xml')
            art = ET.fromstring(raw)
            abstract = ' '.join(''.join(t.itertext()).strip()
                                for t in art.iter('AbstractText'))
            info['Paper_abstract'] = abstract
        except Exception as e:  # noqa: BLE001 - network; leave fields blank
            info['_error'] = repr(e)[:200]
        self.cache[pmid] = info
        return info

    def uid(self, accession: str) -> str:
        """The BioProject UID, which the accession alone is not."""
        key = ('uid', accession)
        if key not in self.cache:
            uid = ''
            try:
                root = self.ez.xml('esearch.fcgi', db='bioproject',
                                   term=f'{accession}[PRJA]')
                uid = root.findtext('.//Id') or ''
            except Exception:  # noqa: BLE001 - network
                uid = ''
            self.cache[key] = uid
        return self.cache[key]

    def bioproject(self, accession: str) -> dict:
        key = ('bp', accession)
        if key in self.cache:
            return self.cache[key]
        info = {}
        try:
            uid = self.uid(accession)
            if uid:
                summ = self.ez.xml('esummary.fcgi', db='bioproject', id=uid)
                doc = summ.find('.//DocumentSummary')
                if doc is not None:
                    date = (doc.findtext('Registration_Date') or '')[:10]
                    info = {
                        'Title': doc.findtext('Project_Title') or '',
                        'Release_Date': date.replace('-', '/') + ' 00:00'
                        if date else '',
                        'Description': doc.findtext('Project_Description')
                        or '',
                    }
        except Exception as e:  # noqa: BLE001
            info['_error'] = repr(e)[:200]
        self.cache[key] = info
        return info


def build_study(accession, samples, existing, abstract, pubmed,
                resolver=None):
    """
    accession: BioProject; samples: list of the study's final sample dicts;
    existing: the current or baseline study row (dict) or None;
    abstract: SRA study abstract; pubmed: PubMed helper (None = offline);
    resolver: authorship.Resolver, which decides the paper and the credit.
    Returns (row, notes).
    """
    notes = []
    row = {f: '' for f in STUDY_FIELDS}
    if existing:
        row.update({f: ('' if existing.get(f) in (None, 'nan', '0.0',
                                                   '<NA>') else
                        str(existing.get(f)))
                    for f in STUDY_FIELDS if f in existing})
        # The paper is re-resolved from evidence every run, so none of it is
        # inherited: a wrong author list is not 'curated work to keep'.
        for field in PAPER_FIELDS + ('PMID',):
            row[field] = ''
    row['BioProject'] = accession
    if row['Release_Date'] and \
            not re.match(r'^(19|20)\d\d/\d\d/\d\d', row['Release_Date']):
        notes.append(f"release date {row['Release_Date']!r} cleared")
        row['Release_Date'] = ''
    row['Samples'] = str(len(samples))
    row['ScientificName'] = '; '.join(sorted(
        {s['ScientificName'] for s in samples if s['ScientificName']}))
    row['SRA'] = ';'.join(sorted({s['SRAStudy'] for s in samples
                                  if s['SRAStudy']}))
    row['seq_types'] = ';'.join(sorted({s['LIBRARYTYPE'] for s in samples
                                        if s['LIBRARYTYPE']}))
    gses = sorted({s['GEO'] for s in samples
                   if s['GEO'].startswith('GSE')})
    if gses and not row['GSE']:
        row['GSE'] = ';'.join(gses)
    if abstract and not row['Study_abstract']:
        row['Study_abstract'] = abstract

    old_pmid = valid_pmid(existing.get('PMID') if existing else '')
    evidence = Evidence(accession)
    if resolver is not None:
        evidence = resolver.resolve(accession, samples, existing or {},
                                    gses, row['SRA'].split(';'))
    row.update(evidence.as_row())
    pmid = row['PMID']
    if old_pmid and pmid and old_pmid != pmid:
        notes.append(f'PMID {old_pmid} -> {pmid} '
                     f'({evidence.pmid_source})')
    elif old_pmid and not pmid:
        notes.append(f'PMID {old_pmid} dropped: nothing links it to the data')
    notes += evidence.notes

    # The rest of the paper comes from the same PubMed record as the authors,
    # or not at all.
    if pmid and pubmed and evidence.source in ('pubmed', 'sra_pmid',
                                               'europepmc', 'manual'):
        info = pubmed.paper(pmid)
        for f in PAPER_FIELDS:
            if info.get(f):
                row[f] = info[f]
        if info.get('Authors'):
            row['Authors'] = info['Authors']
            notes.append(f'publication filled from PubMed {pmid}')
    if pubmed and not row['Title']:
        info = pubmed.bioproject(accession)
        for f in ('Title', 'Release_Date', 'Description'):
            if info.get(f) and not row[f]:
                row[f] = info[f]
    if not row['Release_Date']:
        years = sorted({(s['YEAR'], s['MONTH']) for s in samples
                        if s['YEAR']})
        if years:
            y, m = years[0]
            row['Release_Date'] = f'{y}/{m or "01"}/01 00:00'

    year = row['Release_Date'][:4] if row['Release_Date'] else \
        min((s['YEAR'] for s in samples if s['YEAR']), default='')
    # A name that cites a paper should carry that paper's year, not the year
    # the data happened to be released.
    published = re.search(r'(19|20)\d\d', row['Date_published'] or '')
    if published and row['Authors']:
        year = published.group(0)
    # Any name this pipeline could have generated is regenerated, because the
    # author it was built from may have been the wrong person. A name a
    # curator wrote by hand does not match these shapes and is kept.
    if not row['Name'] or BAD_NAME.match(row['Name']) or \
            AUTO_NAME.match(row['Name']):
        new_name = study_name(row['Authors'], row['Institution'], year)
        if row['Name'] and row['Name'] != new_name:
            notes.append(f"name {row['Name']!r} -> {new_name!r}")
        row['Name'] = new_name
    return row, notes
