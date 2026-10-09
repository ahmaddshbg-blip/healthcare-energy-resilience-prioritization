# County Evidence Readiness

## Decision

**PASS AFTER REMEDIATION FOR EXACTLY ONE NEW CONTROLLED FROZEN COUNTY-EVIDENCE
BUILD; NEW EXPLICIT AUTHORIZATION REQUIRED.**

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
the full suite passes 145 tests. No private artifact was opened to obtain this
decision.

## First Controlled Attempt and Remediation

The user authorized one controlled attempt after the original readiness
decision. At code commit `31751f6d478a41373c5f601de6ffb6581bbd3abe`, the
attempt failed closed before input verification or private artifact reading.
Git rejected the repository ownership before the staging or geography path was
opened. No county-evidence output root or partial artifact was created.

The shared repository-identity helper now invokes Git with a command-scoped
`safe.directory` equal to the resolved repository path. It does not alter the
user's global Git configuration. The remediation is recorded at commit
`85cdd0e4f3b7dbbc9f133133e3d98e82d302ecca`. A focused 22-test set and the
full 145-test suite pass, and a live clean-worktree repository-identity capture
returned that exact commit on the Windows host.

The failed attempt consumed its authorization. The remediation restores
readiness but does not authorize a rerun.

## Residual Risk

Synthetic readiness cannot prove that every real publisher category or null
pattern is benign. The controlled build must therefore fail closed on any
uncontracted value, coverage drift, schema drift, identity mismatch, or
manifest inconsistency. A successful local build would establish reproducible
evidence construction only in its recorded environment; it would not establish
cross-platform Parquet byte equality or analytical validity.

## Required Execution Sequence

If the user separately provides a new authorization for exactly one controlled
build:

1. verify the accepted staging and geography checkpoints without writes;
2. run the no-override county-evidence entrypoint once;
3. independently reopen and verify the manifest and Parquet artifact;
4. record the resulting identities and counts without publishing source data;
5. stop before criteria, scores, portfolio membership, or county status.

A failed attempt consumes the authorization. A rerun requires diagnosis,
documented review, and new explicit authorization.
