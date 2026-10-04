# County Evidence Contract

## Status

**DRAFT FOR ACCEPTANCE. NO REAL-DATA IMPLEMENTATION AUTHORIZED.**

This contract is the next boundary after the independently verified geography
checkpoint. It defines how source-preserving geography maps could be combined
with their own staged source measures into county-level evidence. It does not
define a new method, score, portfolio, or county status, and it must be
accepted before implementation or real-data execution.

## Purpose and Grain

The evidence unit is one row per Census reference county-equivalent, including
all 3,144 reference rows. The 3,133 eligible units and 11 accepted exclusions
remain explicit fields; exclusions are not silently dropped before evidence is
audited.

The proposed primary evidence table has exactly one row per canonical FIPS. It
is not a ranking table, a criterion matrix, or a portfolio table. Every field
must carry source-family provenance or be an explicit deterministic diagnostic.

## Permitted Inputs

Only the following private artifacts may be read:

1. the verified six-artifact geography checkpoint;
2. the matching six-table source-preserving staging checkpoint; and
3. the accepted machine-readable source, staging, geography, and method
   contracts whose identities are recorded in the manifests.

The historical HHS county table remains staging context-only. It must not be
joined, mapped, or used to create current county eligibility or evidence.

For mapped source tables, source measures are recovered only by joining a
geography-map row to its own source-preserving staging row on the pair
`(staging_table_id, source_row_number)`. A map row must never be joined to a
different source family or to a source row selected by value matching.

## Reference and Eligibility

The Census `county_reference` artifact is the left-side universe. It supplies
the canonical FIPS, reference state and county names, population estimate, and
the explicit geography mapping status.

Eligibility is copied from the accepted geography and decision contracts. It
must expose the accepted 11 out-of-scope units and their reasons. The evidence
contract does not infer eligibility from missing source records, population,
county names, or a later criterion value.

## Source Evidence Roles

| Source family | Evidence role | Cardinality at county grain | Required treatment |
|---|---|---|---|
| Current HHS emPOWER county | DME burden and Medicare denominator inputs | Exactly one mapped source row for every eligible county | Preserve reported values, including masked-value ambiguity and source lineage |
| FEMA NRI county | All-hazard context input | Exactly one mapped source row for every reference county | Preserve the contracted composite risk field and all mapping provenance |
| HRSA Primary Care HPSA | Component-level shortage evidence | Zero, one, or many mapped source rows per county | Preserve component rows; exact duplicate rows are not independent evidence; do not sum designation populations or scores |
| HRSA health-center sites | Contextual service-footprint evidence | Zero, one, or many mapped source rows per county | Preserve status and location-type values; do not impose an active-site filter or monotonic priority direction |
| Historical HHS county | Context-only staging input | Not present in county evidence | No join, repair, map, or current eligibility use |

The evidence table must retain source-row counts and provenance diagnostics for
each source family. A missing many-row source is represented as no observed
component or site row, not as a fabricated source record.

## HHS Evidence Semantics

The evidence layer preserves the reported HHS DME count and Medicare
beneficiary denominator as source values. A displayed masked value remains
explicitly ambiguous; it is not converted to a point estimate. The evidence
layer may carry a machine-readable masking flag and the raw declared value,
but it must not calculate lower or upper bounds here.

The Medicare denominator remains source evidence. The rate denominator
threshold and all interval transformations belong to the accepted method
execution boundary, not this evidence contract.

## HPSA Evidence Semantics

HPSA rows are processed only after exact source-row identity and geography
mapping provenance have been verified. The evidence layer preserves:

- eligible-status and designation-type fields;
- the source HPSA score;
- HPSA identifier and source row number;
- component-row count diagnostics; and
- exact-duplicate detection diagnostics.

The evidence layer must not sum component rows, designation populations, or
scores. Any later maximum-score transformation must use the accepted method
specification and must be recorded as a separate analytical artifact.

## Site Evidence Semantics

Site rows remain contextual. The evidence layer may provide transparent counts
or presence diagnostics stratified by the source status and location-type
fields, while preserving the underlying row-count and lineage claims. It must
not silently discard seasonal, mobile, permanent, absent, or other publisher
categories and must not turn presence into a monotonic need or service score.

## Join and Provenance Rules

- The join direction is always from the 3,144-row Census reference universe.
- HHS and FEMA joins must prove the required one-to-one cardinality before
  evidence publication.
- HPSA and site rows must remain one-to-many until their explicitly documented
  evidence diagnostics are produced.
- No inner join may remove a county from the reference universe.
- Every source-derived field must identify its source table and source row
  lineage, directly or through a deterministic provenance summary.
- Mapping statuses and diagnostic reasons must not be overwritten by a join.
- County names and state names come only from the Census reference artifact.
- County FIPS remains the canonical five-character text emitted by the
  verified geography checkpoint; no data normalization is introduced.

## Fail-Closed Conditions

Stop without publishing county evidence when any of the following occurs:

- the geography checkpoint or staging checkpoint identity differs from the
  accepted manifests;
- a required artifact is missing, extra, altered, or contains a symbolic link;
- the Census reference has a duplicate, missing, or unexpected canonical FIPS;
- an HHS or FEMA eligible-county join is missing, duplicated, or many-to-many;
- a source-row lineage lookup is missing, duplicated, or points to another
  source family;
- HPSA duplicate handling changes the declared component-row population;
- site status or location-type rows are silently filtered;
- a historical HHS row enters the evidence table;
- source measures are repaired, coerced, inferred, or replaced by geography
  names or other fallback keys;
- a source value is transformed into a criterion, score, portfolio membership,
  or county status before this evidence artifact is accepted; or
- the output directory exists, the repository is dirty, or a manifest claim
  cannot be independently reproduced.

## Synthetic Acceptance Tests

Before any real-data implementation, invented fixtures must prove:

1. one reference row produces one evidence row;
2. HHS and FEMA one-to-one joins reject missing and duplicate matches;
3. HPSA many-to-one rows preserve component lineage and reject silent sums;
4. exact duplicate HPSA rows are diagnosed without changing source-row counts;
5. site status and location-type categories remain visible without filtering;
6. masked HHS values remain ambiguous and no bounds are calculated;
7. the historical HHS table cannot enter the evidence input set;
8. source-row mutation, manifest mutation, and extra-file conditions fail
   closed; and
9. no criterion, score, portfolio, or county-status field is emitted.

## Acceptance Decision Required

The user must accept, amend, or reject this contract before implementation.
Acceptance would authorize only synthetic contract tests and a readiness
review. It would not authorize opening the private snapshot, building county
evidence, calculating criteria, or producing a portfolio.
