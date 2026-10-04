# Geography Reconciliation Readiness Review

## Decision

**PASS FOR ONE CONTROLLED REAL GEOGRAPHY BUILD; EXPLICIT AUTHORIZATION
REQUIRED.**

The first review accepted the synthetic rules but rejected real execution
because staging identity still depended on a caller assertion. That blocker is
now closed. The production entrypoint constructs its own read-only verifier,
binds the accepted staging build and manifest hashes, reopens all six staging
Parquet artifacts, exposes only contracted geography fields, and repeats the
complete verification after reading and after geography checkpoint creation.

This is readiness to request authorization, not authorization itself. No
private staging artifact was opened during implementation or review.

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
- `src/healthcare_resilience/geography_input.py` verifies exact staging build
  membership, build and checkpoint manifests, all staging artifacts, and the
  three accepted manifest identities. Its production function has no caller-
  supplied probe and no contract-bypass parameter.
- `tests/fixtures/synthetic_geography_rows.json` contains invented labels,
  measures, and direct-match FIPS. Real FIPS occur only where the tests must
  validate the accepted replacement, legacy, or out-of-scope constant sets.
- `tests/test_geography_acceptance.py` implements exactly `GEO-P01` through
  `GEO-P15` and `GEO-N01` through `GEO-N15`.

The full repository suite passes 117 tests. Contract validation and bytecode
compilation also pass. Two fresh synthetic checkpoint roots produce identical
manifests, and independent verification reproduces their schema, content,
count, lineage, and file claims. Nine additional input-boundary tests use a
complete invented six-table staging build, including a production-signature
check proving that no contract or probe override is exposed and a direct check
that the public staging and geography contracts cover the same six-table set.

## Contract identities

- accepted specification review basis:
  `a9ce98e10ca596dfd7ec4f62cdd706e682bf1d42aa4ecb9c6a75328d514f1adb`;
- geography contract:
  `1330c9670a9922a4067804705ece0c8411d4d802ef011309e0dbb57c9e95b274`;
- geography contract schema:
  `93e6bad6e18e9105debb1e24e8bbf55b02d40eee0895408069b4e7e8a7c70884`;
  and
- geography checkpoint schema:
  `ce77778fbb4267882d884332509c1d25b916f99e8f0233d4c4abf22ded244db9`.

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
- The input build must match the accepted build ID, build-manifest file hash,
  checkpoint-manifest canonical hash, and checkpoint-manifest file hash.
- Exact build membership and all six input Parquet artifacts are independently
  verified before and after geography fields are read.
- Address, ZIP, source measures, and all non-geography columns are never
  exposed to the reconciliation function. State and county names are exposed
  only from the Census reference table because they are contracted reference
  attributes.
- Mutation after a completed temporary geography checkpoint is detected before
  atomic publication.

## Closed amendment

The required read-only staging-input boundary is implemented and tested with
invented staging artifacts. It now:

1. verify the accepted staging build identity and exact file membership;
2. load and validate the staging build and checkpoint manifests;
3. independently reopen all six staging Parquet artifacts with the existing
   staging verifier;
4. expose only `source_row_number` and the contracted geography fields to the
   reconciliation function; and
5. repeat the complete input verification after geography checkpoint creation
   so mutation cannot be hidden behind a stable caller assertion.

The adapter has no bypass flag, network behavior, normalization, join,
deduplication, or analytical aggregation. The trusted production function is
`run_frozen_geography_reconciliation`; no CLI was added because the accepted
amendment was limited to the input boundary.

## Scope boundary

No private Parquet artifact was opened for either readiness review. No
real county reference or geography map was created. No source measure was
joined, normalized, deduplicated, filtered, or aggregated. HPSA and site
records remain unaggregated, and no criterion, score, portfolio, or county
status exists.

## Exact next action

Wait for explicit user authorization. If authorized, run exactly one frozen
geography reconciliation through `run_frozen_geography_reconciliation`,
independently verify its manifest and seven artifacts, record the evidence,
and stop for acceptance review. Do not construct joined county evidence,
aggregate HPSA or site records, calculate criteria, scores, portfolios, or
county statuses, or claim cross-platform equality.
