# Geography Reconciliation Readiness Review

## Decision

**SYNTHETIC IMPLEMENTATION ACCEPTED; REAL-DATA EXECUTION NOT READY.**

The accepted geography rules are now machine-readable and executable against
invented rows. All 15 positive and 15 negative acceptance cases pass. This is
not yet sufficient evidence for opening the private staging checkpoint.

The blocking issue is narrow but material: the geography checkpoint writer
requires an `input_identity_probe`, but this repository does not yet implement
a trusted read-only probe that independently opens and verifies the accepted
staging build and its six Parquet artifacts. A caller-supplied tuple is not
evidence. Authorizing a real run in that state would weaken the fail-closed
standard already established for staging.

## Evidence reviewed

- `configs/geography.json` records the accepted reference universe, exact HHS
  replacements, unresolved legacy geographies, six source rules, mapping-count
  invariants, coverage requirements, and failure conditions.
- `configs/geography.schema.json` and
  `configs/geography_checkpoint.schema.json` reject structural contract or
  manifest drift.
- `src/healthcare_resilience/geography.py` creates one sorted county reference
  and six row-preserving geography maps without aggregation or cross-source
  evidence.
- `src/healthcare_resilience/geography_checkpoint.py` writes seven Parquet
  artifacts atomically under a content-addressed path, refuses overwrite and a
  dirty release tree, binds code and environment identity, verifies all files
  independently, and detects input-identity change and artifact tampering.
- `tests/fixtures/synthetic_geography_rows.json` contains invented labels,
  measures, and direct-match FIPS. Real FIPS occur only where the tests must
  validate the accepted replacement, legacy, or out-of-scope constant sets.
- `tests/test_geography_acceptance.py` implements exactly `GEO-P01` through
  `GEO-P15` and `GEO-N01` through `GEO-N15`.

The full repository suite passes 108 tests. Contract validation and bytecode
compilation also pass. Two fresh synthetic checkpoint roots produce identical
manifests, and independent verification reproduces their schema, content,
count, lineage, and file claims.

## Contract identities

- accepted specification review basis:
  `a9ce98e10ca596dfd7ec4f62cdd706e682bf1d42aa4ecb9c6a75328d514f1adb`;
- geography contract:
  `6d4a49c453ae3a95fc4c77b337fd26b3b9c79678bb35711d5f674d380bfe9c27`;
- geography contract schema:
  `10bd1788cf0ed06481306887c614e5f8bf3ec6a026928885cb8b423b155dd522`;
  and
- geography checkpoint schema:
  `f89f9b06da7490e4912bcb5fe80ef1c7cb02f53b3307ebfa0fec7268ec31e41c`.

The accepted review-basis hash remains recorded even though the public
specification status line was subsequently updated. This preserves the exact
document identity the user accepted.

## Controls that passed

- FIPS remains strict five-character text; no trimming, padding, coercion,
  name repair, ZIP fallback, coordinates, fuzzy matching, or allocation is
  available.
- Census alone defines the county reference; state summaries remain explicit
  and outside the reference.
- Only the two accepted HHS replacements can produce
  `EXACT_REPLACEMENT`.
- Alaska and Connecticut legacy rows cannot receive canonical FIPS.
- FEMA and current HHS coverage requirements are exact and one-to-one.
- Valid HPSA fields must agree, and fallback provenance is recorded.
- Every map preserves source-row count and lineage, and shuffled input order
  cannot change canonical outputs or hashes.
- Output schemas exclude source measures and cross-source columns.
- Checkpoints are atomic, content-addressed, no-overwrite, path-neutral, and
  independently reopened before publication.

## Blocking amendment

Implement and test one read-only staging-input boundary using invented staging
artifacts:

1. verify the accepted staging build identity and exact file membership;
2. load and validate the staging build and checkpoint manifests;
3. independently reopen all six staging Parquet artifacts with the existing
   staging verifier;
4. expose only `source_row_number` and the contracted geography fields to the
   reconciliation function; and
5. repeat the complete input verification after geography checkpoint creation
   so mutation cannot be hidden behind a stable caller assertion.

The adapter must have no bypass flag, no network behavior, and no analytical
aggregation. Its tests must use an invented six-table staging build outside the
repository. A real-data CLI is still unnecessary until this amendment passes a
second readiness review.

## Scope boundary

No private Parquet artifact was opened for this implementation or review. No
real county reference or geography map was created. No source measure was
joined, normalized, deduplicated, filtered, or aggregated. HPSA and site
records remain unaggregated, and no criterion, score, portfolio, or county
status exists.

## Exact next action

Implement only the blocking read-only staging-input boundary with invented
artifacts, rerun the complete suite, and conduct a second geography readiness
review. Do not authorize or execute real geography reconciliation before that
review passes.
