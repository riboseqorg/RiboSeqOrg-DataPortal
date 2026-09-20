# Performance work: information needed

*September 2026. Covers the speed changes made in the working tree on top of commit `c77ca018`.*

This file lists what is still needed to finish and verify the speed work, and what was done without it. **Sections 1–3 are the open requests.** Everything was tested against a mock copy of the database (see section 5), because production's link tables are empty.

## 1. Information needed

### 1.1 Trips-Viz / GWIPS-viz / RiboCrypt link data (most important)

**Problem:** the production database has the same contents as `riboseqorg/db.sqlite3`, and the `main_trips`, `main_gwips` and `main_ribocrypt` tables in it are **empty**. Nothing in the repo loads them. So on the live site every Trips-Viz, GWIPS-viz and RiboCrypt button shows as unavailable (greyed out), even though samples are flagged as available: 2,441 for Trips, 2,961 for GWIPS and 11,094 for RiboCrypt.

Status by viewer:

| Viewer | Status |
|---|---|
| Trips-Viz | **Source found; load ready.** See 1.1a. |
| Genome browser (was GWIPS-viz) | **Built from bigWigs; needs the assemblies confirmed.** See 1.1b. |
| RiboCrypt | **Still needed.** See 1.1c. |

All three are loaded with one command, which is a dry run unless `--apply` is given:

```bash
python manage.py load_viewer_links --trips-sqlite trips.sqlite [--gwips-csv gwips.csv] [--ribocrypt-csv ribocrypt.csv] [--apply] [--sync-flags]
```

`--sync-flags` also resets `Sample.trips_id` / `gwips_id` / `ribocrypt_id` from the loaded tables, so the flags and links can't disagree. It changes Sample rows, so coordinate with any metadata work on the database.

#### 1.1a Trips-Viz: source found

The loader reads the Trips-Viz database directly (`~/rdp-prod-snapshot-2026-09-19/trips.sqlite`): public studies and organisms only, matching `files.file_name` (e.g. `SRR3665677.sqlite`) to `Sample.Run`. It was dry-run and applied to a scratch copy:

- **Ribo-seq files:** 2,420 load. **2,418 of the 2,441 flagged runs match.** Of the other 23, 19 aren't in this Trips snapshot and 4 are in private Trips studies.
- **Also available if wanted:** 82 RNA-seq and 26 TCP-seq files for portal runs (`--trips-types riboseq,rnaseq,tcpseq`). **Decision needed:** should RNA-seq and TCP-seq runs get Trips buttons too?
- **Check the snapshot's age:** `trips.sqlite` is dated July 2022 and its newest `UPDATES` entry is 2021-02-22. If Trips has had studies added since, use a newer copy.
- **Not yet verified against the live site:** trips.ucc.ie gave an empty response when tested, so one generated link (e.g. `https://trips.ucc.ie/mus_musculus/Gencode_M14/interactive_plot/?files=857` for SRR2535267) still needs a click-test.
- **For the metadata work:** 27 runs are RNA-seq in Trips but `Ribo-Seq` in the portal's `LIBRARYTYPE`.

#### 1.1b Genome browser links: built from bigWigs

GWIPS links no longer match GWIPS tracks to studies. When a run has bigWigs (`bigwig/<run[:6]>/<run>.forward.bw` / `.reverse.bw`), the portal builds a GWIPS-viz link that loads them as custom tracks (`main/genome_tracks.py`). GWIPS-viz is a UCSC Genome Browser install, so this uses the standard UCSC custom-track format:

- **One run** (sample page, table rows): the track lines are inline in the URL (`hgTracks?db=hg38&hgct_customText=track type=bigWig ...`). Each strand gets a track named `SRR123 fwd` / `SRR123 rev`, a description built from the metadata (e.g. `SRR123 Ribo-Seq, HeLa, CHX (PRJNA1), forward strand`, skipping missing-value markers), blue/red colours, and `visibility=full`.
- **Several runs** (study button, links-page selection): the URL would be too long, so the link points the browser at a text file of track lines served by the portal: `/tracks/ucsc.txt?bioproject=...&organism=...` (same selection parameters as the links page). One link per organism. It shows at most 200 runs, and above 10 runs tracks start `dense`.
- `Sample/<run>/custom` returns the same track lines as text, to paste into a browser.
- The `GWIPS` table is no longer used for links. A link appears whenever the bigWigs exist and the organism has an assembly.
- **Decided:** the "Available on GWIPS-viz" filter on /samples (`Sample.gwips_id`) means "has genome browser tracks". Run `python manage.py sync_bigwig_flags --apply` on the server to set it from the bigWigs on disk (without `--apply` it only reports). Re-run it whenever bigWigs are added. It also lists organisms that have bigWigs but no assembly, e.g. Neurospora crassa and Kluyveromyces marxianus, which GWIPS serves (`Ncrassa_or74a`, `k_marxianus_DMKU3_1042`).

**Needed:**

1. **Confirm the assembly for each organism.** A link is only correct if `db=` is the assembly the bigWigs were aligned to. All links open `gwips.ucc.ie`, using the assemblies it serves (from `gwips_dbDb.tsv`): human `hg38`, mouse `mm10`, yeast `sacCer3`, zebrafish `danRer7`, worm `ce10`, rat `rn6`, fly `dm3`, E. coli `eschColi_K12`, S. pombe `s_pombe`, Arabidopsis `araTha1`, and 11 more.

   rdp.ucc.ie couldn't be reached from here, so this is unverified. On the server, with UCSC's `bigWigInfo` installed, run `python ../audit/perf/check_bigwig_assemblies.py` from `riboseqorg/`. For each organism it compares one bigWig's chromosome names and sizes with the assembly, and prints OK or MISMATCH. Organisms with no mapping get no link: add them to `GENOME_ASSEMBLIES`.
2. **The site must be reachable by GWIPS-viz.** GWIPS-viz fetches the bigWigs and `/tracks/ucsc.txt` from `PUBLIC_BASE_URL` (default `https://rdp.ucc.ie`) themselves. `/static2/` must allow HTTP range requests (nginx does by default). From here, rdp.ucc.ie reset the connection, so if it firewalls outside traffic, the links won't load.
3. **Decisions:**
   - Keep 200 runs and 10-run `full` as the limits?
   - Descriptions list metadata values without labels (e.g. `Leaf, Test, P5-1`). Add labels such as `rep P5-1`?

`gwips_trackDb.tgz` is only needed now for the GWIPS-only assemblies' chromosome sizes. Export `chromInfo` from each of those databases as `<db>.chrom.sizes` and pass `--gwips-sizes DIR` to the check script.

#### 1.1c RiboCrypt: still needed

A CSV with columns `BioProject, Organism, ribocrypt_id, Run`: one row per run in each RiboCrypt experiment. RiboCrypt is built on ORFik, so on the RiboCrypt server `ORFik::list.experiments()` gives experiment names and organisms. Loading each experiment (`read.experiment(name)`) gives its libraries, i.e. run accessions. Also send one working RiboCrypt URL to confirm the `dff=` and `library=` format.

### 1.2 How production runs the site

| Question | Why it matters |
|---|---|
| Which WSGI server (gunicorn / uWSGI / `runserver`?), and how many workers and threads? | Django's cache is in-process (`CACHES` isn't set), so each worker has its own 15-minute page cache. With many workers, a shared cache (file or Redis) would make caching work. |
| Is nginx (or Apache) in front, and does it gzip `text/html`? | `/pivot/` is a **4.9 MB** HTML page. Gzip would make it roughly 10× smaller. If nothing compresses it, Django's `GZipMiddleware` can be enabled instead. |
| Which Django and Python versions are installed? (`pip freeze`) | The three requirements files disagree (Django 3.2 vs 4.1). This affects which fixes are safe, e.g. `GZipMiddleware`'s BREACH mitigation needs Django 4.2+. |

### 1.3 The data directory (`/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg`)

| Question | How to check |
|---|---|
| Is it a local disk or a network mount (NFS/SMB)? | `df -hT /home/DATA` |
| How fast is listing a directory? | `time ls /home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg/bams/SRR253 > /dev/null` |
| Roughly how many files are there per type? | `ls .../bams \| wc -l`, and the same for one sub-directory |

**Why:** file links (reads, BAM, bigWig, reports) used to cost 1–2 filesystem checks each, per sample, per type. On local disk that's cheap. On a network mount it made study pages take minutes: the audit's 134 s figure came from exactly this kind of slow path. File links now use cached directory listings (section 4). The answers decide the cache lifetime, `DATA_DIR_LISTING_TTL`, currently 300 s.

### 1.4 Real-world timings (optional)

These are nice to have, to aim the next round at the pages people actually use:

- nginx access logs with `$request_time` (or gunicorn logs with `%(L)s`) for a typical week, or
- Just a list of the pages that feel slow.

## 2. Decisions for you

1. **Studies with more than one organism** (47 studies; 6 of them on GWIPS). The study-level Trips-Viz, GWIPS-viz and RiboCrypt buttons show a single link, for the first organism only. Should there be one button per organism?
2. **GWIPS track per sample.** Per-sample GWIPS links now always open both the elongation and initiation tracks, as the study and sample pages already did. The links page used to pick one track from the sample's inhibitor (harringtonine or lactimidomycin meant the initiation track), only when opened with `?run=`. Is "both tracks" the right behaviour everywhere?
3. **`/pivot/` sends the whole table (14,004 rows) to the browser.** Keep it (with compression, see 1.2), or cap or sample it?

## 3. Deployment notes for these changes

- **New migration `main/0002_link_lookup_indexes`**: adds indexes on `Sample.Run`, `Trips.Run`, `Trips.BioProject`, `GWIPS.BioProject`, `RiboCrypt.Run` and `RiboCrypt.BioProject`. Run `python manage.py migrate` when deploying. It has **not** been applied to the repo's `db.sqlite3`, which was left untouched because a metadata session is working on it.
- **New optional environment variables:** `RIBOSEQORG_DATA_DIR` (defaults to the current `/home/DATA/...` path) and `DATA_DIR_LISTING_TTL` (seconds, default 300). A newly added file shows a download link within that many seconds.
- The earlier security fixes need `DJANGO_SECRET_KEY` set in production, and `DJANGO_ALLOWED_HOSTS` if the site is served under more than `rdp.ucc.ie`.

## 4. What was changed, and results

| Change | Where |
|---|---|
| Trips/GWIPS/RiboCrypt links built in bulk: one query per link table per page, instead of several queries plus pandas work per sample | `main/viewer_links.py`, used by the study, sample and links views |
| Study-level buttons now cover **every run in the BioProject**, not just the last run in the loop | `main/viewer_links.py` |
| File links check a cached directory listing instead of calling `os.path.exists` per file | `main/datafiles.py`, `models.generate_link`, `views.generate_link`, report links |
| Sample file-link properties are computed once per object, and no longer fetch the Study row each time (they used `self.BioProject` rather than `self.BioProject_id`) | `main/models.py` |
| Indexes on link lookup columns | `main/migrations/0002_link_lookup_indexes.py` |
| `/samples` fetches only the page shown, not all 14,004 rows | `views.samples` |
| `/pivot/` selects only the columns it shows, and its CSV is cached for 15 minutes | `views.pivot` |
| API field selection is per request (it used to change a shared class, so concurrent requests could get each other's fields) | `views.SampleListView` |
| Hard-coded data paths now come from `settings.RIBOSEQORG_DATA_DIR` | settings, models, views, utilities |
| Removed dead code: `handle_trips_urls`, `handle_gwips_urls`, `handle_ribocrypt_urls`, `handle_urls_for_query`, `check_custom_track`, `check_path_exists`, unused query builders | `main/utilities.py`, `main/views.py` |

**Timings.** These are local and use the mock data, with the data directory on a local SSD, which is the best case for the old code. "q" is the number of database queries. The first request of a run includes warm-up.

| Page | Before | After |
|---|---|---|
| Study, 884 samples (PRJNA297288) | 7.15 s, 1,376 q | 0.18 s, 7 q |
| Study, 492 samples (PRJNA232649) | 4.10 s, 3,451 q | 0.08 s, 5 q |
| Study, 376 samples (PRJNA554781) | 2.77 s, 1,886 q | 0.06 s, 4 q |
| Study, 102 samples (PRJNA707431) | 0.75 s, 516 q | 0.02 s, 4 q |
| `/samples` | 0.44 s | 0.07 s |
| `/pivot/` (uncached / cached) | 0.52 s | 0.45 s / ~0 s |

On a slow or network filesystem the gap is much larger. Before, a study page made up to 16 filesystem checks per sample; now it makes one directory listing per run prefix, cached across requests.

**Checks that the output is unchanged.** The old and new code were run against the same mock data, and every link on 5 study pages, 2 sample pages and 4 links pages was compared:

- Per-sample Trips and RiboCrypt links: identical on every page.
- Per-sample GWIPS links: identical, except the `?run=` links-page case described in decision 2.
- Study-level buttons: changed as intended (whole project instead of last run).
- `/samples` pages (5 filter/page combinations) and the `/pivot/` CSV: identical.
- Tests: 31 pass, including new ones that fix the study page at 5 queries whatever the sample count.

## 5. Reproducing the tests

`audit/perf/make_mock.py` fills the three link tables in a **copy** of the database with synthetic rows that agree with each sample's `trips_id`/`gwips_id`/`ribocrypt_id` flags. Never run it on the real database. `audit/perf/bench.py` times the key pages and saves every link they produce to JSON, so two versions of the code can be diffed.

```bash
cp riboseqorg/db.sqlite3 /tmp/mock.sqlite3
python audit/perf/make_mock.py /tmp/mock.sqlite3
# point a scratch copy of the app at /tmp/mock.sqlite3, then from riboseqorg/:
RIBOSEQORG_DATA_DIR=/path/to/mock/files python ../audit/perf/bench.py after.json
```

The mock can't show whether the real Trips, GWIPS and RiboCrypt data matches these assumptions, e.g. whether GWIPS `Organism` values match `ScientificName`. That needs the data in 1.1.
