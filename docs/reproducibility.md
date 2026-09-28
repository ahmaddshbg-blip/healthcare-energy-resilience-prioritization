# Reproducibility

## Current state

The repository currently contains the public decision, source, method, and
claim contracts. Executable acquisition, validation, and analysis code has not
yet been added, and no county result has been produced. This page will not claim
one-command reproduction before that path exists and has been tested.

## Data boundary

Real source files, checkpoints, and runs stay outside Git under
`HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT`. The repository will never depend on a
personal absolute path. Raw files are acquired from official publishers or
read from an exact private frozen snapshot.

## Planned execution modes

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
