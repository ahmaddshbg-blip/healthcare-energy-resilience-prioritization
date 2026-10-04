# Geography Reconciliation Readiness Review

## Decision

**AMENDMENT READINESS PASSED; CONTROLLED GEOGRAPHY BUILD VERIFIED; ANALYTICS
NOT AUTHORIZED.**

The first review accepted the synthetic rules but rejected real execution
because staging identity still depended on a caller assertion. That blocker is
now closed. The production entrypoint constructs its own read-only verifier,
binds the accepted staging build and manifest hashes, reopens all six staging
Parquet artifacts, exposes only contracted geography fields, and repeats the
complete verification after reading and after geography checkpoint creation.

The prior readiness review supported exactly one authorized production attempt.
The input boundary accepted the staging build and all six Parquet artifacts,
but reconciliation failed closed because all 3,228 historical HHS FIPS values
carry trailing whitespace. The amendment now keeps that table in staging as
context-only evidence and removes it from mandatory geography mapping. No raw
value is trimmed or repaired, and the first amended execution attempt published
no geography checkpoint.

The amendment readiness review is now complete. The five mapped source rules,
one context-only staging rule, six-artifact checkpoint definition, exact input
membership, and fail-closed controls agree across the machine-readable
contracts, implementation, schemas, and invented fixtures. The full suite and
contract validator pass. This is a readiness decision only; it does not reopen
the private snapshot or authorize a second real geography execution.

The user then granted a new explicit authorization for exactly one controlled
frozen geography build. That build completed under the amended scope and its
six-artifact checkpoint passed independent read-only verification. The evidence
is recorded in [geography build evidence](geography_build_evidence.md). This
does not authorize county evidence construction or analytical calculation.

## Evidence reviewed

- `configs/geography.json` records the accepted reference universe, exact HHS
  replacements, unresolved legacy geographies, five mapped source rules, one
  context-only staging table, mapping-count invariants, coverage requirements,
  and failure conditions.
- `configs/geography.schema.json` and
  `configs/geography_checkpoint.schema.json` reject structural contract or
  manifest drift.
- `src/healthcare_resilience/geography.py` creates one sorted county reference
  and five row-preserving geography maps without aggregation or cross-source
  evidence.
- `src/healthcare_resilience/geography_checkpoint.py` writes six Parquet
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
count, lineage, and file claims. The post-attempt input verification still
matches all accepted staging identities, and the geography output root is
absent. Nine additional input-boundary tests use a
complete invented six-table staging build, including a production-signature
check proving that no contract or probe override is exposed and a direct check
that the five mapped plus one context-only contracts cover the six-table input
set.

## Contract identities

- accepted specification amendment review basis:
  `a6dd22b06b0ec27761b85f12ad13b154317f99a0f7a518df46a3c02a6d910a9e`;
- geography contract:
  `5f61e313523aec2a0d13848f1e01c97a64b1cf048d403d32592a8cfce69a287c`;
- geography contract schema:
  `4e870a0ddc7192cc30c0c259d1656f430923fc045b20d39018a429da1d74df95`;
  and
- geography checkpoint schema:
  `a445f6e39fa6e0cbe2148c79bf83ed3e885b9fcdfd8ae2aff8754b538b08da15`.

The amendment review-basis hash records the exact public specification used for
this synthetic amendment review.

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
- The controlled run exposed a source-quality mismatch: the historical HHS
  `FIPS_Code` field has 3,228 trailing-whitespace representations, while the
  accepted geography contract permits only exact five-digit text and forbids
  trimming or repair.
- The amendment keeps that historical table source-preserved but excludes it
  from geography map outputs and current eligibility.

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

The private staging Parquet was opened during the explicitly authorized build
and its independent post-build verification. The amended geography checkpoint
was published with six verified artifacts. No source measure was joined,
normalized, deduplicated, filtered, or aggregated, and no county evidence
exists. HPSA and site records remain unaggregated, and no criterion, score,
portfolio, or county status exists. The prior failed-closed attempt remains
part of the history; the amended build is verified only for its stated
geography scope.

## Exact next action

Do not proceed to county evidence or analytics in this execution. The amended
geography checkpoint and its six artifacts have been independently verified.
Any next analytical step requires a separate acceptance decision and must not
modify the verified private checkpoint or claim cross-platform equality.
