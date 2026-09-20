# RiboSeqOrg Data Portal: code audit

*Audited September 2026, at commit `c77ca018`.*

## Scope and method

- **Covered:** the Django app (views, utilities, models, API, settings, templates, site JS), plus deployment and repo setup.
- **Not covered:** vendored MDB/Bootstrap sources; the `scripts/` notebooks (only skimmed); anything that needs the production data directories (`/home/DATA/...`) or populated Trips/GWIPS/RiboCrypt tables, which are empty in the repo's `db.sqlite3`.
- **Method:** the app was run in a throwaway environment (Django 4.2, Python 3.12, RDG stubbed) against a copy of `riboseqorg/db.sqlite3` (14,004 samples, 931 studies).
- **Confirmed** means the problem was reproduced; everything else comes from reading the code.

## Critical: security

1. **Anyone can write to the database through the API. Confirmed.**
   - `SampleListView` is a `ListCreateAPIView` with no permission settings (`riboseqorg/main/views.py:43`).
   - An anonymous `POST /api/samples/` returned 201 and the sample count went from 14,004 to 14,005.
   - Fix: use `ListAPIView`.
2. **Script injection (XSS) via a crafted link. Confirmed in a browser.**
   - `riboseqorg/main/static/js/RiboSeqOrg.js:13-36` puts URL parameter values into the page with `.html()`.
   - Opening `/samples?Cell-Line=<img src=x onerror=...>` runs the injected script.
   - Fix: build the filter chips with `.text()` or `textContent`.
3. **Production-unsafe settings are committed** (`riboseqorg/riboseqorg/settings.py:30-35`).
   - The file has a hard-coded `SECRET_KEY`, `DEBUG = True` and `ALLOWED_HOSTS = ['*']`.
   - With DEBUG on, every 500 error below would show a full traceback and settings to the public.
   - Fix: load these from environment variables and rotate the key.
4. **`/download_all/` writes a new file to the server's disk on every request** (`riboseqorg/main/views.py:1172-1209`).
   - Nothing ever deletes these files, so anyone can fill the disk. Build the script in memory instead.
   - An unknown `file_type` also causes a 500 (`KeyError`).

## High: broken features (all confirmed)

| Where | What happens | Location |
|---|---|---|
| `/links/` or `/download_all/` with no parameters | 500: `bioproject_query` is never set in the `else` branch | `views.py:874` |
| `/generate-csv/?bioproject=…` | 500: `Bioproject__in` should be `BioProject__in`. This local copy also silently overrides the working one imported from utilities. | `views.py:1136` (defined at `views.py:1107-1137`) |
| Any unknown GET parameter on `/samples` | 500: `KeyError` in `cn[field]` | `utilities.py:159` |
| "Explore" from Studies with the PubMed filter on | 500: `PubMed` is mapped to `PMID`, which isn't a Sample field | `utilities.py:545`, reached from `views.py:852` |
| Studies page PubMed filter | Does nothing: 931 studies with or without it. It checks for `'PMID'` but the URL sends `'PubMed'`. | `views.py:413`, `views.py:425` |
| "Download All Metadata" with values like `C6/36NA` or `PDGF/Cre tumor` | 404 instead of 4 and 3 rows. Values are never URL-decoded; only `+` is swapped for a space. Fix: use `urllib.parse.parse_qsl`. | `utilities.py:521-523` |
| "Download All Metadata" with no filters | 404 "No Samples Selected" | `views.py:1068` |
| `PubMed=Not Available` on the links page | Would filter for studies *with* a PMID, because `"Available" in "Not Available"` is true. From reading the code; the PMID error above crashes first. | `views.py:854` |
| `/Sample/<bad>/custom` | 500 instead of 404: uses `.get()` rather than `get_object_or_404` | `views.py:1229` |
| API `?limit=abc`, `?limit=-5`, `?spots=abc` | 500 each | `views.py:110`, `views.py:83` |
| Test suite | 3 of 4 tests fail with 404: they request `/about/`, but the routes are `about` with no trailing slash | `tests.py:14-23` |

## High: performance and correctness

- **Study pages make database queries for every sample.**
  - `views.py:571` builds Trips, GWIPS and RiboCrypt links one sample at a time, with several queries plus pandas work each.
  - The largest study (PRJNA297288, 884 samples) took **134 seconds** to load locally.
  - Production is likely slower still: it has populated link tables and does filesystem checks.
- **The study-level Trips/GWIPS/RiboCrypt buttons point at the last run, not the whole BioProject.** `urls` is reassigned inside the loop (`views.py:569-573`).
- **The API serializer's field list is shared across requests.**
  - `views.py:106-108` sets `SampleSerializer.Meta.fields` at class level, so concurrent requests can get each other's fields.
  - Each of the 9 `*_link` properties (`models.py:265-299`) checks the filesystem for every serialized row.
- **`/samples` and `/pivot/` load the whole Sample table into memory on each request** (`views.py:372-373`, `views.py:1244-1245`).
  - In pivot, `order_by('?')` asks the database for a random order, so `random.seed(42)` has no effect.
- **Unparseable study release dates are shown as 01/01/2001** (`views.py:504`). That displays a made-up date; show blank instead.
- **The "empty query" check never matches.**
  - `utilities.py:295`, `:337` and `:409` compare `str(query)` to `'<Q: (AND: )>'`, but `str(Q())` is `'(AND: )'`.
  - Separately, a query that matches no samples would raise a `KeyError` at `utilities.py:306`.
- **GWIPS link building is inconsistent.**
  - Links match GWIPS by BioProject only, not organism (`views.py:930`).
  - The inhibitor check uses case-sensitive substrings at `utilities.py:324` but a regex at `views.py:935`.
  - A `for … else` at `utilities.py:365` always appends a "not available" entry.
- **Trips IDs are parsed two different ways:** `x[:-2]` at `views.py:909` and `int(float(x))` at `utilities.py:266`. Not verified, because the local Trips table is empty.

## Medium: the RDG endpoint (`views.py:1303-1529`)

- `RDG` and `matplotlib` are imported when the module loads, but neither is in any requirements file. If they're missing, the whole site fails to start, not just this page.
- There's no limit on sequence length, `transcript_length` or `max_starts`, and each request makes live `gget` calls to Ensembl.
- The pyplot state machine isn't thread-safe under a threaded server.
- In sequence mode the start codons aren't stripped of spaces (`views.py:1362`), so `"ATG, CTG"` won't match `CTG`; gene mode does strip them.
- Raw exception text is sent back and inserted into the page with `innerHTML` (`templates/main/rdg.html:388`). Only the user's own input can reach it, so it's low risk.
- Not verified: the exon-offset logic (`views.py:1440-1453`) for minus-strand genes.

## Medium: deployment and repo hygiene

- **Three requirements files that conflict** (`requirements.txt`, `requirements_alt.txt`, `riboseqorg/requirements.txt`).
  - The root one pins Django 3.2 and pandas 1.1.5, while the code targets 4.1.
  - Between them they're missing matplotlib, RDG and gget. The inner file also lacks DRF and django-filter.
- **The Dockerfile won't produce a working image of your code.**
  - It `git clone`s GitHub instead of copying the local source.
  - It uses Python 3.8 with the root requirements, so it would fail on the RDG import.
  - It runs migrations at build time and serves with `runserver`.
- **Files that shouldn't be in git:**
  - `riboseqorg/db.sqlite3` (10 MB), tracked even though `.gitignore` lists it.
  - The `ribo/` virtualenv symlinks, `.vscode/`, `riboseqorg/downloads/recode.zip`, and 1,118 files under `sqlites/`.
  - The DB has no auth users, and no other committed secrets were found.
- **Server paths are hard-coded** (`/home/DATA/RiboSeqOrg-DataPortal-Files/...`) about 8 times.
  - There are two copies of `generate_link` (`models.py:7`, `views.py:769`) that return different formats: an absolute URL or `""` vs a relative path or `None`.
- **Dead code:**
  - `StudyListView` (its template doesn't exist).
  - `check_custom_track` (wrong directory prefix `[:5]` and `.bw` extension).
  - `handle_trips_urls` (never called).
  - Leftover `print` calls, and duplicate imports at the bottom of `views.py`.
- **Pagination links keep appending `&page=N`**, so the URL grows on every click (`templates/main/samples.html:402-421`).

## Suggested order

1. Security items 1–4: each is small.
2. The 500s in the High table, which are mostly one-line fixes.
3. The Trips/GWIPS/RiboCrypt link-building rewrite. This fixes the study-page slowness, the last-run bug and the GWIPS matching together. It needs real link-table data to verify; see `metadata-audit.md`.
