"""
Who owns a dataset: the paper, its authors, and the people who submitted it.

Every author list written by this module is traceable to one of the sources
below, recorded in the study's ``Authorship_source``. Nothing is guessed.
The old pipeline guessed: with no PubMed ID it searched PubMed for the
literal string "nan" and stored the first hit,
so 358 studies ended up credited to whichever paper was newest in PubMed the
day the load ran (see the module tests and audit/metadata-audit.md).

Evidence, best first:
  * ``manual``     - a curated row in resources/study_authorship.csv;
  * ``pubmed``     - a PubMed ID that NCBI itself links to the BioProject or
                     GEO series, or that GEO's own record names;
  * ``sra_pmid``   - a PubMed ID that only the SRA records carry, so the
                     paper is plausible but nothing links it to the data;
  * ``europepmc``  - a paper that cites the accession *and* shares authors
                     with the submitters, or an affiliation with the owning
                     institution. A citation on its own is not ownership:
                     reanalysis papers cite accessions too.
Nothing above it means no authors: the study is then credited to its
submitters and institution ("RIKEN, 2020"), which is at least true.

Network results are cached as one JSON file per BioProject, so a rebuild can
run offline once the cache is warm.
"""
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
GEO = 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi'

# Archives and brokers submit on behalf of others, so their name says
# nothing about who produced the data.
BROKERS = re.compile(
    r'european bioinformatics|embl-ebi|^ebi$|ddbj|^ncbi|sequence read archive|'
    r'dna data bank', re.IGNORECASE)
# Words too common in institution names to count as agreement
GENERIC = {
    'university', 'universite', 'universitat', 'universidad', 'the', 'of',
    'and', 'for', 'institute', 'institut', 'instituto', 'department', 'dept',
    'center', 'centre', 'centro', 'school', 'college', 'hospital', 'research',
    'national', 'laboratory', 'laboratories', 'lab', 'medical', 'medicine',
    'sciences', 'science', 'scientific', 'faculty', 'division', 'unit',
    'group', 'program', 'programme', 'gmbh', 'inc', 'ltd', 'llc', 'state',
    'federal', 'academy', 'academic', 'health', 'biology', 'biological',
    'molecular', 'cell', 'cellular', 'genetics', 'genomics', 'technology',
    'technologies', 'engineering', 'campus', 'graduate',
}


def ascii_fold(value: str) -> str:
    return unicodedata.normalize('NFKD', str(value)) \
        .encode('ascii', 'ignore').decode()


def surname(author: str) -> str:
    """
    'Ingolia NT' (PubMed), 'Nicholas,T,Ingolia' (GEO) and 'Nicholas Ingolia'
    all give 'ingolia'.
    """
    author = ascii_fold(author).strip()
    if ',' in author and not re.search(r',\s*[A-Z]{1,3}\.?\s*$', author):
        # GEO writes contributors as First,Middle,Last
        author = author.split(',')[-1]
    else:
        author = re.split(r'[,;]', author)[0]
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", author)
    if not words:
        return ''
    # PubMed puts the surname first and initials last ('Ingolia NT')
    if len(words) > 1 and re.fullmatch(r'[A-Za-z]{1,3}', words[-1]) and \
            words[-1].isupper():
        return words[0].lower()
    return words[-1].lower() if len(words[-1]) > 1 else words[0].lower()


def institution_words(value: str) -> set:
    """The distinctive words of an institution name."""
    return {w for w in re.findall(r"[a-z]{3,}", ascii_fold(value).lower())
            if w not in GENERIC}


# Submitters sometimes type their role, not their institution
JUNK_INSTITUTION = {'postdoc', 'phd', 'phd student', 'student', 'researcher',
                    'scientist', 'professor', 'unknown', 'none', 'na', 'n/a',
                    'test', 'me', 'self', 'university', 'institute', 'lab'}
# The noun an organisation's name is built around
HEAD_NOUN = {'university', 'universite', 'universitat', 'universidad',
             'college', 'institute', 'institut', 'instituto', 'academy',
             'hospital', 'school'}
COUNTRY = {'uk', 'usa', 'us', 'prc', 'roc', 'eu', 'nl', 'de', 'fr', 'cn',
           'jp', 'ca', 'au', 'ch', 'se', 'dk', 'no', 'fi', 'it', 'es'}


def _capitalised(token: str) -> bool:
    return bool(re.match(r"^[A-Z][\w'’-]*$", token)) and \
        token.lower() not in COUNTRY


def organisation_phrase(head: str) -> str:
    """
    The organisation inside an address: 'Department of Biochemistry University
    of Cambridge UK' -> 'University of Cambridge', 'The Ohio State University'
    -> 'Ohio State University'.
    """
    if not any(t[:1].isupper() for t in head.split()):
        head = head.title()   # 'the first affiliated hospital of ...'
        head = re.sub(r'\b(Of|And|The|For|De|Du)\b',
                      lambda m: m.group(1).lower(), head)
    tokens = head.split()
    lowered = [t.lower().strip('.,') for t in tokens]
    for i, word in enumerate(lowered):
        if word not in HEAD_NOUN:
            continue
        left = i
        while left > 0 and _capitalised(tokens[left - 1]) and \
                lowered[left - 1] not in HEAD_NOUN | {'the'}:
            # 'Department of Biochemistry University': 'Biochemistry' follows
            # 'of', so it belongs to the department, not to the university
            if left - 2 >= 0 and lowered[left - 2] == 'of':
                break
            left -= 1
        right = i + 1
        if right < len(tokens) and lowered[right] == 'of':
            right += 1
            while right < len(tokens) and (_capitalised(tokens[right]) or
                                           lowered[right] in ('and', 'the')):
                right += 1
            while right > i + 2 and lowered[right - 1] in ('and', 'the'):
                right -= 1
        words = tokens[left:right]
        # 'University of Cambridge Cambridge' -> the city is written twice
        words = [w for n, w in enumerate(words)
                 if n == 0 or w.casefold() != words[n - 1].casefold()]
        phrase = ' '.join(words).strip(' ,;.')
        # A dangling connector is left when nothing usable followed 'of'
        phrase = re.sub(r'\s+(of|de|du|for|the|and)$', '', phrase,
                        flags=re.IGNORECASE)
        if len(phrase) > 55:
            # Too long to read: cut at 'and', then drop the 'of ...' tail
            phrase = re.split(r'\s+and\s+', phrase, maxsplit=1)[0]
        if len(phrase) > 55:
            phrase = ' '.join(tokens[left:i + 1]).strip(' ,;.')
        if len(phrase.split()) > 1:
            return phrase
    return ''


def short_institution(value: str) -> str:
    """
    A name short enough to display: 'RIKEN Center for Biosystems Dynamics
    Research' -> 'RIKEN', 'Institut de Biologie de Ecole normale superieure
    (IBENS), France' -> 'IBENS'.
    """
    value = re.sub(r'\s+', ' ', str(value or '')).strip(' ,;.')
    if not value or value.casefold() in JUNK_INSTITUTION:
        return ''
    acronym = re.search(r'\(([A-Z][A-Za-z0-9&.-]{1,14})\)', value)
    if acronym:
        return acronym.group(1)
    head = value.split(',')[0].strip()
    # A leading acronym is the name people use: 'KTH', 'EMBL', 'RIKEN'
    lead = re.match(r'^([A-Z][A-Z0-9&.-]{2,14})\b', head)
    if lead and not head.isupper():
        return lead.group(1)
    if head.isupper():
        # 'ICBFM SB RAS' is acronyms; 'UNIVERSITY COLLEGE CORK' is shouting
        if any(len(w) > 5 for w in head.split()):
            head = head.title()
        elif len(head.split()) > 1:
            return head
    return organisation_phrase(head) or \
        (head if len(head) <= 60 else ' '.join(head.split()[:6]))


ORGANISATION = re.compile(
    r'universit|institut|college|centre|center|hospital|academy|riken|embl|'
    r'cnrs|max planck|inserm|csic', re.IGNORECASE)
# Parts of an address that belong to an organisation rather than being one
SUBUNIT = re.compile(r'school|department|dept|laborator|division|faculty|'
                     r'\blab\b|unit\b', re.IGNORECASE)


def best_institution(institution: str) -> str:
    """
    Pick the organisation out of what the repositories give us. GEO's contact
    institute often leads with a lab, a person or a department ('Qian Lab,
    Cornell University'; 'Graduate School of Science and Technology, Nara
    Institute of Science and Technology').
    """
    parts = [p.strip() for p in re.split(r'[;]', str(institution or ''))
             if p.strip()]
    pieces = [q.strip() for p in parts for q in p.split(',') if q.strip()]
    for piece in pieces:
        if ORGANISATION.search(piece) and not SUBUNIT.search(piece):
            return piece
    for piece in pieces:
        if ORGANISATION.search(piece):
            return piece
    return parts[0] if parts else ''


def study_name(authors: str, institution: str, year: str) -> str:
    """
    The study's display name. An author is best; failing that the
    institution that submitted the data, which is true where a guessed
    author name is not.
    """
    first = surname(authors.split(',')[0]) if authors else ''
    year = str(year or '').strip()
    if first:
        return f'{first.title()} et al. {year}'.strip()
    short = short_institution(best_institution(institution))
    if short:
        return f'{short}, {year}'.strip().strip(',')
    return f'Unknown {year}'.strip()


class Evidence:
    """What is known about one study's ownership."""

    def __init__(self, bioproject):
        self.bioproject = bioproject
        self.pmid = ''
        self.pmid_source = ''
        self.authors = ''
        self.source = ''
        # A preprint has a DOI and no PubMed ID. Keeping the DOI is what
        # makes an author list checkable when there is no PMID to cite.
        self.doi = ''
        self.title = ''
        self.submitters = []          # people named by the repository
        self.institutions = []        # owning organisations (brokers dropped)
        self.candidates = []          # Europe PMC mentions, verified or not
        self.notes = []

    @property
    def institution(self) -> str:
        return '; '.join(self.institutions)

    def as_row(self) -> dict:
        return {
            'PMID': self.pmid,
            'Authors': self.authors,
            'Submitters': '; '.join(self.submitters),
            'Institution': self.institution,
            'Authorship_source': self.source,
            'PMID_source': self.pmid_source,
            'doi': self.doi,
            'Publication_title': self.title,
        }


class Web:
    """GEO and Europe PMC lookups, rate limited and cached on disk."""

    def __init__(self, cache_dir=None, offline=False, delay=0.35):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.delay = delay
        self._last = 0.0
        self.requests = 0

    def _get(self, url: str) -> str:
        if self.offline:
            return ''
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return r.read().decode('utf-8', 'replace')
            except Exception:  # noqa: BLE001 - network: retry, then give up
                if attempt == 3:
                    return ''
                time.sleep(2 ** attempt)
        return ''

    def cached(self, key: str, build):
        path = self.cache_dir / f'{key}.json' if self.cache_dir else None
        if path and path.exists():
            try:
                return json.loads(path.read_text())
            except ValueError:
                pass
        if self.offline:
            return None
        value = build()
        if path and value is not None:
            path.write_text(json.dumps(value))
        return value

    def geo_series(self, gse: str) -> dict:
        """Contributors, contact and any PubMed ID GEO names for a series."""
        def build():
            text = self._get(f'{GEO}?' + urllib.parse.urlencode(
                {'acc': gse, 'targ': 'self', 'form': 'text', 'view': 'brief'}))
            people, pmids, institutes = [], [], []
            for line in text.splitlines():
                if '=' not in line:
                    continue
                tag, value = (p.strip() for p in line.split('=', 1))
                if tag in ('!Series_contributor', '!Series_contact_name'):
                    # First,Middle,Last -> 'Last FM', as PubMed writes it
                    parts = [p for p in value.split(',') if p.strip()]
                    if parts:
                        initials = ''.join(p.strip()[0] for p in parts[:-1])
                        people.append(
                            f'{parts[-1].strip()} {initials}'.strip())
                elif tag == '!Series_contact_institute':
                    institutes.append(value)
                elif tag == '!Series_pubmed_id':
                    pmids.append(value)
            return {'people': list(dict.fromkeys(people)),
                    'institutes': list(dict.fromkeys(institutes)),
                    'pmids': pmids}
        return self.cached(f'geo_{gse}', build) or \
            {'people': [], 'institutes': [], 'pmids': []}

    def ena_project(self, accession: str) -> dict:
        """
        ENA's own view of a project. It carries PubMed cross-references that
        NCBI's elink sometimes lacks (PRJDB2960 -> 27013550) and names the
        submitting institution, which is all an ENA or DDBJ study has.
        """
        def build():
            xml = self._get(
                f'https://www.ebi.ac.uk/ena/browser/api/xml/{accession}')
            if '<PROJECT' not in xml:
                return None
            pmids = [m for db, m in re.findall(
                r'<DB>([^<]+)</DB>\s*<ID>([^<]*)</ID>', xml)
                if db.strip().upper() == 'PUBMED' and m.strip().isdigit()]
            namespace = re.search(r'<SUBMITTER_ID namespace="([^"]*)"', xml)
            return {'pmids': pmids,
                    'institution': (namespace.group(1).strip()
                                    if namespace else '')}
        return self.cached(f'ena_{accession}', build) or \
            {'pmids': [], 'institution': ''}

    def mentions(self, accessions: list) -> list:
        """Papers whose text cites any of these accessions."""
        accessions = [a for a in accessions if a]
        if not accessions:
            return []
        key = 'epmc_' + accessions[0]

        def build():
            query = ' OR '.join(f'"{a}"' for a in accessions)
            raw = self._get(EPMC + '?' + urllib.parse.urlencode({
                'query': query, 'format': 'json', 'resultType': 'core',
                'pageSize': 25}))
            try:
                hits = json.loads(raw)['resultList']['result']
            except (ValueError, KeyError):
                return None
            out = []
            for h in hits:
                authors = h.get('authorList', {}).get('author', [])
                out.append({
                    'pmid': h.get('pmid', ''),
                    'doi': h.get('doi', ''),
                    'id': h.get('id', ''),
                    'source': h.get('source', ''),
                    'year': h.get('pubYear', ''),
                    'title': h.get('title', '')[:300],
                    'authorString': h.get('authorString', ''),
                    'surnames': [
                        surname(a.get('lastName') or a.get('fullName', ''))
                        for a in authors],
                    'affiliations': ' '.join(filter(None, [
                        h.get('affiliation', ''),
                        *[a.get('affiliation', '') for a in authors]]))[:2000],
                })
            return out
        return self.cached(key, build) or []


def bioproject_owners(entrez, accession: str, uid: str, web: Web) -> list:
    """The organisations that own a BioProject, brokers excluded."""
    def build():
        if not uid or entrez is None:
            return []
        try:
            root = entrez.xml('efetch.fcgi', db='bioproject', id=uid,
                              retmode='xml')
        except Exception:  # noqa: BLE001 - network
            return []
        names = []
        for org in root.iter('Organization'):
            name = (org.findtext('Name') or org.text or '').strip()
            if name:
                names.append(name)
        return list(dict.fromkeys(names))
    names = web.cached(f'owner_{accession}', build) or []
    return [n for n in names if not BROKERS.search(n)]


def verify_candidate(candidate: dict, submitters: list,
                     institutions: list) -> tuple:
    """
    Is this citing paper the one that produced the data?

    Returns (verified, reason). Shared authors are the strong signal: a
    reanalysis cites the accession but is written by other people. With no
    submitter names (ENA and DDBJ rarely give them) the owning institution
    has to do, and then two distinctive words must agree.
    """
    shared = sorted(set(submitters) & set(candidate.get('surnames') or []))
    if submitters:
        enough = 2 if len(submitters) > 2 else 1
        if len(shared) >= enough:
            return True, ('shares authors with the submitters: '
                          + ', '.join(shared))
        if shared and candidate.get('surnames') and \
                candidate['surnames'][-1] in submitters:
            return True, f"last author {shared[0]} submitted the data"
        return False, 'submitters are not among its authors'
    institutions = [i for i in institutions if not BROKERS.search(i)]
    words = set().union(*(institution_words(i) for i in institutions)) \
        if institutions else set()
    affiliations = candidate.get('affiliations', '')
    agree = sorted(words & institution_words(affiliations))
    if len(agree) >= 2:
        return True, ('affiliation matches the submitting institution: '
                      + ', '.join(agree[:4]))
    return False, 'nothing ties its authors to the submitters'


class Resolver:
    """
    Resolves one study at a time. ``pubmed`` is studies.PubMed (paper
    lookups and BioProject UIDs); ``entrez`` is fetch.Entrez or None.
    """

    def __init__(self, pubmed=None, entrez=None, web=None, manual=None,
                 use_europepmc=True):
        self.pubmed = pubmed
        self.entrez = entrez
        self.web = web or Web(offline=True)
        self.manual = manual or {}
        self.use_europepmc = use_europepmc
        self.seen = {}   # BioProject -> Evidence, for the review queue

    # -- evidence gathering ------------------------------------------------
    def linked_pmids(self, accession: str) -> set:
        """PubMed IDs NCBI links to this BioProject."""
        if self.pubmed is None:
            return set()

        def build():
            uid = self.pubmed.uid(accession)
            if not uid:
                return []
            try:
                root = self.entrez.xml('elink.fcgi', dbfrom='bioproject',
                                       db='pubmed', id=uid)
            except Exception:  # noqa: BLE001 - network
                return None
            return [e.text for e in root.iter('Id') if e.text != uid]
        return set(self.web.cached(f'elink_{accession}', build) or [])

    def resolve(self, accession: str, samples: list, existing: dict,
                gses: list, sras: list) -> Evidence:
        evidence = self._resolve(accession, samples, existing, gses, sras)
        self.seen[accession] = evidence
        return evidence

    def _resolve(self, accession: str, samples: list, existing: dict,
                 gses: list, sras: list) -> Evidence:
        from .studies import valid_pmid  # circular at import time only
        ev = Evidence(accession)

        # Who the repositories say submitted the data
        for gse in gses:
            series = self.web.geo_series(gse)
            ev.submitters += [p for p in series['people']
                              if p not in ev.submitters]
            ev.institutions += [i for i in series['institutes']
                                if i not in ev.institutions]
        uid = self.pubmed.uid(accession) if self.pubmed else ''
        ena = self.web.ena_project(accession)
        # SRA's CenterName is the submitting centre, and for ENA and DDBJ
        # studies it is often the only institution on record.
        centres = [c for c in dict.fromkeys(
            s.get('CenterName', '').strip() for s in samples)
            if c and c.upper() not in ('GEO', 'NA')]
        for owner in bioproject_owners(self.entrez, accession, uid, self.web) \
                + ([ena['institution']] if ena['institution'] else []) \
                + centres:
            if owner not in ev.institutions:
                ev.institutions.append(owner)
        ev.institutions = [i for i in ev.institutions
                           if not BROKERS.search(i)
                           and i.casefold() not in JUNK_INSTITUTION]

        # A curated row wins outright
        curated = self.manual.get(accession)
        if curated:
            ev.pmid = valid_pmid(curated.get('PMID')) or ''
            ev.authors = curated.get('Authors', '').strip()
            ev.source = 'manual'
            ev.pmid_source = 'manual' if ev.pmid else ''
            ev.notes.append('authorship taken from the curated sheet')
            if ev.pmid and not ev.authors and self.pubmed:
                paper = self.pubmed.paper(ev.pmid)
                ev.authors = paper.get('Authors', '')
            return ev

        # PubMed IDs, and what links each one to the data
        linked = self.linked_pmids(accession)
        for gse in gses:
            linked |= {p for p in self.web.geo_series(gse)['pmids']
                       if valid_pmid(p)}
        linked |= {p for p in ena['pmids'] if valid_pmid(p)}
        from_sra = {valid_pmid(s.get('Study_Pubmed_id')) for s in samples}
        from_sra |= {valid_pmid(existing.get('PMID') if existing else '')}
        from_sra -= {''}
        if linked & from_sra:
            ev.pmid, ev.pmid_source = sorted(linked & from_sra, key=int)[0], \
                'ncbi_link'
        elif linked:
            ev.pmid, ev.pmid_source = sorted(linked, key=int)[0], 'ncbi_link'
            if from_sra:
                ev.notes.append(
                    f"PMID {sorted(from_sra)[0]} replaced by NCBI's link "
                    f'{ev.pmid}')
        elif from_sra:
            ev.pmid, ev.pmid_source = sorted(from_sra, key=int)[0], 'sra_only'

        if ev.pmid:
            paper = self.pubmed.paper(ev.pmid) if self.pubmed else {}
            ev.authors = paper.get('Authors', '')
            if ev.authors:
                ev.source = 'pubmed' if ev.pmid_source == 'ncbi_link' \
                    else 'sra_pmid'
                if ev.source == 'sra_pmid':
                    # No repository links this paper, but if the people who
                    # wrote it are the people who submitted the data, that is
                    # the same evidence by another route.
                    ok, reason = verify_candidate(
                        {'surnames': [surname(a) for a in
                                      ev.authors.split(',')],
                         'affiliations': ''},
                        [surname(p) for p in ev.submitters], ev.institutions)
                    if ok:
                        ev.source, ev.pmid_source = 'pubmed', 'submitters'
                        ev.notes.append(f'PMID {ev.pmid} confirmed: {reason}')
                return ev
            if not self.pubmed:
                # Offline: keep a PMID that was already verified, but never
                # inherit an author list we cannot check
                ev.source = ''
                return ev

        # No paper yet: look for one that cites the accession
        if self.use_europepmc:
            for cand in self.web.mentions([accession] + list(gses) +
                                          list(sras)):
                ok, reason = verify_candidate(cand, [surname(p) for p in
                                                     ev.submitters],
                                             ev.institutions)
                cand = dict(cand, verified=ok, reason=reason)
                ev.candidates.append(cand)
            verified = [c for c in ev.candidates if c['verified']]
            # A peer-reviewed record beats a preprint of the same work
            verified.sort(key=lambda c: (c['source'] == 'PPR', c['year']))
            if verified and not ev.pmid:
                best = verified[0]
                if best['pmid']:
                    ev.pmid, ev.pmid_source = best['pmid'], 'europepmc'
                    paper = self.pubmed.paper(best['pmid']) if self.pubmed \
                        else {}
                    ev.authors = paper.get('Authors', '') or \
                        best['authorString']
                else:
                    # A preprint: no PMID, but a DOI that identifies the
                    # paper the author list came from.
                    ev.authors = best['authorString']
                    ev.pmid_source = ''
                    ev.doi = best.get('doi', '')
                    ev.title = best.get('title', '')
                ev.source = 'europepmc'
                ev.notes.append(
                    f"paper {best['pmid'] or best['id']} accepted: "
                    f"{best['reason']}")
                return ev

        if ev.submitters or ev.institutions:
            ev.source = 'submitters'
        return ev


def shared_author_strings(rows, limit=5):
    """
    Author lists spread over many studies that do not agree on one paper.

    This is the signature of the esearch("nan") bug: one stranger's author
    list on hundreds of studies. A real group publishes several datasets
    under one paper, so a shared list is only suspicious when the studies
    carry different PubMed IDs.
    """
    seen = {}
    for row in rows:
        authors = (row.get('Authors') or '').strip()
        if not authors:
            continue
        studies, pmids = seen.setdefault(authors, (set(), set()))
        studies.add(row.get('BioProject') or len(studies))
        pmids.add((row.get('PMID') or '').strip())
    return {authors: sorted(pmids)
            for authors, (studies, pmids) in seen.items()
            if len(studies) > limit and len(pmids) > 1}
