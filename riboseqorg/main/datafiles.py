'''
Look up processed files under settings.RIBOSEQORG_DATA_DIR.

Files live at <DATA_DIR>/<type dir>/<first 6 chars of run>/<file name>.
Rather than checking each file with os.path.exists, each directory is listed
once and the listing cached for settings.DATA_DIR_LISTING_TTL seconds, so a
page with hundreds of samples costs a handful of listdir calls.
'''
import os
import time

from django.conf import settings

_listings: dict = {}


def files_in(directory: str) -> frozenset:
    '''
    Return the names of the files in a directory (empty if it doesn't exist).
    '''
    now = time.monotonic()
    cached = _listings.get(directory)
    if cached and now - cached[0] < settings.DATA_DIR_LISTING_TTL:
        return cached[1]
    try:
        names = frozenset(os.listdir(directory))
    except OSError:
        names = frozenset()
    _listings[directory] = (now, names)
    return names


def find_run_file(type_dir: str, run: str, suffixes: list):
    '''
    Find the first existing file for a run, trying each suffix in order.

    Arguments:
    - type_dir (str): directory for the file type, e.g. 'bams'
    - run (str): the run accession
    - suffixes (list): file name endings to try, e.g. ['.bam', '_1.bam']

    Returns:
    - (str): path relative to RIBOSEQORG_DATA_DIR, e.g. 'bams/SRR123/SRR1234.bam'
    OR
    - (None): if no file exists
    '''
    run = str(run)
    prefix = run[:6]
    names = files_in(os.path.join(settings.RIBOSEQORG_DATA_DIR, type_dir, prefix))
    for suffix in suffixes:
        if run + suffix in names:
            return f"{type_dir}/{prefix}/{run}{suffix}"
    return None


def clear_cache():
    _listings.clear()
