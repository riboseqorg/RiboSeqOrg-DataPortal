'''
Build Trips-Viz, genome browser and RiboCrypt links for many samples at once,
with one query per link table rather than several per sample.

GWIPS-viz gets two links, because there are two different things to show:
- gwips_link: the portal's own per-run coverage, as a UCSC custom track built
  from that run's bigWig files (see genome_tracks.py). No table needed.
- gwips_native_link: the curated tracks GWIPS-viz already hosts for the study,
  from the GWIPS table. Study-level, and only for the studies GWIPS has loaded.

Each link is a dict with the keys used by the templates: trips_link,
trips_name, gwips_link, gwips_name, gwips_native_link, gwips_native_name,
ribocrypt_link, ribocrypt_name. An unavailable viewer gets its home page as
the link and an empty name.
'''
from . import genome_tracks
from .models import GWIPS, RiboCrypt, Trips

TRIPS_HOME = "https://trips.ucc.ie/"
GWIPS_HOME = "https://gwips.ucc.ie/"
RIBOCRYPT_HOME = "https://ribocrypt.org/"

# Keeps each IN (...) under SQLite's bound-parameter limit
CHUNK_SIZE = 500


def _unique(values):
    return list(dict.fromkeys(values))


def trips_file_id(value: str) -> str:
    # Older loads stored IDs as e.g. "1234.0"
    try:
        return str(int(float(value)))
    except ValueError:
        return value


def _trips(rows: list) -> tuple:
    '''
    Link to the first transcriptome (in table order) of the given Trips rows.
    '''
    if not rows:
        return TRIPS_HOME, ""
    first = rows[0]
    ids = _unique(trips_file_id(r.Trips_id) for r in rows
                  if r.transcriptome == first.transcriptome)
    return (f"https://trips.ucc.ie/{first.organism}/{first.transcriptome}"
            f"/interactive_plot/?files={','.join(ids)}", 'Visit Trips-Viz')


def _ribocrypt(rows: list) -> tuple:
    '''
    Link to the first (ribocrypt_id, Organism) group of the given rows.
    '''
    if not rows:
        return RIBOCRYPT_HOME, ""
    key = min((r.ribocrypt_id, r.Organism) for r in rows)
    ribocrypt_id, organism = key
    runs = _unique(r.Run for r in rows if (r.ribocrypt_id, r.Organism) == key)
    dff = f"{ribocrypt_id}-{organism.replace(' ', '_').lower()}"
    return (f"https://ribocrypt.org/?dff={dff}&library={','.join(runs)}"
            "&go=TRUE&go=TRUE", 'Visit RiboCrypt')


def _gwips(link) -> tuple:
    # The name is what the templates test for, so it stays the same
    return (link, 'Visit GWIPS-viz') if link else (GWIPS_HOME, "")


def gwips_native_link(rows: list) -> tuple:
    '''
    Link to the curated GWIPS-viz tracks of the first of the given GWIPS rows.

    One assembly per link, so a study whose samples span several gets the
    first row in table order, as the custom-track side does for organisms.
    '''
    rows = [r for r in rows if r.gwips_db and
            (r.GWIPS_Elong_Suffix or r.GWIPS_Init_Suffix)]
    if not rows:
        return GWIPS_HOME, ""
    first = rows[0]
    tracks = [t for t in (first.GWIPS_Elong_Suffix, first.GWIPS_Init_Suffix) if t]
    params = ''.join(f'&{track}=full' for track in tracks)
    return (f"https://gwips.ucc.ie/cgi-bin/hgTracks?db={first.gwips_db}{params}",
            'Visit GWIPS-viz')


def _as_dict(trips, gwips, gwips_native, ribocrypt) -> dict:
    return {
        'trips_link': trips[0], 'trips_name': trips[1],
        'gwips_link': gwips[0], 'gwips_name': gwips[1],
        'gwips_native_link': gwips_native[0],
        'gwips_native_name': gwips_native[1],
        'ribocrypt_link': ribocrypt[0], 'ribocrypt_name': ribocrypt[1],
    }


def _rows_by_run(model, runs: list) -> dict:
    by_run: dict = {}
    for i in range(0, len(runs), CHUNK_SIZE):
        chunk = runs[i:i + CHUNK_SIZE]
        for row in model.objects.filter(Run__in=chunk).order_by('pk'):
            by_run.setdefault(row.Run, []).append(row)
    return by_run


def _gwips_by_project(projects: list) -> dict:
    '''
    GWIPS rows keyed by BioProject: the native tracks are per study, not
    per run.
    '''
    by_project: dict = {}
    for i in range(0, len(projects), CHUNK_SIZE):
        chunk = projects[i:i + CHUNK_SIZE]
        for row in GWIPS.objects.filter(BioProject__in=chunk).order_by('pk'):
            by_project.setdefault(row.BioProject, []).append(row)
    return by_project


def sample_links(samples, selection: dict = None) -> tuple:
    '''
    Links for each sample, and combined links for all of them together
    (used as the study-level buttons).

    Arguments:
    - samples: Sample objects
    - selection (dict): links-page parameters that select these samples,
      e.g. {'bioproject': ['PRJNA1']}; needed for the combined genome
      browser link, which is left out without it

    Returns:
    - (dict): run -> link dict
    - (dict): link dict covering all the samples
    '''
    samples = list(samples)
    runs = _unique(s.Run for s in samples)
    projects = _unique(s.BioProject_id for s in samples if s.BioProject_id)
    trips_rows = _rows_by_run(Trips, runs)
    ribocrypt_rows = _rows_by_run(RiboCrypt, runs)
    gwips_rows = _gwips_by_project(projects)

    per_run = {}
    browser_organism = None
    for s in samples:
        link = genome_tracks.run_link(s)
        if link and browser_organism is None:
            browser_organism = s.ScientificName
        per_run[s.Run] = _as_dict(
            _trips(trips_rows.get(s.Run, [])), _gwips(link),
            gwips_native_link(gwips_rows.get(s.BioProject_id, [])),
            _ribocrypt(ribocrypt_rows.get(s.Run, [])))

    all_trips = [row for run in runs for row in trips_rows.get(run, [])]
    all_ribocrypt = [row for run in runs for row in ribocrypt_rows.get(run, [])]
    all_gwips = [row for project in projects for row in gwips_rows.get(project, [])]
    # One organism per link: the first with tracks
    combined_link = None
    if browser_organism and selection:
        combined_link = genome_tracks.selection_link(browser_organism, selection)
    combined = _as_dict(_trips(all_trips), _gwips(combined_link),
                        gwips_native_link(all_gwips), _ribocrypt(all_ribocrypt))
    return per_run, combined


def attach_links(samples, selection: dict = None) -> dict:
    '''
    Set trips_link, trips_name, etc. on each sample, as the templates expect.

    Returns:
    - (dict): link dict covering all the samples (see sample_links)
    '''
    samples = list(samples)
    per_run, combined = sample_links(samples, selection)
    for s in samples:
        for key, value in per_run[s.Run].items():
            setattr(s, key, value)
    return combined
