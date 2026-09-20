# Finalising the RDP database for release

Status: draft, 2026-09-20. Nothing here is committed.
Related: [scripts/metadata_rebuild/README.md](scripts/metadata_rebuild/README.md),
[VIEWER_LINKS_SPEC.md](VIEWER_LINKS_SPEC.md), [audit/metadata-audit.md](audit/metadata-audit.md).

## Goal

Produce one database that can be installed on rdp.ucc.ie, containing both the
corrected sample selection and the resolved study authorship. Those two things
exist today in two different builds, and neither build is shippable on its own.

The bar is "an improvement with nothing glaringly wrong", not perfection. The
one thing that is glaringly wrong today is that **343 studies are credited to
an unrelated paper**, and that text is rendered on the study page and the
studies list. Everything else below exists to get that fix installed without
regressing anything.

## Where things stand

Verified on 2026-09-20 against the working tree.

| Build | Samples | Studies | Why it can't ship |
|---|---|---|---|
| `riboseqorg/db.sqlite3` (installed) | 20,055 | 1,401 | 343 studies carry fabricated authors; `Submitters`/`Institution` empty for all 1,401 |
| `build/metadata_rebuild/output/` (11:48) | 36,623 | 1,811 | Contaminated: the "Ribo-Zero" selection bug pulled in ~16.5k plain RNA-seq runs |
| `build/metadata_rebuild/check_output/` (13:38) | 20,087 | 1,400 | Built `--offline`, so 930 studies have no `Authorship_source` |

Three sessions wrote `build/metadata_rebuild/` concurrently on 20 Sep and
overwrote each other's output. Two consequences:

- `~/Downloads/RiboSeqOrg_authorship_review_2026-09-20.csv` (502 studies) was
  copied from the **contaminated 11:48 build**. Discard it; do not curate from it.
- `output/` is the contaminated build, not a candidate. Delete it so nobody
  picks it up later.

### Inputs that are settled

These questions were open across sessions and are now answered. Treat them as
locked unless there's a reason to revisit.

| Input | Use | Evidence |
|---|---|---|
| **SRA cache** | `build/metadata_rebuild/sra_cache_v2` | It is the only one with the `experiment_title`, `design_description` and `library_construction_protocol` evidence fields (columns 34–36). `sra_cache` lacks them and is superseded. Both hold 4,582 projects. |
| **Baseline DB** | `edff627d:riboseqorg/db.sqlite3` (Oct 2024) | The last load before the Nov 2024 regression. `pipeline.step_baseline` extracts it. |
| **Vendored dead projects** | `scripts/metadata_rebuild/inputs/legacy_runinfo/` | PRJDB11308 and PRJEB51486 (38 runs) no longer exist in SRA. Without these the rebuild silently drops them. |
| **Authorship cache** | `build/metadata_rebuild/authorship_cache` | 7,479 entries: 1,813 elink, 1,807 ENA, 1,396 GEO, 650 Europe PMC. Keeps a rebuild cheap. See task 1 for the one cache class that must be invalidated. |
| **Trips DB** | `~/rdp-prod-snapshot-2026-09-19/trips.sqlite` | Confirmed current despite its Jul 2022 mtime. |
| **GWIPS trackDb** | `~/rdp-prod-snapshot-2026-09-19/gwips_trackDb.tgz` | 115 native study rows is the ceiling the dump supports, not a matching failure. |

### Fixes already in the code

Do not redo these; they are on disk and tested.

- **Selection** (`build.py:69-74`): `EVIDENCE_FIELDS` are used only to *type* a
  run, never to decide membership, and `NOT_A_RIBO_TERM` rejects
  Ribo-Zero/Ribo-Gold/Ribo-Minus wording. This is what caused the 36,623-sample build.
- **Jump detection** (`pipeline.py:136-141`): verify now fails on a sample-count
  *increase* over 25%, not only a drop. The contaminated build passed because
  the old check only looked downward.
- **Contamination guard** (`authorship.py:594`, `shared_author_strings`): a build
  stops if one author list spans more than five studies that disagree on a PMID.
  Run against the current DB it catches all three bogus strings.

## Work items

### 1. Fix preprint-only acceptances  — blocking, small

`verify` reports `papers without a PMID: 2`. Three studies — PRJNA1032574,
PRJNA566006, PRJNA977618 — have author lists correctly verified against their
submitters, but the source is a **preprint**, which has a DOI and no PubMed ID.
The rule "an author list always comes with a PMID" is too strict.

Three changes:

1. `authorship.py`, `Web.mentions()` (~line 365): the candidate dict does not
   capture the DOI. Add `'doi': h.get('doi', '')` to the dict built from each
   Europe PMC hit.
2. `authorship.py`, the Europe PMC acceptance branch (~line 578, the `else`
   where `best['pmid']` is empty): record `best['doi']` and `best['title']` on
   the `Evidence` object, and surface them through `Evidence.as_row()`. Add a
   `doi` field to `Evidence.__init__`. `Study.doi` and `Study.Publication_title`
   already exist, so no migration is needed.
3. `pipeline.py`, `step_verify`: relax the check to

   ```sql
   select count(*) from main_study
    where PMID = '' and doi = '' and (Authors != '' or Publication_title != '')
   ```

**Cache invalidation.** `Web.cached()` stores the *parsed* candidate list, not
the raw response, so the 650 `epmc_*.json` entries will not contain the new
`doi` key. Delete them before the build:

```bash
rm build/metadata_rebuild/authorship_cache/epmc_*.json
```

Leave the elink, ENA and GEO entries alone — they are unaffected and are most
of the lookup cost.

**Done when:** `step_verify` reports zero problems on a build where those three
studies keep their authors and carry a DOI.

### 2. One clean online build  — blocking, ~2h

The only step that produces a database with both the corrected selection and
full authorship. It must be **one process**, writing to a **fresh directory**,
with **nothing else** running against `build/metadata_rebuild/`.

```bash
cd /Users/jackt/projects/RiboSeqOrg-DataPortal
python -m scripts.metadata_rebuild.pipeline \
  --skip-fetch \
  --cache build/metadata_rebuild/sra_cache_v2 \
  --out   build/metadata_rebuild/release_2026-09 \
  --release 2026.09 \
  --api-key "$NCBI_API_KEY"
```

- `--skip-fetch` because `sra_cache_v2` is complete at 4,582 projects. Do not
  re-fetch; a partial fetch is how runs got dropped before.
- No `--offline`. This is the whole point: the offline candidate is why 930
  studies have no authorship source.
- An NCBI API key triples the request rate and is worth setting; without one
  budget the full ~2 hours.
- **No `--install`** on this run. Inspect first (task 3).

Expect roughly 20,000–20,100 samples and ~1,400 studies. Anything near 36,000
means the selection fix regressed — stop.

### 3. Review the build before installing

Check `release_2026-09/output/summary.json` and the verify log:

- `[verify] ... 0 problems`. Any problem line is a stop.
- Sample count within a few hundred of 20,055.
- `authorship.by_source` has `pubmed` around 900-950 and `none` in single or
  low double digits. If `pubmed` is near zero the run silently went offline
  (network failure returns `''` from `Web._get`, which looks like a miss).
  (The 2026-09 build: 912 pubmed, 356 submitters, 114 europepmc, 18 none.)
- Zero rows match the bogus author strings:

  ```bash
  sqlite3 build/metadata_rebuild/release_2026-09/output/db.sqlite3 \
    "select count(*) from main_study where Authors like '%Vogel P%' \
       or Authors like '%Shen K,Cheng L%' or Authors like '%Theofanidis%';"
  ```

  Must be 0.

### 4. Install and resync the link tables

`write_db` starts from a copy of the live database, so `main_trips`,
`main_gwips`, `main_ribocrypt` and `django_migrations` are inherited — the new
build already carries migrations 0001–0003 and the loaded links. But the sample
set changes slightly, so the link rows and the per-sample flags must be resynced
against the new runs.

```bash
# --install-only, NOT --install: plain --install rebuilds first and would
# throw away the review decisions patched in at task 5.
python -m scripts.metadata_rebuild.pipeline \
  --out build/metadata_rebuild/release_2026-09 --install-only
# then, in riboseqorg/
python manage.py migrate
python manage.py load_viewer_links \
  --trips-sqlite ~/rdp-prod-snapshot-2026-09-19/trips.sqlite \
  --gwips-trackdb ~/rdp-prod-snapshot-2026-09-19/gwips_trackDb.tgz \
  --apply
```

`step_install` backs the live DB up to `build/metadata_rebuild/db.sqlite3.backup-<date>-<ts>` first.

Do **not** pass `--sync-flags`. `Sample.gwips_id` means "this run has bigWigs"
and is owned by `sync_bigwig_flags` on the server; native GWIPS tracks are a
study-level thing and overwriting the flag with them would break the
"Available on GWIPS-viz" filter.

**Done when:** `main_trips` ≈ 2,551, `main_gwips` = 115, no orphan link rows,
44 app tests and 45 rebuild tests pass, and the pages listed in task 7 render.

### 5. Patch in the 62 review decisions  — required, after the build

`check_output/review_queue.csv` holds 62 rows, down from 622 once the v2 SRA
evidence landed: 18 with no data type, 23 typed from study text only, 15 where
SRA says Ribo-seq but the label says RNA-Seq, 6 in studies with no Ribo-seq
signal. Columns carry the evidence needed to decide (`rule_suggestion`,
`rule_evidence`, `library_construction_protocol`, `other_types_in_study`,
`labelled_siblings`, `sra_url`).

**Decided.** All 62 were reviewed by hand: 22 RNA-Seq, 15 Ribo-Seq, 13 SSU,
4 Selective Ribo-Seq, 2 QTI-Seq, and 6 excluded (PRJEB7207 miRNA-Seq runs, not
Ribo-seq). They are stored in `scripts/metadata_rebuild/inputs/review_decisions_2026-09.csv`.
The rebuild has no run-level override for data types, so patch them in after the
build instead of curating into `resources/`.

**Patch, after task 3 and before task 4's `--install`:**

```bash
cd /Users/jackt/projects/RiboSeqOrg-DataPortal
python3 -m scripts.metadata_rebuild.apply_review_decisions build/metadata_rebuild/release_2026-09/output          # dry run
python3 -m scripts.metadata_rebuild.apply_review_decisions build/metadata_rebuild/release_2026-09/output --apply
```

It relabels or removes each run in `db.sqlite3`, `samples.csv` and
`RiboSeqOrg_Metadata_v2026.09.csv`, recomputes `seq_types` and `Samples` on the
affected studies, and saves `db.sqlite3.pre-review-decisions` first. An excluded
run also loses its `main_trips` and `main_ribocrypt` rows, so no link points at
a run that is no longer in the catalogue; the six miRNA runs had none, and the
count is reported. `main_gwips` is untouched on purpose: it is per study, and
PRJEB7207 keeps its curated tracks because its Ribo-seq runs remain. Expect
"62 runs found, 0 not in this build", "0 link rows removed" and the CSVs to
lose 6 rows. The dry run
exits non-zero if any run is missing; a missing run means the release build's
selection differs from the check build, so look before applying.

The install step reads `db.sqlite3` from the output directory, so the patch
must come first. Install with `--install-only`: plain `--install` re-runs the
build and silently discards the patch, as does re-running the pipeline into the
same directory. If either happens, apply the patch again. The queue's leftover 62 rows should not
reappear if the patch was applied, but a fresh `review_queue.csv` will still
list them because the rules are unchanged.

**Still open:** SRR1630811 and SRR1630813 (PRJNA246023) both report 46,414,543
spots. Their titles say QTI-Seq and Ribo-Seq, but one may be a duplicated run.
Check on SRA before release.

### 6. Release artefacts

- Publish `release_2026-09/output/RiboSeqOrg_Metadata_v2026.09.csv` to
  `rdp.ucc.ie/static2/`.
- Add a September 2026 row to the versions table in
  `riboseqorg/main/templates/main/about.html:128`, and move the `Latest` badge
  off November 2024. Leave `Published` on September 2024 — that is the release
  the paper cites. While there, confirm each row's CSV URL matches its label; a
  previous session flagged these as crossed but did not record which.
- `authorship_queue.csv` from the release build is the curation backlog for next
  time. Decisions go in `resources/study_authorship.csv`
  (`BioProject,PMID,Authors,note`), which beats every other source.

### 7. Acceptance gate

Before this goes to prod:

- [ ] `python -m scripts.metadata_rebuild.pipeline ... ` verify: **0 problems**
- [ ] 0 studies matching the Vogel / Shen / Theofanidis author strings
- [ ] `Authorship_source` non-empty for >95% of studies; every author list traceable
- [ ] Sample count within ±5% of 20,055
- [ ] Review decisions applied: `apply_review_decisions` reported 62 found / 0
      missing, and `db.sqlite3.pre-review-decisions` exists beside the build
- [ ] The 6 PRJEB7207 miRNA runs are gone, and no `main_trips` /
      `main_ribocrypt` row references a run that is not in `main_sample`
- [ ] `manage.py check` clean; 44 app tests pass on the pinned Django 3.2.25
- [ ] 45 `scripts/metadata_rebuild` tests pass
- [ ] `main_trips` and `main_gwips` populated and consistent with `main_sample`
- [ ] These render 200: `/`, `/samples`, `/studies`, `/about`, `/search/`,
      `/links/`, `/pivot/`, `/vocabularies/`, `/Study/<id>/`, `/Sample/<run>/`,
      `/api/samples/`
- [ ] A spot-check study that previously showed Vogel — e.g. PRJDB10544,
      "Ribosome profiling in Arabidopsis T87 cultured cells" — now shows either
      its real authors or its submitting institution

### 8. Housekeeping

- **Commit first.** The tree is 66 changed paths plus 1,118 staged `sqlites/`
  deletions, no stashes, no backup branch, zero commits ahead of
  `origin/sync-prod`. Every session that produced it has ended. This should
  happen before any of the above.
- Delete the contaminated `build/metadata_rebuild/output/` and the Downloads CSV.
- `.claude/launch.json` points at venvs under `/private/tmp/.../scratchpad/`,
  which are ephemeral, and three sessions used three different Django versions
  (3.2.25, 4.1.13, 4.2.30). Point it at a real venv on the pinned 3.2.25.
- `/references/` reads a hard-coded `/home/DATA/RiboSeqOrg-DataPortal-Files/...`
  path and 500s anywhere but prod.

## Out of scope

- **RiboCrypt.** Deferred pending a verified sample-name list. `main_ribocrypt`
  is empty while 11,103 samples carry `ribocrypt_id = 1`; `viewer_links._ribocrypt`
  degrades to the RiboCrypt home page rather than a dead deep link, so this is
  not glaring. Next release.
- **omics-extractor integration** — see [audit/omics-extractor-integration-plan.md](audit/omics-extractor-integration-plan.md).
- **Performance work** — see [audit/performance-info-needed.md](audit/performance-info-needed.md).
- Re-fetching SRA. `sra_cache_v2` is complete.

## Risks

| Risk | Mitigation |
|---|---|
| Concurrent builds overwrite each other again | One session owns `build/metadata_rebuild/`; the release build writes to its own `release_2026-09/` directory |
| A network failure mid-build looks like "no paper found" — `Web._get` returns `''` after 4 retries | Check `authorship.by_source.pubmed` in summary.json before installing (task 3) |
| The 2h build is repeated because something small was missed | Do task 1 first; the preprint fix is the only known code change outstanding |
| Link tables drift from the new sample set | Re-run `load_viewer_links --apply` after install (task 4) |
