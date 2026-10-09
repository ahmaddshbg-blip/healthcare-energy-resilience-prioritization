# County Evidence Contract

## Status

**ACCEPTED FOR SYNTHETIC IMPLEMENTATION. NO REAL-DATA IMPLEMENTATION
AUTHORIZED.**

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

The proposed `county_evidence` table has exactly one row per canonical FIPS and
is accompanied by one evidence manifest. It is not a ranking table, a criterion
matrix, or a portfolio table. Every field must carry source-family provenance
or be an explicit deterministic diagnostic.

## Permitted Inputs

Only the following private artifacts may be read:

1. the verified six-artifact geography checkpoint;
2. the matching six-table source-preserving staging checkpoint; and
3. the accepted machine-readable source, staging, geography, and method
   contracts whose identities are recorded in the manifests.

The historical HHS county table remains staging context-only. It must not be
joined, mapped, or used to create current county eligibility or evidence.

The accepted geography checkpoint retains the exact geography-contract hash
used when it was built. A later documentation-only update changed the current
geography contract's specification-review hash without changing any mapping
rule. The evidence contract must bind both identities and may reconstruct the
build-time contract only by replacing that single declared review hash in the
current contract bytes. Any other byte or semantic difference fails closed.

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
| FEMA NRI county | Composite and hazard-specific risk inputs | Exactly one mapped source row for every reference county | Preserve the composite risk value plus every contracted hazard score/rating pair and mapping provenance |
| HRSA Primary Care HPSA | Component-level shortage evidence | Zero, one, or many mapped source rows per county | Preserve component rows; exact duplicate rows are not independent evidence; do not sum designation populations or scores |
| HRSA health-center sites | Contextual service-footprint evidence | Zero, one, or many mapped source rows per county | Preserve status and location-type values; do not impose an active-site filter or monotonic priority direction |
| Historical HHS county | Context-only staging input | Not present in county evidence | No join, repair, map, or current eligibility use |

The evidence table must retain source-row counts and provenance diagnostics for
each source family. A missing many-row source is represented as no observed
component or site row, not as a fabricated source record.

## Required Output Contract

The private evidence checkpoint may contain only:

1. `county_evidence.parquet`, with exactly 3,144 rows and one row per canonical
   FIPS; and
2. `county_evidence_manifest.json`, containing accepted input identities,
   schema and canonical-content hashes, artifact byte and file hashes, row
   counts, code commit, environment identity, and verification status. The
   manifest must bind the staging build identity and manifest hash, geography
   checkpoint identity and manifest hash, and exact source, staging,
   geography, method, and evidence-contract hashes.

The county table must contain these field families:

- reference: `canonical_fips`, `state_fips`, `county_code`, `state_name`,
  `county_name`, `population`, `decision_scope_status`, and `scope_reason`;
- HHS: source-row number, mapping status/rule, `Medicare_Benes`, reported
  `Power_Dependent_Devices_DME`, and the deterministic ambiguity flag;
- FEMA: source-row number, mapping status/rule, `RISK_SCORE`, `RISK_RATNG`, and
  all 18 contracted `*_RISKS` and paired `*_RISKR` fields used by mandatory
  hazard sensitivities;
- HPSA: mapped source-row count, exact-duplicate count, distinct HPSA-ID count,
  eligible row counts, maximum raw score for the `Designated` family, maximum
  raw score for the `Designated` plus `Proposed For Withdrawal` family, and a
  canonical lineage hash;
- site context: mapped source-row count, canonical status-count JSON, canonical
  location-type-count JSON, and a canonical lineage hash; and
- source-presence and validation flags that do not reinterpret source values.

No field beginning with `C_`, no normalized percentile, no weighted value, no
configuration membership, and no final county status may appear in this
checkpoint.

### Output types and nullability

The machine-readable implementation contract must use these logical types and
null rules without implicit casts:

| Field family | Logical type | Null rule |
|---|---|---|
| Reference identifiers, names, status, and reason | String | Identifiers, names, and status are non-null; `scope_reason` is required only for `OUT_OF_SCOPE` rows |
| Population and all row/count diagnostics | Integer | Non-null and nonnegative; population must remain positive |
| HHS source row and source measures | Integer | Non-null for `ELIGIBLE`; null for `OUT_OF_SCOPE` |
| HHS mapping status/rule | String | Non-null for `ELIGIBLE`; null for `OUT_OF_SCOPE` |
| HHS ambiguity flag | Boolean | Non-null for `ELIGIBLE`; false for `OUT_OF_SCOPE` |
| FEMA source row | Integer | Non-null for every reference row |
| FEMA mapping status/rule and rating fields | String | Mapping fields and `RISK_RATNG` are non-null; hazard ratings retain source nullability |
| FEMA score fields | Number | `RISK_SCORE` is non-null and finite; hazard scores retain source nullability |
| HPSA raw maximum scores | Integer | Nullable only when the corresponding qualifying-row count is zero |
| Canonical category maps | JSON object encoded as String | Non-null; empty input is exactly `{}` |
| Canonical lineage hashes | 64-character lowercase hexadecimal String | Non-null, including the deterministic hash of an empty lineage array |
| Presence and validation flags | Boolean | Non-null |

Canonical FIPS fields remain fixed-width strings and must never be emitted as
numbers. Physical Parquet types and field order must be frozen in the later
machine-readable evidence contract and tested against this logical contract.

## HHS Evidence Semantics

The evidence layer preserves the reported HHS DME count and Medicare
beneficiary denominator as source values. A displayed value of 11 remains
explicitly ambiguous; it is not converted to a point estimate. The
machine-readable ambiguity flag is deterministic:

```text
hhs_dme_ambiguous_11 = (Power_Dependent_Devices_DME == 11)
```

This follows the accepted publisher disclosure that values from 1 through 10
are displayed as 11 and the audit finding that a displayed 11 can also be a
true 11. The evidence layer preserves the reported value and flag but must not
calculate lower or upper bounds here.

The Medicare denominator remains source evidence. The rate denominator
threshold and all interval transformations belong to the accepted method
execution boundary, not this evidence contract.

Current HHS coverage is required only for the 3,133 `ELIGIBLE` units. The 11
`OUT_OF_SCOPE` rows retain null HHS source lineage and measures and a false
ambiguity flag. A missing HHS row never causes a county to become out of scope;
missing eligible coverage is a build failure.

## FEMA Evidence Semantics

The evidence layer preserves `RISK_SCORE` and `RISK_RATNG` plus these 18 exact
hazard score/rating pairs:

`AVLN`, `CFLD`, `CWAV`, `DRGT`, `ERQK`, `HAIL`, `HWAV`, `HRCN`, `ISTM`,
`LNDS`, `LTNG`, `IFLD`, `SWND`, `TRND`, `TSUN`, `VLCN`, `WFIR`, and `WNTW`,
using the contracted `*_RISKS` and `*_RISKR` fields.

A null hazard score and its publisher rating remain distinct from numeric zero.
`Not Applicable` is never converted to zero or ranked as observed low risk. The
evidence layer does not normalize, rerank, average, or combine hazard fields.
For every reference county, the composite `RISK_SCORE` must be finite and
within the accepted 0-to-100 source scale or the evidence build fails closed.

## HPSA Evidence Semantics

HPSA rows are processed only after exact source-row identity and geography
mapping provenance have been verified. Exact-duplicate identity is the
canonical typed value of every retained HPSA staging field except
`source_row_number`; geography-map fields are not used to manufacture or erase
a duplicate. The evidence layer preserves:

- eligible-status and designation-type fields;
- the source HPSA score;
- HPSA identifier and source row number;
- component-row count diagnostics; and
- exact-duplicate detection diagnostics.

The evidence layer must not sum component rows, designation populations, or
scores. It may calculate only the two declared maximum raw-score summaries
after exact-row deduplication: the primary `Designated` status family and the
accepted `Designated` plus `Proposed For Withdrawal` sensitivity family. Both
use only `Geographic HPSA`, `High Needs Geographic HPSA`, or `HPSA Population`
designation types. A county with no qualifying row retains a null raw maximum
and zero qualifying-row count; conversion to criterion value zero belongs to
the later method boundary.

Exact-row deduplication is applied globally to the mapped `DIRECT_REFERENCE`
population before county summaries are calculated. The first row is retained
by ascending `source_row_number`; every later identical row increments the
exact-duplicate count but cannot affect an eligible-row count or maximum. The
mapped source-row count and lineage hash still cover all mapped rows, including
diagnosed duplicates, so deduplication cannot conceal source population.

## Site Evidence Semantics

Site rows remain contextual. The evidence layer provides a mapped row count and
two canonical JSON count maps keyed by the exact publisher values in
`Site Status Description` and
`Health Center Location Type Description`. Keys are sorted, counts are
nonnegative integers, and the sum of each map must equal the mapped source-row
count. It must not silently discard any category and must not turn presence
into a monotonic need or service score.

Only rows whose accepted geography map has `DIRECT_REFERENCE` and a non-null
canonical FIPS may contribute to HPSA or site county summaries. HHS may also
use its two accepted `EXACT_REPLACEMENT` rows. Unresolved, missing, invalid,
outside-universe, and context-only rows remain accounted for by their immutable
geography and staging manifests but never enter a county summary.

## Lineage Hashes

For HPSA and site evidence, the lineage hash is SHA-256 over the canonical JSON
array of ascending mapped `source_row_number` values for that county and source
table. The row count, sorted lineage array, and hash must agree. Full source
values remain in the immutable staging artifact and are not duplicated in the
public repository.

## Join and Provenance Rules

- The join direction is always from the 3,144-row Census reference universe.
- HHS must cover every eligible county exactly once; FEMA must cover every
  reference county exactly once. Both cardinalities are proved before evidence
  publication.
- HPSA and site rows must remain one-to-many until their explicitly documented
  evidence diagnostics are produced.
- Each map-to-staging recovery must use the exact contracted staging table ID
  and source row number, then prove one and only one recovered staging row.
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
- an eligible county lacks exactly one HHS row, or any reference county lacks
  exactly one FEMA row;
- an eligible HHS DME or Medicare value is null, negative, or has DME greater
  than Medicare beneficiaries;
- any reference-county FEMA composite score is null, non-finite, or outside 0
  through 100;
- a FEMA `Not Applicable` or null hazard is converted to numeric zero;
- a source-row lineage lookup is missing, duplicated, or points to another
  source family;
- HPSA duplicate handling changes the declared component-row population or
  uses fields outside the accepted exact-duplicate identity;
- a non-`DIRECT_REFERENCE` HPSA or site row contributes to a county summary,
  or an HHS row outside `DIRECT_REFERENCE` and the two accepted
  `EXACT_REPLACEMENT` mappings contributes;
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

1. exactly 3,144 reference rows produce 3,144 unique evidence rows with 3,133
   eligible and 11 out-of-scope units;
2. HHS eligible-only and FEMA all-reference one-to-one joins reject missing,
   duplicate, and many-to-many matches;
3. the HHS ambiguity flag is true exactly when reported DME equals 11, while no
   lower or upper bound is calculated;
4. all 18 FEMA hazard score/rating pairs remain present and `Not Applicable`
   cannot become zero;
5. HPSA many-to-one rows preserve component lineage, diagnose exact duplicates,
   and produce only the two accepted raw maximum-score summaries;
6. site status and location-type count maps retain every invented category and
   sum to the mapped row count;
7. HPSA and site lineage hashes are deterministic under shuffled input order;
8. the 11 out-of-scope rows retain null HHS lineage and measures, while a
   missing HHS row for an eligible unit fails closed;
9. unresolved, missing, invalid, and outside-reference HPSA or site rows cannot
   enter county summaries, while remaining fully accounted in input manifests;
10. the historical HHS table cannot be selected, read, joined, or summarized
    as an evidence source, even though it remains a member of the verified
    six-table staging checkpoint;
11. source-row mutation, manifest mutation, contract-identity mutation,
   extra-file, existing-output, and dirty-tree conditions fail closed;
12. two fresh invented checkpoints have identical canonical manifests; and
13. no criterion, normalized value, score, portfolio, or county-status field is
    emitted.

## Acceptance Decision

The user accepted this revised contract on 2026-10-09 for machine-readable
contract implementation, invented fixtures, synthetic tests, and a second
readiness review only. Acceptance does not authorize opening the private
snapshot, building real county evidence, calculating criteria, or producing a
portfolio.
