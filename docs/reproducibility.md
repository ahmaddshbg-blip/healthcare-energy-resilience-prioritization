# Reproducibility

## Current state

The repository contains public decision, source, method, and claim contracts.
It also contains executable validation for the frozen source manifest, accepted
method invariants, deterministic 480-configuration expansion, and hash-only
private snapshot verification. This is an engineering milestone, not a
completed analytical pipeline. No source table has been parsed and no county
result has been produced.

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

The validator checks JSON Schema, accepted semantic invariants, content hashes,
unique identifiers, exact family counts, and byte-for-byte deterministic
expansion. It does not access `HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT`.

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

1. **Synthetic test** validates transformations, failure paths, deterministic
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
