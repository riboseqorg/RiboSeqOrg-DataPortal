"""
Rebuild the portal's Sample/Study metadata from raw SRA records.

Replaces the chain Metadata-Curation (R) -> obtain_live_metadata_set.ipynb ->
generate_fixtures.py, which introduced the NA_ / ...NA / X_X / 0.0 artefacts
documented in audit/metadata-audit.md. See README.md in this directory.
"""
