"""
Time key pages and snapshot the link output they produce.
Usage: python bench.py OUT.json [--skip-big]
"""
import json, os, sys, time
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "riboseqorg.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "bench")
import django
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ['testserver']
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext, setup_test_environment
setup_test_environment()

c = Client(raise_request_exception=True)
out, skip_big = sys.argv[1], '--skip-big' in sys.argv
LINK_KEYS = ['trips_link', 'trips_name', 'gwips_link', 'gwips_name',
             'ribocrypt_link', 'ribocrypt_name']
snap, timings = {}, []


def get(url):
    cache.clear()
    t = time.time()
    with CaptureQueriesContext(connection) as q:
        r = c.get(url)
    dt = time.time() - t
    timings.append((url, r.status_code, len(q), dt))
    print(f"{r.status_code} {len(q):6d} queries {dt:8.2f}s  {url}", flush=True)
    return r


studies = ['PRJNA637713', 'PRJNA707431', 'PRJNA554781', 'PRJNA232649']
if not skip_big:
    studies.append('PRJNA297288')
for bp in studies:
    r = get(f'/Study/{bp}/')
    ctx = r.context
    snap[f'study {bp}'] = {
        'bioproject': {k: ctx[f'bioproject_{k}'] for k in LINK_KEYS},
        'runs': {e.Run: [getattr(e, k) for k in LINK_KEYS] for e in ctx['ls']},
    }

for run in ['SRR2535267', 'SRR11944058']:
    r = get(f'/Sample/{run}/')
    if r.status_code == 200:
        ctx = r.context
        snap[f'sample {run}'] = [ctx[k] for k in
                                 ['trips', 'trips_name', 'gwips', 'gwips_name',
                                  'ribocrypt', 'ribocrypt_name']]

for url in ['/links/?bioproject=PRJNA637713', '/links/?bioproject=PRJNA297288',
            '/links/?run=SRR2535267&run=SRR11944058',
            '/links/?query=Organism%3DHomo+sapiens']:
    r = get(url)
    ctx = r.context
    snap[f'links {url}'] = {
        'trips': ctx['trips'], 'gwips': ctx['gwips'],
        'runs': {e.Run: [getattr(e, k) for k in LINK_KEYS]
                 for e in ctx['sample_results']},
    }

for url in ['/samples', '/samples?Organism=Homo+sapiens&page=3', '/studies',
            '/pivot/', '/api/samples/?limit=100',
            '/api/samples/?limit=100&fields=Run,fastqc_link,reads_link,bam_link']:
    get(url)

json.dump({'snap': snap, 'timings': timings}, open(out, 'w'), indent=1,
          sort_keys=True, default=str)
