# Plan: integrating omics-extractor into the portal metadata pipeline

*September 2026. Builds on `metadata-audit.md` and the rebuild in
`scripts/metadata_rebuild/`.*

## Goal

- For every sample, store and show three versions of each metadata field:
  - **raw**: exactly what SRA/BioSample says;
  - **pattern-matched**: the rule-based value;
  - **LLM-standardised**: omics-extractor's value.
- Run the LLM on **all** samples, not only those with gaps, so the tiers can
  be compared everywhere.
- Never let an unvalidated LLM value reach the published columns or filters.

## Where things stand

**Portal (live DB, rebuilt 19 Sep 2026)**
- 20,079 samples and 1,401 studies. The audit's artefact detector finds none
  of the patterns it listed.
- `scripts/metadata_rebuild/` fetches from NCBI and produces the pattern tier,
  recording the source of every core value (`manual`, `baseline`, `st`,
  `auto`, `strategy`).
- 1,952 runs are in `review_queue.csv`, 1,932 of them because they have no
  data type (LIBRARYTYPE).
- The raw tier is not stored anywhere yet. OpenColumns only holds unmapped
  attributes, and the per-project `sqlites/` files have been removed.

**omics-extractor** (`Metadata-Curation-phase1/omics-extractor`)
- 148 tests pass (40% coverage). It has:
  - fetchers for SRA, BioSample, BioProject, GEO and PubMed;
  - per-value provenance (`BaseProvenance`) and a field registry
    (`fields.py`);
  - a rule-based assay classifier;
  - an ontology mapper backed by OLS;
  - LLM providers for Claude, Gemini, vLLM and Transformers.
- **The LLM step isn't accurate enough yet.** In the pilot's human review
  (48 samples), 64 LLM additions were judged: 26 accepted, 10 relabelled,
  28 rejected.
- **The LLM step is too expensive as designed.** It makes one call per
  sample, with the full study context each time: about 9 s per sample, or
  around 50 GPU-hours for the portal.
- **The assay classifier needs fixes before it can be trusted.** Tested
  against the 6,082 samples curators labelled Ribo-Seq, it calls 1,908
  Ribo-seq, 1,310 RNA-seq and 2,814 ambiguous. The causes are in Phase 2.

**Evaluation data we already have**
- 6,973 runs with human-checked LIBRARYTYPE in the RiboCrypt curation sheet
  (`CHECKED` = a curator's name), and the same sheet for the other core
  columns. That's a far larger test set than the pilot's 48 samples.
- One caveat: curators started from ORFik's suggestions, so the sheet
  favours rule-based answers. Part of it should be re-checked blind (Phase 4).

## Target design

```
NCBI ──fetch.py──▶ raw tier ──merge/core.py──▶ pattern tier ──┐
                      │                                         ├─▶ published columns
                      └──omics-extractor (offline batch)──▶ LLM tier ──(per-field gate)──┘
                                                                  ▲
                                          curator decisions ─▶ curated tier
```

- **The published Sample columns don't change.** They stay the source for
  filters, the API and downloads, so search stays fast. They are filled in
  this order:
  1. curated value;
  2. pattern-matched value;
  3. LLM value, only for fields that passed the gate, and only where 1 and 2
     are empty.
- **All tiers live in one new long-format table**, which the sample page
  reads.
- **omics-extractor runs offline** (GPU box or API) and hands over a file.
  The portal never calls an LLM.

### New table: `SampleValue`

| Column | Notes |
|---|---|
| `sample` | FK to Sample (run level; BioSample-level values are copied to each run) |
| `field` | Portal column name, e.g. `TISSUE`, or a new name for fields without a column (`cell_type`, `nuclease_time`) |
| `tier` | `raw` / `pattern` / `llm` / `curated` |
| `value` | Display value |
| `source` | e.g. `biosample:cell line`, `manual`, `st`, `auto`, `llm:gemini-2.5-flash` |
| `evidence` | The verbatim source text the value came from (required for `llm`) |
| `confidence` | 0–1; null for raw |
| `ontology_id` | e.g. `UBERON:0002107`, when mapped |
| `run_id` | Which pipeline or LLM run produced it (model, prompt version, input hash) |
| `status` | `accepted` / `rejected` / `pending` (for `llm` and `curated`) |

- Index on (`sample`, `field`) and (`field`, `tier`, `value`).
- Size estimate: around 1.5 M rows; SQLite handles that comfortably.
- `OpenColumns` becomes redundant (raw values with `field` = the source
  attribute name) and can be dropped later.
- This is a `models.py` change plus a migration. `models.py` is currently
  being edited in another session, so land this after that work merges.

### Hand-over from omics-extractor: JSONL

One line per (sample, field, tier = `llm`):

```json
{"run": "SRR1234567", "biosample": "SAMN0000001", "field": "TISSUE",
 "value": "Liver", "raw_text": "hepatocytes from adult liver",
 "evidence": "hepatocytes from adult liver", "confidence": 0.8,
 "ontology_id": "UBERON:0002107", "model": "gemini-2.5-flash",
 "prompt_version": "2026-10-a", "input_hash": "sha256:…"}
```

The portal side is a management command, `import_sample_values <file>`,
which loads the file, checks field names and evidence, and replaces the
earlier `llm` rows for that model run.

### Field mapping (omics-extractor → portal)

| omics-extractor | Portal | Note |
|---|---|---|
| organism | ScientificName | pattern tier already fine |
| tissue, cell_line, strain, genotype, age, sex | TISSUE, CELL_LINE, Strain, Genotype, Age, Sex | |
| cell_type | *(new field)* | CELL_LINE currently mixes lines and primary cell types (`NA_Primary hippocampal neurons` in the audit) |
| developmental_stage | STAGE | |
| condition, timepoint, replicate, batch | CONDITION, TIMEPOINT, REPLICATE, BATCH | |
| treatment | *(new field)* | not INHIBITOR, which is the translation inhibitor |
| disease, stress, temperature, growth_condition | Disease, Stress, Temperature, Growth_Condition | |
| inhibitor, nuclease, fraction, monosome_purification, umi, adapter, rrna_depletion, kit | INHIBITOR, Nuclease, FRACTION, Monosome_purification, UMI, Adapter, rRNA_depletion, Kit | |
| digestion_temperature/time, footprint_min/max_length | *(new fields)* | useful for Ribo-seq users; tier table only at first |
| library_strategy | LIBRARYTYPE | set by the assay classifier (Phase 2), not by the LLM |
| *(none)* | GENE, SiRNA, SgRNA, ShRNA, Plasmid, Cancer, microRNA, Individual, Antibody, Ethnicity, Dose, Stimulation, Host, Infected, Feeding, Separation, Barcode | add to the omics-extractor scheme, or leave them raw and pattern tier only |

## Phases

### Phase 1: raw and pattern tiers in the portal (no LLM)

- Add `SampleValue` and the `import_sample_values` command.
- Make the rebuild write the `raw` and `pattern` rows. It already has both in
  memory (`merge.py` attributes, `samples.csv` `_source_*`).
- Sample page: a table per field with raw, pattern-matched and curated
  values, and the source of each.
- **Done when:** every published value on a sample page traces back to a raw
  value or a curator, and the page still renders in under 300 ms.

### Phase 2: data type (assay) classification

- Fix the classifier in omics-extractor:
  1. Treat `_`, `.` and `/` as word boundaries. `Ribo-seq_rep1` currently
     fails `ribo[-_\s]?seq\b`.
  2. Remove `miRNA-Seq` from the hard exclusions. 34 curated Ribo-seq runs
     were filed under that SRA strategy. Also add `Ribo-seq` as a strategy
     value, and treat `MNase` library selection as supporting footprinting,
     not RNA-seq.
  3. Classify runs from run-level text only (title, library name,
     attributes). Use study text as a separate prior, so a
     "WT input mRNA for Ribosome Profiling" run is classed as RNA-seq.
- Record the verdict, confidence and evidence as `pattern` rows for
  `LIBRARYTYPE`. The published value follows the rebuild's order
  (curated > baseline > classifier > SRA strategy).
- **Done when:** against the curated labels, Ribo-Seq precision is at least
  0.98 and recall at least 0.90, and RNA-Seq precision is at least 0.95.
  Anything below the confidence threshold goes to the review queue.
- The ~550 new and ~1,400 older runs with no data type get a verdict or a
  review entry. The 26 new projects with no Ribo-seq signal (several are
  RIP/CLIP studies) get a keep/remove decision.

### Phase 3: make the LLM step accurate and affordable (in omics-extractor)

- **Extract, don't standardise.**
  - The LLM returns a free-text value plus a verbatim evidence quote for each
    field.
  - Any value whose quote doesn't appear in the input is dropped. The pilot
    already does this, but only for gap-filling.
- **Standardise by choosing, not generating.**
  - A second, cheap step gives the model a closed list of candidates and asks
    it to pick one, or "none of these".
  - Candidates come from the portal vocabulary
    (`resources/display_names.csv`, `Content.csv`) plus the top OLS ontology
    matches.
  - Otherwise, map deterministically.
  - This targets the pilot's failure mode (invented or relabelled terms).
- **Batch per project.**
  - One prompt holds the study context once, plus a compact table of that
    project's distinct samples, and returns JSON keyed by sample.
  - 20,079 runs reduce to 15,935 BioSamples, and to 7,924 distinct attribute
    sets once replicate and ID fields are ignored. That's 1,401 project
    prompts, split when a project exceeds the context budget.
- **Cache and re-run incrementally.** Key each project on a hash of its
  input, so re-runs only process new or changed projects. Use prompt caching
  where the provider supports it.
- **Keep it reproducible.** Pin model, prompt and scheme versions, recorded in
  every output row (`run_id`).
- Output the JSONL described above.

### Phase 4: evaluation gate

- Score each field against the human-checked runs (6,973 for LIBRARYTYPE,
  and the manual sheet's other columns) plus the pilot's 48-sample gold set.
- Before trusting those scores, re-check a random sample of about 300 runs
  blind, so rule-based suggestions don't bias the result.
- Report per field: coverage, exact-match accuracy after vocabulary mapping,
  unsupported-evidence rate, and changes versus the pattern tier.
- **Publishing rule:** a field's LLM values may fill empty published values
  only when its accuracy is at least 0.95 on the blind set. Every such value
  is labelled "LLM" in the UI and downloads. Until then, LLM values are shown
  on the sample page only.

### Phase 5: run on everything

- Run the full batch on the GPU host or an API, then import.
- Rough cost: 1,401 prompts. With batching and caching this should be a few
  GPU-hours, not ~50. Measure it in Phase 3.
- Monthly schedule after that:
  1. `fetch.py` (incremental);
  2. `build.py`;
  3. omics-extractor on changed projects;
  4. `import_sample_values`;
  5. evaluation report.

### Phase 6: curation in the portal

- Curators accept or reject LLM and pattern values from the sample or study
  page. A decision writes a `curated` row, which then wins.
- This replaces the Google Sheet and CSV curation loop, whose missing
  display-name mapping had to be reconstructed.
- Optional: a "show LLM suggestions" toggle on filters, off by default.

## Order and dependencies

1. Commit `scripts/metadata_rebuild/` and the removal of `sqlites/`.
2. Merge the in-progress app work before adding `SampleValue` (both touch
   `models.py`).
3. Phase 1 and the Phase 2 classifier fixes can run in parallel. Phase 3
   can start right away in omics-extractor.
4. Phase 4 gates Phase 5 publishing, but not showing values on the sample
   page.

## Decisions needed

- **Which LLM to use in production:** local vLLM on your GPU host, or an API
  (Gemini or Claude). This decides the cost and the data-handling story.
- **Curator time for the blind re-check** (~300 runs) and the review queue
  (1,952 runs today).
- **Whether to add portal columns** for cell type, treatment and the Ribo-seq
  protocol fields, or keep them in the tier table only.
- **What to do with non-Ribo-seq projects** (RIP/CLIP-only) that came in
  through the whitelist.
