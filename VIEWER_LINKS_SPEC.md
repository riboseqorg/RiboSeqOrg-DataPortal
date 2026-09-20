# Spec: populate the Trips-Viz, GWIPS-viz and RiboCrypt link tables

Written 2026-09-20. Branch: `sync-prod`.

> **Status, 2026-09-20.** Trips-Viz and GWIPS-viz are **done and loaded into the committed
> `db.sqlite3`** (§3a, §3b). RiboCrypt is **deferred to the next release**, waiting on a verified
> list of RiboCrypt's own library names — the groundwork is in §3c and the source file is in the
> repo. Everything below is kept as written; the per-section notes say what landed.

## 1. Why

*(As of writing. `main_trips` and `main_gwips` are now loaded; `main_ribocrypt` is still empty.)*

The `main_trips`, `main_gwips` and `main_ribocrypt` tables are **empty**, locally and on the live
site. The links page therefore shows placeholders today, e.g. on
`https://rdp.ucc.ie/links/?run=ERR1994961`:

```
href="https://trips.ucc.ie/None of the Selected Runs are available on Trips-Viz//interactive_plot/?..."
href="https://gwips.ucc.ie/cgi-bin/hgTracks?db=&..."
```

The portal holds 20,055 runs with an accession. The job is to fill these three tables, and to give
GWIPS links two levels: a custom track built from the run's own bigWigs (works now), and a link into
GWIPS-viz's own tracks for studies that are fully loaded there (not built yet).

## 2. Where things stand

| Piece | State |
|---|---|
| `main/genome_tracks.py` | Builds GWIPS **custom track** links from each run's bigWigs. Working. `GENOME_ASSEMBLIES` maps 21 organisms to assemblies, marked UNVERIFIED in the code. |
| `main/viewer_links.py` | Builds per-run and combined links. Trips and RiboCrypt come from the DB tables; GWIPS comes only from `genome_tracks` — **the `GWIPS` model is not used at all**. |
| `main/management/commands/load_viewer_links.py` | Loads Trips from a Trips-Viz sqlite; GWIPS and RiboCrypt from CSVs whose columns are the model fields. Dry run unless `--apply`. |
| `main/management/commands/sync_bigwig_flags.py` | Sets `Sample.gwips_id` from bigWig availability. Must run on the server. |
| `Sample.trips_id` / `gwips_id` / `ribocrypt_id` | Availability flags used by the filters on `/samples`. Currently set for 2,445 / 2,982 / 11,103 samples in the local DB. Provenance unknown — see open questions. |

### Data sources on hand

| Source | Location | What it gives |
|---|---|---|
| Trips-Viz DB | `~/rdp-prod-snapshot-2026-09-19/trips.sqlite` (from `/home/DATA/www/tripsviz/tripsviz3.6/trips.sqlite`) | **Confirmed current** — the file's 2022-07-25 mtime is when it was last written, not a stale copy. `files` (12,273 rows), `studies` (369), `organisms` (49). Public riboseq files give 2,586 run accessions, **2,551 of which are in the portal (12.7% of runs)**. |
| GWIPS trackDb dump | `~/rdp-prod-snapshot-2026-09-19/gwips_trackDb.tgz` | `gwips_dbDb.tsv` (assemblies: name, organism, scientificName, taxId, active) and 32 `gwips_trackDb_<db>.tsv` files (5,347 rows; columns `db, tableName, shortLabel, longLabel, type, grp, settings, html`). 4,620 rows are in ribo/mRNA groups (`RP-ElongatingRibos`, `RP-InitiatingRibos`, `Ribo-Coverage`, `mRNA-Coverage`). |
| bigWigs | server, `/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg/bigwig/<run[:6]>/<run>.{forward,reverse}.bw` | 4,806 files, so roughly 2,400 runs. |
| RiboCrypt | `scripts/viewer_links/inputs/ribocrypt_live_libraries_2026-09-20.csv.gz` (the live list, copied from `~/Downloads/Misc/FINAL_LIST.csv`; provenance in the same directory) | 13,617 runs over 997 study accessions and 87 organisms, one row per library. **13,049 runs are in the portal (65.1%), spanning 946 of 1,401 studies.** Same 48-column schema as `scripts/metadata_rebuild/inputs/ribocrypt_manual_curation.csv.gz`, which is the older (2024-09-13) curation snapshot. |

### The GWIPS trackDb, and why it gives study-level links

Study accessions appear in the `longLabel` column (345 of hg38's rows) and in `html` (141), not in a
column of their own. For example:

```
hg38  Cenik15_All_ribopro_track  Cenik 2015  Ribosome profiles from Cenik et al. (2015) study,  SRP055009,  added 2015-10-28  RP-ElongatingRibos
hg38  Battle15_All_ribocov_track Battle 2015 All riboseq coverage data from Battle et al. 2015.,  SRP047476,  added 2015-10-27  Ribo-Coverage
```

So an SRP or GSE in a `longLabel` maps a GWIPS track table to a portal study, and the `_All_*_track`
tables are exactly the study-level aggregate tracks. This matches the existing `GWIPS` model:
`BioProject, Organism, gwips_db, GWIPS_Elong_Suffix, GWIPS_Init_Suffix`.

## 3. What to build

### 3a. Trips-Viz — **done**
Loaded: **2,551 rows** covering 2,551 runs across 86 studies, and `Sample.trips_id` synced to
match (2,445 -> 2,551).

The loader already exists and the sqlite on hand is the current Trips-Viz database, so this was
a run-and-check job.

- Run `load_viewer_links --trips-sqlite ~/rdp-prod-snapshot-2026-09-19/trips.sqlite` as a dry run,
  then with `--apply`.
- Match the link format Trips-Viz itself produces. A real link looks like:

  ```
  https://trips.ucc.ie/homo_sapiens/Gencode_v25/interactive_plot/
    ?files=462,461,453,451,
    &ribo_studies=31,89,90,99,...,1498,
    &tran=ENST00000558401
    &minread=5&maxread=150&user_dir=fiveprime&ambig=F&cov=F&lg=T&nuc=F&rs=0&crd=F
  ```

  `_trips()` currently emits only `?files=<ids>`. Decide which of the rest to add:
  - `minread=5&maxread=150&user_dir=fiveprime&ambig=F&cov=F&lg=T&nuc=F&rs=0&crd=F` are plot
    settings. Sending them pins what the user sees instead of leaving it to Trips-Viz's defaults —
    worth doing, as a named constant.
  - `tran=` is the transcript to open on. The portal has no transcript in hand for a run-level
    link, so leave it off and let Trips-Viz land on its default; add it only if a transcript-level
    entry point is wanted later.
  - `ribo_studies=` is Trips-Viz's own study-id list (sidebar selection), not something the portal
    holds. Leave it off unless a link without it opens in the wrong state — check this when
    verifying.
  - Note the trailing comma after the last file id in real links; harmless, but match it if
    Trips-Viz is fussy.
- Confirm a handful of runs across more than one organism open a working plot.
- Decide whether to include `rnaseq` and `tcp-seq` files or only `riboseq` (`--trips-types`,
  default `riboseq`).

### 3b. GWIPS-viz, two buttons — **done**
Loaded: **115 rows for 113 studies** (2,609 runs), 12 of them with initiating tracks.
`Sample.gwips_id` is deliberately **not** synced from this table — it means "has bigWigs", which is
what the custom tracks need, and `sync_bigwig_flags` owns it. The loader warns if you ask.

Coverage is limited by the dump, not the matching: of 4,513 ribo/mRNA track rows only **803 name a
study accession** at all, and 272 of those are studies the portal doesn't hold. Widening the group
filter beyond the four canonical groups was tried and adds nothing — the accession is the
bottleneck, so a live MySQL read or a mapping from the GWIPS maintainers is the way to do better.

The two link kinds are complementary, so show **both** rather than picking one:

**Button 1, custom tracks from bigWigs — already works.** Per-run coverage from the portal's own
processing, built by `genome_tracks.py` for any run with bigWigs whose organism is in
`GENOME_ASSEMBLIES`. Label it as the portal's own tracks, e.g. "View tracks in GWIPS-viz".

**Button 2, native GWIPS tracks for loaded studies — to build.** The curated aggregate tracks
GWIPS-viz already hosts for that study. Label it "Visit GWIPS-viz".

1. Write a loader that reads the trackDb dump (a directory of TSVs, or a live MySQL connection to
   the GWIPS database) and produces `GWIPS` rows:
   - Keep rows whose `grp` is one of the ribo/mRNA groups.
   - Pull SRP/GSE/PRJ accessions out of `longLabel`, falling back to `html`.
   - Map the accession to a portal `Study`. The `Study` model holds those accessions; check which
     fields are populated before deciding the match order.
   - Prefer the `_All_*_track` aggregates, splitting elongating (`RP-ElongatingRibos`) from
     initiating (`RP-InitiatingRibos`) into `GWIPS_Elong_Suffix` and `GWIPS_Init_Suffix`.
   - Take `Organism` and `gwips_db` from `db` plus `gwips_dbDb.tsv`, and use the same file to confirm
     the hard-coded `GENOME_ASSEMBLIES` entries (`active` flag included).
2. Change `viewer_links._gwips()` to return **two** links rather than one. It currently returns
   `(link, name)` and the templates key off `gwips_name`; the smallest change that keeps that
   working is to add `gwips_native_link` / `gwips_native_name` alongside the existing
   `gwips_link` / `gwips_name`, and render a second button only when the native link is set.
   Native link format: `…/cgi-bin/hgTracks?db=<gwips_db>&<table>=full`.
3. Study-level buttons: decide what happens when a study's samples span several assemblies. The
   custom-track side already picks one organism (the first with tracks); the native side should
   do the same, or show one button per assembly.

### 3c. RiboCrypt — **deferred to the next release**
Waiting on a verified list of RiboCrypt's own per-study library names. Until then nothing is
loaded, `main_ribocrypt` stays empty, and the links keep falling back to the RiboCrypt home page,
which is the existing behaviour. Everything below stands and is ready to build on.

The live list is now in the repo (see §2), so this is buildable. Target URL format, as RiboCrypt
itself produces:

```
https://ribocrypt.org/?dff=GSE1234123-homo_sapiens&library=RFP_KO_CLUH_r1,RFP_WT_r1,RFP_WT_r3
```

**Column mapping** (CSV column -> `RiboCrypt` model field):

| Model field | From | Notes |
|---|---|---|
| `Run` | `Run` | 13,617 rows, all distinct; 13,049 are portal runs |
| `BioProject` | portal `Sample.BioProject`, as `read_trips()` does | The CSV's own `BioProject` column agrees with the portal on **every** overlapping run, so either works |
| `ribocrypt_id` | `study_accession` | This is the `dff` prefix. Mixed `PRJ*` (10,661 rows) and `GSE*` (2,953) — use it verbatim, do **not** normalise to BioProject, or `dff` stops resolving |
| `Organism` | `ScientificName` | RiboCrypt's own organism naming, which is not always the portal's: it includes hybrids like `Homo sapiens x Vaccinia virus`. Take it from the CSV, lowercase-and-underscore it at link time as `_ribocrypt()` already does |
| `library` | **new field, see below** | Needed for the `library=` parameter |

**The model needs a `library` field and a migration.** `_ribocrypt()` currently puts run accessions
in `library=`; RiboCrypt expects its own library names (`RFP_KO_CLUH_r1`), so every link built today
would be wrong even with the table filled.

**Reconstructing the library name.** The CSV's `name` column is *not* it — `name` is a raw join of
all ten metadata columns with empty slots kept, used for the duplicate check:

```
name = LIBRARYTYPE_BATCH_REPLICATE_TIMEPOINT_TISSUE_CELL_LINE_CONDITION_GENE_FRACTION_INHIBITOR
       e.g. RFP__1____KO_dhh1__chx      (REPLICATE renders as "NA" when blank)
```

RiboCrypt's display names come from ORFik's `bamVarName`, which applies two rules
(confirmed against the ORFik source):

- **Drop constant columns.** A column is included only if it has more than one distinct value
  within the experiment — the experiment being one `(study_accession, ScientificName)` group.
- **Replicate goes last, prefixed `r`.** `1` -> `r1`. Empty values are skipped, with `_` inserted
  only between two non-empty parts.

Grouping the list by `(study_accession, ScientificName)` gives **1,058 experiments**, and this
reconstruction produces a **unique name within every one of them** — no collisions. Examples:

```
GSE87892   / S. cerevisiae : RFP_r1, RFP_r2, RFP_r3          (only REPLICATE varies)
GSE91068   / S. cerevisiae : RFP_SD, RFP_MetR                (only CONDITION varies)
PRJNA727298/ H. sapiens    : RFP_WT_dmso_r1, RFP_KD_HSP70_dmso_r1, ...
```

**The one thing to verify before loading:** ORFik core only orders `libtype, condition, stage,
fraction, rep`. The RiboCrypt schema adds `gene`, `inhibitor`, `batch`, `timepoint`, `tissue` and
`cell_line`, and where those sit is inferred, not confirmed. The example URL
(`RFP_KO_CLUH_r1` = libtype, CONDITION, GENE, replicate) fits the assumed order, but a wrong
position gives a plausible-looking name that RiboCrypt will not resolve. Check a handful of
multi-column studies against live RiboCrypt — or, better, ask for RiboCrypt's own library names
per study, which removes the guesswork entirely.

**Also fix while here:** `_ribocrypt()` emits `&go=TRUE&go=TRUE` (duplicated). The example URL
carries no `go` parameter at all — check whether it is needed.

## 4. Deliverables
- [x] `load_viewer_links --gwips-trackdb` builds `GWIPS` rows from a trackDb dump (a directory of
  TSVs, or the .tgz), dry run by default.
- [ ] A `library` field on the `RiboCrypt` model plus its migration, and a reader for the live list
  (§3c) — the existing `--ribocrypt-csv` expects the model's columns, not these 48. **Next release.**
- [x] `main_trips` and `main_gwips` populated in the committed `db.sqlite3`; migrations 0002 and
  0003 applied, which the committed database was missing.
- [x] `viewer_links` gives GWIPS two links, `gwips_link` (custom tracks) and `gwips_native_link`
  (curated study tracks), rendered as two buttons on the sample, study and links pages.
- [ ] RiboCrypt links from library names rather than run accessions. **Next release**, along with
  the duplicated `&go=TRUE&go=TRUE`.
- [x] Tests in `main/tests.py`: accession parsing from `longLabel` and `html`, aggregate-vs-sample
  track choice, tarball input, the native/custom split, and the empty-table fallback. 44 pass.
- [ ] A short section in the repo docs on refreshing each table, and how often.

## 5. Acceptance
- [x] `/Study/<bioproject>/`, `/Sample/<run>/` and `/links/` render both GWIPS buttons where the
  data supports them, and no placeholder text. Verified on PRJNA275305 (native hg38 tracks
  `Ji15_All_RiboProElong_track` / `Ji15_All_RiboProInit_track`), PRJNA262009 (Trips) and
  PRJDB10544 as a negative control.
- [x] A study GWIPS has loaded links to the native tracks; one it hasn't falls back to custom
  tracks from its bigWigs. (Custom tracks can only be seen on the server: the bigWigs are not on a
  development machine, so those links render empty locally.)
- [x] Runs with no data in a given viewer still get that viewer's home page.
- [x] Coverage per viewer, against 20,055 runs: **Trips 2,551 (12.7%)**, **GWIPS native 2,609 runs
  / 113 studies (13.0%)**, GWIPS custom tracks ~2,400 runs with bigWigs, **RiboCrypt 0** until the
  next release.
- [x] The pages don't get slower: GWIPS adds exactly **one** bulk query per page, keyed by
  BioProject and chunked at 500, so the study page goes from 4 queries to 5 regardless of how many
  samples it has. The query-count tests assert this.

## 6. Open questions
1. ~~Where is the current Trips-Viz database?~~ **Resolved:** the copy on hand is the current one.
2. **Where do the extra RiboCrypt metadata columns sit in a library name?** See §3c. This is what
   the RiboCrypt work is now waiting on — a verified list of library names settles it.
3. **What populated `Sample.trips_id` / `gwips_id` / `ribocrypt_id`?** Partly answered. `trips_id`
   is now derived from the loaded table (2,551). `gwips_id` is left at 2,982 and still belongs to
   `sync_bigwig_flags`, which has to run on the server. `ribocrypt_id` is still at 11,103 from an
   earlier version of the live list, so the `/samples` RiboCrypt filter currently promises more
   than the links deliver — it should be re-derived when §3c lands.
4. **Is a trackDb dump the right input, or should the loader read the GWIPS MySQL database
   directly?** Still open, and it now has a number attached: the dump yields 113 studies because
   most tracks never name an accession (§3b).
5. **`GENOME_ASSEMBLIES` is UNVERIFIED.** Unchanged. The assemblies need checking against the
   bigWigs' own chromosome names and sizes; `gwips_dbDb.tsv` (now read by the loader for organism
   names) and `audit/performance-info-needed.md` are the starting points. A wrong assembly gives a
   browser view with no data.
6. **Trips IDs are stored as strings and some older loads wrote "1234.0"**
   (`viewer_links.trips_file_id` works around it). The new load writes plain integers, so this only
   matters for databases loaded before today.
7. **Study-level Trips links have no cap.** PRJNA297288 (Atger15) has 884 files, so its study
   button builds a ~5 kB URL; real Trips-Viz links carry a handful. Worth a limit.
8. **568 runs in the RiboCrypt list are not in the portal.** Confirm they are genuinely out of
   scope rather than a sign the portal is missing data.
9. **How often does each source change,** and should refreshing be a cron job on the server or a
   manual step before a deploy? Note that `db.sqlite3` is tracked in git, so anything loaded on the
   server is overwritten by the next deploy unless it's also loaded locally and committed — which
   is why both tables were loaded locally.

## 7. Starting points
- `riboseqorg/main/viewer_links.py` — link building: `_trips()`, `_gwips()` (custom tracks),
  `gwips_native_link()` (curated tracks), `_ribocrypt()` (still to change)
- `riboseqorg/main/genome_tracks.py` — custom tracks, `GENOME_ASSEMBLIES`
- `riboseqorg/main/management/commands/load_viewer_links.py` — `read_trips()`,
  `read_gwips_trackdb()`, `study_accession_index()`, `read_csv()`
- `riboseqorg/main/models.py` — `Trips`, `GWIPS`, `RiboCrypt`
- `riboseqorg/main/templates/main/links.html`, `sample.html`, `study.html` — where the links
  are shown; the two GWIPS buttons live in all three
- Data: `~/rdp-prod-snapshot-2026-09-19/{trips.sqlite,gwips_trackDb.tgz}` and
  `scripts/viewer_links/inputs/ribocrypt_live_libraries_2026-09-20.csv.gz`
- Related: [PY310_MIGRATION.md](PY310_MIGRATION.md) for the deployment side

## 8. Reloading, for the record
Both tables were loaded locally against the committed `db.sqlite3`, because a deploy overwrites
whatever is on the server. To redo it:

```
cd riboseqorg
python manage.py migrate main
python manage.py load_viewer_links \
    --trips-sqlite ~/rdp-prod-snapshot-2026-09-19/trips.sqlite \
    --gwips-trackdb ~/rdp-prod-snapshot-2026-09-19/trackdb \
    --apply --sync-flags
```

Drop `--apply` for a dry run, which reports row counts, skip reasons and how each table compares
with the `Sample` availability flags. `--gwips-trackdb` takes either the extracted directory or
`gwips_trackDb.tgz` itself.
