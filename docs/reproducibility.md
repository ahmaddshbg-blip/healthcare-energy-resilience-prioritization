# Reproducibility

## Current state

The repository contains public decision, source-file, source-table, method, and
claim contracts, plus six source-preserving staging-table contracts. It also
contains executable validation for the frozen source manifest, eight
source-table declarations, accepted method invariants, deterministic
480-configuration expansion, synthetic structural profiles, source adapters,
staging extraction and checkpoints, independent Parquet verification,
fail-closed frozen-build orchestration, and hash-only private snapshot
verification. This is an engineering milestone, not a completed analytical
pipeline. Real files have been read only by the structural profiler after hash
verification; no real record has been staged, normalized, joined, or scored.

## Contract validation

Create an isolated Python 3.11-3.13 environment, install the project, and run:

```bash
python -m pip install -e ".[dev]"
python scripts/validate_contracts.py
python -m pytest
```

Direct dependencies are exactly pinned in `pyproject.toml`; the complete tested
environment is recorded in `requirements-lock.txt`.

`configs/configurations.json` is generated only from `configs/method.json`:

```bash
python scripts/validate_contracts.py --write-configurations
```

The validator checks JSON Schema, accepted semantic invariants, source-table
shape, staging row-preservation rules, content hashes, unique identifiers,
exact family counts, and byte-for-byte deterministic expansion. It does not
access `HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT`.

The source-table tests use only invented contracts and observed profiles. They
exercise failures for encoding, row count, ordered header, required parser
type, table or sheet presence, key cardinality, and exact duplicate count. The
accepted contract also records the physical Windows-1252 Census file and the
trailing empty header cells in both HRSA CSV files.

## Synthetic staging extraction

`configs/staging_tables.json` is tied to the exact source-table contract hash.
It stages six county-relevant tables and explicitly leaves the historical
state and ZIP Code sheets as validation-only. Every staged source row must
produce one output row in source order, with a one-based `source_row_number`.
Only declared required columns are retained; names, parser types, and null
policies are inherited from `configs/source_tables.json`.

`src/healthcare_resilience/staging.py` transforms already-opened mappings.
`src/healthcare_resilience/source_adapters.py` validates contracted CSV/XLSX
structures while retaining only required columns, and
`src/healthcare_resilience/staging_checkpoint.py` writes private Parquet tables
plus a deterministic manifest through an atomic directory rename. Tests cover
preserved strings, displayed HHS-like value 11, `Not Applicable` text,
repeated rows, nulls, strict logical types, physical schema drift, independent
Parquet read-back, deterministic hashes, failed-write cleanup, and tampering.
Every file used by these tests is invented.

The checkpoint manifest binds the snapshot and source, source-table, and
staging contract hashes. It records logical, physical, combined-schema, and
canonical typed-row hashes plus local Parquet byte hashes, but deliberately
omits timestamps and absolute paths. Binary Parquet identity is local evidence;
canonical content identity is the cross-environment target. See
[staging tables](staging_tables.md) and
[staging checkpoints](staging_checkpoints.md) for the complete boundary.

## Frozen staging build

The implemented command is:

```bash
python scripts/build_staging_checkpoint.py --data-root /absolute/private/data/root
```

It must be run without network access from a clean committed checkout. It
accepts only the public accepted contracts: there is no CLI flag to bypass the
15-file snapshot or eight-table requirements. It records the commit,
`requirements-lock.txt` hash, Python/platform identity, and direct dependency
versions. It verifies the snapshot before and after extraction, then publishes
one content-addressed build only after independent Parquet verification.

The private output is:

```text
<data-root>/checkpoints/<snapshot-id>/source_preserving_staging/<build-id>/
  staging_build_manifest.json
  checkpoint/
    staging_checkpoint_manifest.json
    tables/
```

The command refuses dirty repositories and existing output. A failure removes
its temporary build and cannot claim `COMPLETE`. Although this command is now
implemented and tested with invented files, it has not been authorized or run
against the accepted private snapshot.

## Source-table profiling

After frozen snapshot verification succeeds, run:

```bash
python scripts/profile_source_tables.py --data-root /absolute/private/data/root
```

The command reads only the five contracted CSVs and three HHS workbook sheets.
It validates strict encoding, BOM state, line endings, workbook sheet order,
header fingerprints, row widths, required parser types, key cardinality, and
exact-duplicate counts. It writes
`verification/<snapshot-id>/source_table_profile.json`, never inside the
immutable snapshot.

The private profile contains structural evidence only. It has no source values,
absolute paths, normalized identifiers, joins, criteria, scores, or portfolio
results. Two complete runs produced the same profile SHA-256:
`adfb58748598143eb32633f7db0dabec06aab25611961b6f9fea2d77104bfae1`.

## Frozen snapshot verification

The private root must contain this exact layout:

```text
<data-root>/
  snapshots/
    <accepted-snapshot-id>/
      raw/
```

Set `HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT` or pass an explicit path:

```bash
python scripts/verify_snapshot.py --data-root /absolute/private/data/root
```

The command rejects missing, extra, renamed, symbolic-link, size-mismatched,
or hash-mismatched files. It never opens a parser for CSV, JSON, XML, or Excel;
it reads bytes only for SHA-256 verification. Its deterministic report is
written outside the immutable snapshot under
`verification/<snapshot-id>/source_verification.json`. The report contains no
absolute data-root path. A failed verification returns a nonzero exit status.

## Data boundary

Real source files, checkpoints, and runs stay outside Git under
`HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT`. The repository will never depend on a
personal absolute path. Raw files are acquired from official publishers or
read from an exact private frozen snapshot.

## Planned analytical execution modes

1. **Synthetic test** validates parser boundaries, failure paths, deterministic
   behavior, and output contracts without real county records.
2. **Frozen reproduction** runs without network access and requires every file
   to match the accepted source manifest.
3. **Current-source refresh** downloads a new immutable evidence vintage and
   stops for review when source schema, geography, or semantics change.

## Verification target

The first accepted result must complete twice from fresh output directories:
once in clean Windows and once in clean Linux or Google Colab. Canonical sorted
analytical hashes must match. Binary Parquet file hashes may differ across
library builds and will be reported separately rather than falsely promised as
cross-platform identical.

## Publication boundary

The eventual public repository may include compact reviewed result tables and
figures. It will not include raw HHS, FEMA, HRSA, or Census files, private paths,
credentials, or unreviewed intermediate artifacts.
