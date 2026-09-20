'''
Genome browser links built from each run's forward/reverse bigWig files.

A single run is linked with its track lines inline in the URL
(hgct_customText=track ...). Several runs (a study, or a links-page
selection) would make the URL too long, so those link to the tracks view,
which serves the track lines as text for the browser to fetch.

Links open GWIPS-viz (a UCSC Genome Browser install), with the assembly
chosen per organism in GENOME_ASSEMBLIES. Organisms not listed there get no
genome browser link.
'''
from urllib.parse import quote, urlencode

from django.conf import settings

GWIPS = "https://gwips.ucc.ie"

# Sample.ScientificName -> (browser, GWIPS-viz assembly). The assembly must be
# the one the bigWigs were aligned to; UNVERIFIED until checked against the
# bigWigs' chromosome names and sizes (see audit/performance-info-needed.md).
GENOME_ASSEMBLIES = {
    'Homo sapiens': (GWIPS, 'hg38'),
    'Mus musculus': (GWIPS, 'mm10'),
    'Saccharomyces cerevisiae': (GWIPS, 'sacCer3'),
    'Danio rerio': (GWIPS, 'danRer7'),
    'Caenorhabditis elegans': (GWIPS, 'ce10'),
    'Rattus norvegicus': (GWIPS, 'rn6'),
    'Drosophila melanogaster': (GWIPS, 'dm3'),
    'Arabidopsis thaliana': (GWIPS, 'araTha1'),
    'Escherichia coli': (GWIPS, 'eschColi_K12'),
    'Schizosaccharomyces pombe': (GWIPS, 's_pombe'),
    'Bacillus subtilis': (GWIPS, 'baciSubt2'),
    'Staphylococcus aureus': (GWIPS, 'Saureus_ASM1346'),
    'Xenopus laevis': (GWIPS, 'xenLaevis'),
    'Zea mays': (GWIPS, 'Zea_Mays_B73'),
    'Trypanosoma brucei': (GWIPS, 'Tbrucei_TREU927'),
    'Streptomyces coelicolor': (GWIPS, 'S_coelicolor_ASM20383v1'),
    'Salmonella enterica': (GWIPS, 'Salmonella_typhimurium_SL1344'),
    'Plasmodium falciparum': (GWIPS, 'plasFalc1'),
    'Mycobacteroides abscessus': (GWIPS, 'Mabcessus_ASM6918v1'),
    'Human betaherpesvirus 5': (GWIPS, 'HHV5'),
    'Caulobacter vibrioides': (GWIPS, 'caulCres'),
}

# Most runs shown in one multi-run view; more makes the browser unusable
MAX_TRACK_RUNS = 200
# Above this many runs, tracks start collapsed (dense) instead of full
FULL_VISIBILITY_RUNS = 10

STRANDS = [
    ('bigwig_forward_link', 'fwd', 'forward strand', '0,100,200'),
    ('bigwig_reverse_link', 'rev', 'reverse strand', '200,60,60'),
]
# Metadata values that mean "no value"
MISSING = {'', 'nan', 'none', 'na', 'nana', 'null', '0.0', '<na>'}
MAX_DESCRIPTION = 120
DESCRIPTION_FIELDS = ['LIBRARYTYPE', 'CELL_LINE', 'TISSUE', 'INHIBITOR',
                      'CONDITION', 'TIMEPOINT', 'REPLICATE']


def assembly_for(organism: str):
    return GENOME_ASSEMBLIES.get(organism)


def has_tracks(sample) -> bool:
    return bool(assembly_for(sample.ScientificName) and
                (sample.bigwig_forward_link or sample.bigwig_reverse_link))


def _clean(value) -> str:
    # Track line values are double-quoted, so drop quotes and line breaks
    text = ' '.join(str(value).replace('"', "'").split())
    return '' if text.lower() in MISSING else text


def describe(sample) -> str:
    '''
    e.g. "SRR123 Ribo-Seq, HeLa, CHX (PRJNA1)"
    '''
    details = []
    for field in DESCRIPTION_FIELDS:
        value = _clean(getattr(sample, field, ''))
        if value and value not in details:
            details.append(value)
    text = sample.Run
    if details:
        text += ' ' + ', '.join(details)
    if sample.BioProject_id:
        text += f' ({sample.BioProject_id})'
    return text


def track_lines(samples, visibility: str = 'full') -> list:
    '''
    UCSC custom track lines, one per available strand of each sample.
    '''
    lines = []
    for sample in samples:
        # Leave room for the strand; browsers truncate long labels anyway
        description = describe(sample)[:MAX_DESCRIPTION]
        for attr, short, strand, colour in STRANDS:
            url = getattr(sample, attr)
            if not url:
                continue
            lines.append(
                f'track type=bigWig name="{sample.Run} {short}" '
                f'description="{description}, {strand}" '
                f'visibility={visibility} color={colour} bigDataUrl={url}')
    return lines


def run_link(sample):
    '''
    Browser link for one run with its tracks inline, or None.
    '''
    target = assembly_for(sample.ScientificName)
    if not target or not has_tracks(sample):
        return None
    browser, db = target
    text = '\n'.join(track_lines([sample]))
    return (f'{browser}/cgi-bin/hgTracks?db={db}'
            f'&hgct_customText={quote(text, safe="=,/:")}')


def selection_link(organism: str, selection: dict):
    '''
    Browser link that loads tracks for a selection of runs from the tracks
    view. `selection` holds the same parameters as the links page
    (run / bioproject / query).
    '''
    target = assembly_for(organism)
    if not target:
        return None
    browser, db = target
    params = [(key, value) for key, values in selection.items() for value in values]
    params.append(('organism', organism))
    tracks_url = f'{settings.PUBLIC_BASE_URL}/tracks/ucsc.txt?{urlencode(params)}'
    return (f'{browser}/cgi-bin/hgTracks?db={db}'
            f'&hgct_customText={quote(tracks_url, safe="")}')


# Links-page parameters that select samples, passed on to the tracks view
SELECTION_KEYS = ('run', 'bioproject', 'query')


def selection_from(params) -> dict:
    return {key: params.getlist(key) for key in SELECTION_KEYS if params.getlist(key)}


def selection_links(samples, selection: dict) -> list:
    '''
    One browser link per organism that has tracks among the samples.

    Returns:
    - (list): dicts with clean_organism, link and runs (number with tracks)
    '''
    counts: dict = {}
    for sample in samples.only('Run', 'ScientificName', 'BioProject'):
        if has_tracks(sample):
            counts[sample.ScientificName] = counts.get(sample.ScientificName, 0) + 1
    return [{
        'clean_organism': organism,
        'link': selection_link(organism, selection),
        'runs': n,
    } for organism, n in sorted(counts.items(), key=lambda item: -item[1])]


def tracks_text(samples) -> str:
    '''
    The track lines for a multi-run view, capped at MAX_TRACK_RUNS runs.
    '''
    chosen = []
    for sample in samples:
        if has_tracks(sample):
            chosen.append(sample)
            if len(chosen) == MAX_TRACK_RUNS:
                break
    visibility = 'full' if len(chosen) <= FULL_VISIBILITY_RUNS else 'dense'
    header = [f'# RiboSeq.Org Data Portal: bigWig tracks for {len(chosen)} runs']
    if len(chosen) == MAX_TRACK_RUNS:
        header.append(f'# Limited to the first {MAX_TRACK_RUNS} runs with tracks')
    return '\n'.join(header + track_lines(chosen, visibility)) + '\n'
