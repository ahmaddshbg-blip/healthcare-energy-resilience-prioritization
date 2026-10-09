# County Evidence Readiness

## Decision

**PASS FOR EXACTLY ONE CONTROLLED FROZEN COUNTY-EVIDENCE BUILD; EXPLICIT
AUTHORIZATION REQUIRED.**

This decision covers implementation readiness only. It is not authorization to
open the accepted private staging or geography checkpoint. It does not approve
criteria, normalization, weighting, ranking, portfolio construction, or county
status calculation.

## Accepted Build Boundary

An authorized build may read only:

1. the accepted six-table source-preserving staging checkpoint;
2. the accepted six-artifact geography checkpoint; and
3. the public source, source-table, staging, method, geography, and county-
   evidence contracts whose hashes are bound in `configs/county_evidence.json`.

The build may publish only a new content-addressed private directory containing
exactly:

- `county_evidence.parquet`, with 3,144 unique reference rows and 72 contracted
  source-evidence fields; and
- `county_evidence_manifest.json`, with the complete input, contract, schema,
  canonical-content, environment, code, and file identities.

The historical HHS table remains a verified staging member but cannot be
selected, read, joined, or summarized by the county-evidence loader.

## Readiness Evidence

The machine-readable contract and schemas validate successfully. Synthetic
tests use invented source values and prove:

- one output row per reference county and explicit eligible/out-of-scope
  behavior;
- exact HHS eligible coverage, displayed-11 ambiguity, and source-value bounds;
- exact FEMA all-reference coverage, all 18 hazard score/rating pairs, and
  preservation of null versus `Not Applicable`;
- exact-row HPSA duplicate handling, mapped lineage, distinct identifiers, and
  separate primary and proposed-withdrawal raw maxima;
- complete site status and location-type category maps with canonical JSON;
- deterministic output and lineage under shuffled input order;
- source-row and map-to-staging lineage integrity;
- exact staging and geography manifest binding before and after reads;
- atomic two-file checkpoint publication, two-fresh-build manifest equality,
  independent artifact verification, and refusal of overwrite, dirty tree,
  input mutation, extra files, or tampering; and
- end-to-end invented orchestration from trusted extraction through verified
  checkpoint publication.

The repository contract validator is valid, all Python modules compile, and
the full suite passes 144 tests. No private artifact was opened to obtain this
decision.

## Residual Risk

Synthetic readiness cannot prove that every real publisher category or null
pattern is benign. The controlled build must therefore fail closed on any
uncontracted value, coverage drift, schema drift, identity mismatch, or
manifest inconsistency. A successful local build would establish reproducible
evidence construction only in its recorded environment; it would not establish
cross-platform Parquet byte equality or analytical validity.

## Required Execution Sequence

If the user separately authorizes exactly one controlled build:

1. verify the accepted staging and geography checkpoints without writes;
2. run the no-override county-evidence entrypoint once;
3. independently reopen and verify the manifest and Parquet artifact;
4. record the resulting identities and counts without publishing source data;
5. stop before criteria, scores, portfolio membership, or county status.

A failed attempt consumes the authorization. A rerun requires diagnosis,
documented review, and new explicit authorization.
