# RiboSeqOrg Data Portal: metadata audit

*Audited September 2026, using `riboseqorg/db.sqlite3` at commit `c77ca018` (14,004 samples).*

No metadata was changed. Everything here is a suggestion for review.

## How to use the tool

| Command | What it does |
|---|---|
| `python manage.py clean_metadata` | Scans the 41 curated Sample columns and writes suggestions to `riboseqorg/main/metadata_vocabulary.csv`. Read-only: a database checksum was identical before and after. |
| `python manage.py clean_metadata --columns INHIBITOR TISSUE` | Limits the scan to the named columns. |
| `python manage.py clean_metadata --apply` | Applies only rows marked `approved`, in a single database transaction. Every other row is ignored. |

Run the commands from `riboseqorg/`. The code lives in:

- `riboseqorg/main/metadata_cleaning.py` (rules)
- `riboseqorg/main/management/commands/clean_metadata.py` (command)
- `riboseqorg/main/test_metadata_cleaning.py` (13 tests)

The vocabulary CSV has one row per (column, value) that was flagged. Its columns are `column, value, suggestion, rule, rows, status, note`.

- To review, set `status` to `approved` or `rejected`, and edit `suggestion` if needed.
- An empty `suggestion` means "treat as missing" (store `''`).
- Re-running the scan keeps your statuses, suggestions and notes, and refreshes the counts. A value that no longer occurs keeps its row, with `rows=0`.
- Synonyms and moves the rules can't detect can be added by hand as extra rows. `--apply` handles them the same way.

Only the manually curated columns are scanned. SRA run-info fields (Run, accessions, dates, library info) are copied verbatim from the archive and left alone.

## Summary

The current file has 286 suggestions, all `proposed`:

| Rule | What it catches | Distinct values | Samples affected |
|---|---|---|---|
| `missing_marker` | `0.0`, `none`, `NANA`, `Null`, `na` used for "no value" | 49 | nearly every sample, in 39 of 41 columns |
| `na_prefix` | `NA_` joined onto a value, e.g. `NA_Primary hippocampal neurons` | 136 | 736 |
| `spelling_variant` | Case, whitespace or `1.0`/`1` variants of the same value; suggests the most common spelling, or the integer form | 41 | 6,355 |
| `na_suffix` | `NA` appended to a number, e.g. `2NA`, `1.0NA`; words like `mRNA` are excluded | 27 | 206 |
| `duplicated_join` | A value repeated twice, joined by `_`, e.g. `sty1delta_sty1delta` | 26 | 357 |
| `na_prefix+na_suffix` | Both at once, e.g. `NA_1NA` → `1` | 4 | 31 |
| `whitespace` | Leading, trailing or doubled whitespace | 3 | 24 |

`BATCH` and `Monosome_purification` are empty for every sample.

## Per column

"Missing" counts samples whose value is `''` or a missing marker. "Other suggestions" covers every rule except `missing_marker`.

| Column | Missing (of 14,004) | Other suggestions: values | Other suggestions: samples |
|---|---|---|---|
| SgRNA | 13,982 | 1 | 2 |
| Disease | 13,976 | 0 | 0 |
| Ethnicity | 13,976 | 1 | 4 |
| SiRNA | 13,970 | 0 | 0 |
| Antibody | 13,949 | 0 | 0 |
| microRNA | 13,948 | 0 | 0 |
| Host | 13,937 | 1 | 8 |
| ShRNA | 13,934 | 0 | 0 |
| Nuclease | 13,930 | 0 | 0 |
| UMI | 13,919 | 0 | 0 |
| Kit | 13,900 | 0 | 0 |
| Stimulation | 13,894 | 0 | 0 |
| Adapter | 13,870 | 0 | 0 |
| Stress | 13,870 | 0 | 0 |
| Dose | 13,818 | 0 | 0 |
| Temperature | 13,810 | 0 | 0 |
| Barcode | 13,805 | 0 | 0 |
| Plasmid | 13,760 | 0 | 0 |
| Cancer | 13,755 | 0 | 0 |
| Individual | 13,729 | 46 | 201 |
| rRNA_depletion | 13,647 | 0 | 0 |
| Infected | 13,555 | 2 | 32 |
| Separation | 13,465 | 0 | 0 |
| GENE | 13,365 | 0 | 0 |
| Feeding | 13,089 | 0 | 0 |
| Sex | 12,705 | 0 | 0 |
| FRACTION | 12,580 | 7 | 127 |
| Growth_Condition | 12,480 | 2 | 16 |
| STAGE | 11,600 | 3 | 19 |
| Age | 11,579 | 3 | 26 |
| TIMEPOINT | 11,387 | 12 | 49 |
| INHIBITOR | 8,761 | 2 | 8 |
| Genotype | 8,494 | 28 | 610 |
| CELL_LINE | 8,409 | 94 | 577 |
| REPLICATE | 7,425 | 28 | 5,997 |
| Strain | 7,243 | 5 | 24 |
| TISSUE | 4,813 | 2 | 9 |
| CONDITION | 1,180 | 0 | 0 |
| LIBRARYTYPE | 1,022 | 0 | 0 |
| BATCH | 14,004 (all `''`) | 0 | 0 |
| Monosome_purification | 14,004 (all `''`) | 0 | 0 |

## Needs a curator's judgement

- **`0.0` in numeric columns** (REPLICATE, TIMEPOINT, Dose, Temperature, Age) is flagged with a note, because zero could be a real measurement. Everywhere else it's clearly a missing-value marker. Separately, 32 Dose values are a literal `0` and were not flagged.
- **`NA_` in CELL_LINE seems to carry meaning:** "not a cell line, here's the primary cell type", e.g. `NA_Primary hippocampal neurons` or `NA_CD8+ T cells`. Stripping the prefix would lose that. A separate cell-type column may be the better fix.
- **In Individual, `NA_` is joined onto bare IDs** (`NA_13`, `NA_A`), which suggests two source fields were concatenated.
- **Synonyms the rules can't detect**, which need manual rows:
  - Genotype: `wild type`, `Wild type`, `wild type genotype`.
  - LIBRARYTYPE: `RNA-Seq` vs `RNAseq matched to RPF`.
  - FRACTION: `ribosome protected fragments`, `RPF`, `ribosome-protected mRNA fragments`, `ribosome-protected fragments 26-34nt`.
  - INHIBITOR: `untreated` vs missing.
- **Values in the wrong column:** FRACTION contains treatments (`DMSO`, `Auxin`) and read-length descriptions rather than cellular compartments.
- **The spelling-variant rule picks the most common spelling**, which is sometimes lower case (e.g. Age `Adult` → `adult`). Edit the suggestion where a different house style is wanted.

## Where the problems come from

- **None of the patterns (`0.0` for missing, `NA_…`, `…NA`, `X_X`) are produced by code in this repo.**
  - `scripts/generate_fixtures.py` writes non-string values with `f'"{row[col]}"'`, which would turn NaN into `"nan"`. No `"nan"` values exist in the DB, so the `0.0` came from further upstream.
  - The concatenation patterns point to an earlier step that joined several source fields with `_`, possibly in the curation sheet or a notebook run that isn't in the repo.
- Finding that step would stop these problems coming back on the next import. Until then, re-running `clean_metadata` after each import will re-flag them. Already-approved rows re-apply cleanly.

## Related display bug (code, not data)

The filter panels treat only `''` and `'nan'` as missing (`riboseqorg/main/utilities.py:196`, `riboseqorg/main/views.py:267`). So `0.0` is the top option in almost every filter list. Treating `0.0` as missing when displaying would fix this without touching stored values.

## Trips / GWIPS / RiboCrypt link data

- The three link tables are empty in the repo's DB, and nothing in the repo loads them.
- Meanwhile samples are flagged as available: 2,441 on Trips, 2,961 on GWIPS and 11,094 on RiboCrypt. `generate_fixtures.py` set these flags from CSVs.
- So on the server, the link tables and the flags can disagree. The proposed link-building rewrite needs either a production copy of those tables or the source CSVs (ideally both) to build and verify against.
