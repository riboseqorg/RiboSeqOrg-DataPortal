# Metadata rebuild

Rebuilds the portal's `main_sample`, `main_study` and `main_opencolumns`
tables from SRA, keeping the curation work that exists. It replaces the chain
`Metadata-Curation` (R) → `obtain_live_metadata_set.ipynb` →
`generate_fixtures.py`, which caused the problems described in
`audit/metadata-audit.md`.

The current database is never modified. The output is a new `db.sqlite3` plus
CSVs and a summary, for review before swapping it in.

## Why a rebuild

| Problem in the current DB | Cause | Fix here |
|---|---|---|
| `NA_x`, `xNA`, `NANA`, `x_x`, values glued with no separator (`U-2OSepithelial`) | `metadata_cleanup_columns.R` joins synonym columns with `paste(sep = "_")` (a missing value becomes `NA`), then strips NAs with a regex that can't undo the join | Values are cleaned before they are combined, and joined with `; ` (`merge.py`) |
| Sample attributes attached to the wrong run in 229 projects (e.g. two GSMs for one sample) | ORFik's `rich.format` binds one attribute row per experiment onto one row per run | Every project is re-fetched; attributes are attached to each run (`fetch.py`) |
| `0.0` in every empty field, CONDITION `Test` for ~6,000 samples, 1,428 samples dropped | The November 2024 DB load | Values come from the sources below, not from that load |
| AUTHOR `Makar`, Study_Pubmed_id `1`/`<NA>`, study names like `0.0 et al. 2022` | ORFik falls back to PubMed ID 1 (a 1975 paper by A. B. Makar); pandas `Int64` → `<NA>` | PubMed IDs are resolved through the BioProject UID; placeholders are cleared (`studies.py`) |
| 358 studies (26%) credited to an unrelated paper: `Vogel P, Beyer D, Holm C, Palberg T` on 304, `Shen K,Cheng L,Xu C` on 39, with that paper's title, journal and DOI, and names like `Vogel et al. 2020` | `populate_study_metainfo_dict.py` tests `unique()[0] != np.nan`, which is always true, so a study with no PMID got `PMID = "nan"`; `get_study_metainformation` then ran an Entrez **esearch** for that text and took the first hit — PubMed's newest record that day (the Vogel paper appeared on 2024-11-27, the date of the Nov load) | Nothing is searched by text: PubMed is only ever read by validated ID, every author list records the evidence it came from, and a study with no paper is credited to its submitters (`authorship.py`) |
| Paired-end, non-Illumina, and `Ribo-seq`-strategy runs missing | massiveNGSpipe's processing filter (single-end Illumina only) was used to decide what's in the catalogue | Selection is the Ribo-seq term match from `finding_riboseq.R`, plus the whitelists and manually curated runs; only DNA-type library strategies are excluded |

## Where each value comes from

- **SRA fields** (Run, spots, LibraryStrategy, …): the fresh fetch, as is.
- **Open columns** (Strain, Genotype, Age, …): rebuilt from the fetched
  attributes with the mapping in `resources/Core.csv`, `Open.csv` and
  `Technical.csv`. These columns were never hand-curated, so nothing is lost.
- **Core columns** (LIBRARYTYPE, REPLICATE, CONDITION, INHIBITOR, TIMEPOINT,
  TISSUE, CELL_LINE, FRACTION): the first valid value from:
  1. `manual`: the human-checked rows of the RiboCrypt curation sheet;
  2. `baseline`: the October 2024 DB (`git show edff627d:riboseqorg/db.sqlite3`),
     the last load before the regression;
  3. `st`: the R pipeline's standardised `_st` values;
  4. `auto`: the same standardisation (a port of ORFik `findFromPath`) run on
     the fresh records;
  5. `assay` (LIBRARYTYPE only): the broader rules in `assay.py`, from the
     run's own title, library name and library attributes;
  6. `strategy` (LIBRARYTYPE only): SRA's `Ribo-seq` library strategy;
  7. `assay_study` (LIBRARYTYPE only): inferred from the study text, when the
     study describes only one kind of library. Always goes to the review
     queue.

  REPLICATE trusts the manual sheet last, because curators used it for their
  own grouping. In the 229 misaligned projects, `auto` goes before `baseline`
  and `st`, because those were derived from shifted attributes.
  `samples.csv` records the source of every value (`_source_<column>`).
- **Validation** (`core.py`): recoverable artefacts are repaired
  (`NA2hr` → `2hr`, `CT00NANANA` → `CT00`), and placeholders (`Test`,
  `NONE`) are rejected. Strains in CELL_LINE (`C57BL/6`, `BY4741`, …) move
  to Strain. LIBRARYTYPE and FRACTION only accept their controlled
  vocabularies, so library descriptions no longer sit in FRACTION.
- **Display names** (`resources/display_names.csv`): `RFP` → `Ribo-Seq`,
  `chx` → `Cycloheximide`, and so on. The original mapping sheet is lost; this
  one was rebuilt from the historical data (each mapping held for 100% of
  samples), plus a few curator abbreviations. Edit it to change a display
  name.
- **Portal flags** (trips_id, gwips_id, ribocrypt_id, verified,
  process_status, FASTA_file): carried over from the current DB, or the
  October 2024 DB for restored runs.
- **The paper and its authors**: never inherited from the current DB, always
  re-resolved from evidence. See below.

## Who owns a dataset (`authorship.py`)

A study's `Authors`, `Publication_title`, `Journal`, `doi`, `PMC` and
`Paper_abstract` all come from one PubMed record or from none: filling them
one field at a time is how the old contamination spread. `Authorship_source`
records which evidence was used, best first:

| Source | Evidence | Confidence |
|---|---|---|
| `manual` | A row in `resources/study_authorship.csv` (`BioProject,PMID,Authors,note`). This is where a curator's answer to a review row goes | Decided by a person |
| `pubmed` | A PubMed ID that NCBI's `elink`, GEO's own series record or ENA's project XML ties to this data — or one whose authors are the submitters | Linked by a repository |
| `sra_pmid` | A PubMed ID only the SRA records carry. Plausible, nothing confirms it | Queued for review |
| `europepmc` | A paper that cites the accession **and** shares authors with the submitters, or an affiliation with the owning institution | Verified citation |
| `submitters` | No paper: the study is credited to the people and institution that submitted it | Ownership, not authorship |
| *(empty)* | Nothing is known. `Authors` stays empty | — |

A Europe PMC citation on its own is never enough, because reanalysis papers
cite accessions too: Pamudurti 2017 cites `PRJEB7207` and Liu & Song cite
`PRJNA156379` without having produced either. Submitter names come from GEO's
`!Series_contributor` and `!Series_contact_name`; institutions from the
BioProject owner, ENA's `SUBMITTER_ID` namespace and SRA's `CenterName`.
Archives that submit on others' behalf (EBI, DDBJ, NCBI) are ignored, since
every ENA study would otherwise look like the EBI's work.

**Display names.** `Ingolia et al. 2011` when there is a paper (with the
paper's year, not the release year); otherwise the institution that submitted
the data — `RIKEN, 2020`, `University of Cambridge, 2017` — which is true
where a guessed author is not. A name a curator wrote by hand is left alone;
only names this pipeline could have produced itself are regenerated.

**Guard.** A build stops if one author list appears on more than five studies
that do not agree on a single PubMed ID. That is exactly what the
`esearch("nan")` bug looked like, and run against the current database it
catches all three strings (Vogel 304 studies, Shen 39, Theofanidis 15). A
real group with several datasets under one paper does not trip it. `verify` repeats it on the built database, together with
checks for a paper with no PMID and authors with no recorded source.

Roughly four or five lookups per study, so the first pass over the catalogue
takes about half an hour without an NCBI API key. Answers are cached under
`build/metadata_rebuild/authorship_cache` (one JSON file per project and per
series), so later rebuilds are fast and `--offline` repeats them exactly.
`--no-europepmc` skips the citation search.

`authorship_queue.csv` lists every study a person still has to settle, with
the candidate papers, the reason each was accepted or rejected, and empty
`decision_PMID` and `decision_Authors` columns to fill in and paste into
`resources/study_authorship.csv`.

## Data type (`assay.py`)

ORFik's matcher only answers when exactly one vocabulary term matches, so it
left 1,932 runs with no LIBRARYTYPE (`RIBOseq Ba/F3 Rpl22`, `ribo_DOX_3`).
`assay.py` applies ordered rules instead, most specific first:

| Label | Recognised from |
|---|---|
| Ribo-tRNA-Seq, tRNA-Seq | ribosome-bound tRNA capture, `tRNA-seq` |
| Mito-Ribo-Seq | `MitoRibo`, `MitoIP-Ribo`, mitoribosome |
| Disome-Seq, Polysome-Seq | `disome`, heavy/light polysome, "associated with >7 ribosomes" |
| RiboTag | RiboTag, TRAP, translating ribosome affinity |
| Selective Ribo-Seq | selective/proximity-specific profiling: IP and pulldown runs; `total`/`input` runs in the same study are Ribo-Seq |
| RNA-Seq | `RNA-seq`, `input`, total RNA, polyA, transcriptome, ribo-depleted |
| Ribo-Seq | footprint, RPF, ribosome-protected, `riboseq`, `ribo`, 80S, monosome, footprint size ranges (`frac_26-34nt`) |

Order matters: footprint wording beats `mRNA` (so "ribosome-protected mRNA
fragments" is Ribo-Seq), and `input` beats generic ribosome wording (so
"input mRNA for Ribosome Profiling" is the RNA-seq control). The run's own
title, library name and library attributes are read first; `source_name` and
treatment are only a fallback, because GEO's source describes the starting
material for every library in a study ("Liver Total RNA").

Measured against the 5,400 runs curators labelled by hand: 98.5% agreement
for run-level rules (most of the rest are this being more specific, e.g.
Disome-Seq inside Ribo-Seq), 100% for the selective-profiling rule (77 runs),
and 93.5% for study-level inference, which is why those runs are queued for
review.

A genomic MNase-seq or ATAC-seq library is not RNA and is excluded from the
catalogue, with the reason recorded in `excluded_runs.csv`.

## Running it

One command rebuilds everything, from `scripts/`:

```bash
python -m metadata_rebuild.pipeline               # fetch, build, verify
python -m metadata_rebuild.pipeline --install     # ... and install it live
python -m metadata_rebuild.pipeline --skip-fetch  # reuse the SRA cache
```

Steps, each usable on its own (`python -m metadata_rebuild.<step> --help`):

| Step | What it does |
|---|---|
| `baseline` | Extracts the October 2024 database from git (`edff627d`), the last load before the regression |
| `fetch` | Downloads SRA records for every Ribo-seq BioProject. Incremental, resumable, and safe to re-run; hours without an NCBI API key, so pass `--api-key` if you have one |
| `build` | Writes the new database, CSVs and `summary.json` under `build/metadata_rebuild/output` |
| `verify` | Unit tests, then checks the built database: no orphan samples, no placeholder values (`0.0`, `<NA>`, `Test`, `Makar`), no NA artefacts, no paper without a PMID, no author list shared by unrelated papers, integrity check, and no unexplained drop in sample count |
| `install` | Backs up the live database (to `build/metadata_rebuild/db.sqlite3.backup-<date>-<stamp>`) and installs the new one. Skipped automatically if verification found problems |

Nothing but `--install` touches the live database. After installing, run
`python manage.py migrate` in `riboseqorg/`.

```bash
# Tests
python -m unittest metadata_rebuild.test_metadata_rebuild
```

## Inputs

Everything the rebuild needs is in `inputs/` (about 2 MB, gzipped), so it
does not depend on a checkout of Metadata-Curation. `inputs/provenance.json`
records where each file came from, with a checksum of the original.

| File | What it is |
|---|---|
| `ribocrypt_manual_curation.csv.gz` | The RiboCrypt curation sheet: the human-checked (`CHECKED`) rows are the strongest value source |
| `standardized_columns_final_2025-08-30.csv.gz` | The last R pipeline run, for its `_st` values |
| `whitelisted_samples.csv.gz`, `whitelisted_bioprojects.csv.gz` | Runs and projects curators added by hand |
| `misaligned_projects.txt` | The 229 projects whose historical attributes were shifted by the ORFik bug; precomputed so the old SraRunInfo folder isn't needed |
| `resources/*.csv` | The curation sheets (Core/Open/Technical/Content/Irrelevant) and `display_names.csv` |

`--historical-sra` is optional and only used as a fallback for projects that
fail to fetch.

## Output (`--out`)

| File | Contents |
|---|---|
| `db.sqlite3` | Copy of the current DB with the three tables replaced. Sample IDs are kept for existing runs. Run `python manage.py migrate` on it. |
| `samples.csv` | Every Sample field, plus `_source_<column>` provenance and `_misaligned_project` |
| `studies.csv` | Study rows, including `Submitters`, `Institution`, `Authorship_source` and `PMID_source` |
| `authorship_queue.csv` | Studies whose ownership needs a person: a citing paper that could not be tied to the submitters, a PubMed ID nothing links to the data, or no credit at all. Carries the candidates with the reason each was accepted or rejected, the submitters, the institution, and blank `decision_PMID` / `decision_Authors` columns for `resources/study_authorship.csv` |
| `review_queue.csv` | Runs whose data type needs a curator, with the evidence to decide: why it was flagged, what the rules matched and in which text, the SRA strategy and selection, read length and spots, the sample title, library name, experiment title, design description and construction protocol, the sample attributes, how the rest of the study is labelled with examples, the study title and abstract, and an SRA link. The `decision` column is left blank to fill in |
| `excluded_runs.csv` | Runs in the current or October 2024 DB that are not in the rebuild, and why |
| `summary.json` | Counts, value sources, rejected candidates, spelling merges, study repairs, and a re-run of the audit's `clean_metadata` detector |

## Swapping it in

Review `summary.json` and `excluded_runs.csv`. Then copy `db.sqlite3` over
`riboseqorg/db.sqlite3` and run `python manage.py migrate`. The Trips, GWIPS
and RiboCrypt link tables are carried over unchanged.
