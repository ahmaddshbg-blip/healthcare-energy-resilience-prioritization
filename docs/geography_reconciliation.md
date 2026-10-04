# Geography Reconciliation Specification

Status: **CONTROLLED BUILD BLOCKED - CONTRACT-TO-SNAPSHOT COUNT MISMATCH**

This specification defines how the accepted source-preserving staging tables
may later be assigned to the frozen U.S. county-equivalent reference universe.
It defines rules and acceptance tests only. It does not execute a join, create
normalized data, aggregate evidence, calculate criteria, or produce county
decisions.

## Evidence boundary

The specification is downstream of the verified frozen staging build:

- source snapshot:
  `cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb`;
- staging build:
  `238da712ad4a9d08b602e89ae8eaa2446871de1e6d84f2dc162ac8a69c5f3b0d`;
- execution-code commit:
  `177f6d372ed6c200dc94137fb8050e10abc1bded`;
- six staging tables and 112,370 source-preserving rows; and
- independently verified schemas, source-row lineage, canonical contents,
  artifact sizes, and file hashes.

Acceptance of that build proves staging integrity only. Geography remains a
separate controlled transformation.

## Decision

Use the Census Vintage 2025 county rows as the only reference geography.
Reconcile records only by exact five-character county FIPS. Do not use county
names, state names, abbreviations, ZIP Codes, coordinates, fuzzy matching,
spatial overlays, or population-weighted allocation.

Two HHS historical-name changes are the only allowed one-to-one replacements.
No Alaska or Connecticut predecessor value may be divided among successor
geographies.

## Facts, interpretations, and unknowns

### Facts

- The Census file contains 3,144 `SUMLEV=050` county-equivalent rows and 51
  state-summary rows.
- Current HHS evidence directly matches 3,131 reference units. Two accepted
  name-only replacements increase supported eligibility to 3,133 units.
- Two Alaska successor areas and nine Connecticut planning regions cannot be
  assigned HHS values without an unsupported allocation.
- FEMA contains one direct record for every reference unit.
- HPSA and health-center sources contain repeated county assignments, records
  outside the reference universe, and records without usable county FIPS.
- Absence of a valid HRSA record is allowed and is not a failed core join.

### Interpretation

FIPS is an identifier, not a number. Geography processing may validate and map
it, but may not repair malformed text. A county name is audit context only and
may never override a FIPS result.

### Unknowns

- Cross-platform identity of a future geography checkpoint is untested.
- Future publisher vintages may adopt different boundaries or codes.
- No claim is made yet about real reconciliation runtime or memory use.

These unknowns do not justify a permissive fallback. A changed or ambiguous
geography must stop for review.

## Canonical FIPS contract

A canonical county FIPS must satisfy `^[0-9]{5}$` and remain a string.

The implementation must not:

- cast FIPS to an integer;
- left-pad, trim, case-fold, or otherwise repair source text;
- infer county identity from names or state labels;
- assign a source row to more than one reference unit; or
- replace a code unless the source and replacement are explicitly permitted
  below.

For Census county rows, canonical FIPS is the exact concatenation of a
two-character `STATE` and three-character `COUNTY`. Both components must
already satisfy their declared widths. Only `SUMLEV=050` rows enter the
reference universe. The 51 state-summary rows remain accounted for but do not
receive county identities.

## Reference universe

The future `county_reference` table must contain exactly 3,144 rows and these
fields:

- `canonical_fips`;
- `state_fips`;
- `county_code`;
- Census state and county names;
- Census 2025 population;
- `decision_scope_status`; and
- `scope_reason`.

`decision_scope_status` is limited to:

- `ELIGIBLE` for exactly 3,133 units; and
- `OUT_OF_SCOPE` for exactly 11 units.

The 11 `OUT_OF_SCOPE` FIPS are:

```text
02063 02066
09110 09120 09130 09140 09150 09160 09170 09180 09190
```

Territories are not reference units and therefore do not receive
`OUT_OF_SCOPE` county rows.

## Allowed replacements and unresolved legacies

Only these HHS current and HHS county-history replacements are permitted:

| Source FIPS | Canonical FIPS | Rule |
|---|---|---|
| `02270` | `02158` | exact historical-name replacement |
| `46113` | `46102` | exact historical-name replacement |

The replacements are one-to-one identifier changes and do not allocate or
transform a value. The same codes appearing in another source must stop for
review rather than silently invoking an HHS-specific rule.

These HHS legacy codes remain unresolved and receive no canonical FIPS:

```text
02261
09001 09003 09005 09007 09009 09011 09013 09015
```

`02261` is the predecessor of two Alaska reference units. The eight Connecticut
legacy counties do not map one-to-one to the nine planning regions. These rows
must remain traceable but cannot enter county evidence.

## Mapping statuses

Every staging row must receive exactly one mapping status:

- `DIRECT_REFERENCE`: valid source FIPS equals one reference FIPS;
- `EXACT_REPLACEMENT`: one of the two permitted HHS replacements;
- `UNRESOLVED_LEGACY_GEOGRAPHY`: an accepted Alaska or Connecticut legacy
  source code that cannot be allocated;
- `OUTSIDE_REFERENCE_UNIVERSE`: valid FIPS outside the 50-states-plus-DC
  reference universe;
- `MISSING_SOURCE_FIPS`: source geography is null or empty under an accepted
  nullable source contract;
- `INVALID_SOURCE_FIPS`: nonempty source geography does not satisfy the
  five-digit contract; or
- `STATE_SUMMARY_NOT_COUNTY`: a Census non-county summary row.

Only `DIRECT_REFERENCE` and `EXACT_REPLACEMENT` may have non-null
`canonical_fips`. No row may be dropped, duplicated, or assigned multiple
statuses.

## Source-specific rules

### Census reference

- Input: `stg_census_county_population_2025`.
- Use only `SUMLEV=050` to construct the 3,144-row reference.
- Account separately for exactly 51 state-summary rows.
- Require unique canonical FIPS and positive non-null population.
- Census names are authoritative display labels, not matching keys for other
  sources.

### HHS emPOWER current county

- Input: `stg_hhs_empower_county`.
- Geography field: `FIPS_Code`.
- Permit direct matches and the two HHS replacements only.
- Retain the nine unresolved legacy rows without allocating them.
- Retain territorial and missing-FIPS rows outside county evidence.
- Core eligibility uses this current table, not the historical table.

Frozen-snapshot reconciliation must produce:

| Status | Rows |
|---|---:|
| `DIRECT_REFERENCE` | 3,131 |
| `EXACT_REPLACEMENT` | 2 |
| `UNRESOLVED_LEGACY_GEOGRAPHY` | 9 |
| `OUTSIDE_REFERENCE_UNIVERSE` | 86 |
| `MISSING_SOURCE_FIPS` | 5 |
| **Total** | **3,233** |

### HHS emPOWER county history

- Input: `stg_hhs_empower_history_county`.
- Geography field: `FIPS_Code`.
- Apply the same direct, replacement, unresolved, and outside-universe rules.
- Use this source for traceable historical context only; it cannot create or
  repair current eligibility.

Frozen-snapshot reconciliation must produce 3,131 direct, 2 replacement, 9
unresolved legacy, and 86 outside-universe rows, totaling 3,228.

### FEMA National Risk Index

- Input: `stg_fema_nri_counties`.
- Geography field: `STCOFIPS`.
- Permit direct reference matches only.
- Require exactly one direct FEMA row for each of the 3,144 reference units.
- Retain exactly 88 territorial rows as `OUTSIDE_REFERENCE_UNIVERSE`.
- Any replacement, duplicate reference match, or missing reference unit is a
  failure.

### HRSA Primary Care HPSA

- Input: `stg_hrsa_primary_care_hpsa`.
- Primary geography field:
  `State and County Federal Information Processing Standard Code`.
- Fallback audit field: `Common State County FIPS Code`.
- If both fields are valid, they must agree exactly.
- If only one field is valid, use that field and record which field supplied
  the mapping.
- If neither is valid, classify the row as missing or invalid and retain it
  outside county evidence.
- Permit direct reference matches only. Do not invoke HHS replacements.
- Do not deduplicate, filter statuses, select designation types, or aggregate
  HPSA scores during geography reconciliation.

Frozen-snapshot reconciliation must account for 78,883 direct-reference rows,
393 outside-universe rows, and 923 rows without a valid county FIPS, totaling
80,199. The two FIPS fields must have zero valid-value conflicts.

### HRSA health-center sites

- Input: `stg_hrsa_health_center_sites`.
- Geography field:
  `State and County Federal Information Processing Standard Code`.
- Permit direct reference matches only.
- Missing or invalid FIPS remains explicit and cannot be inferred from address,
  ZIP Code, site name, or coordinates.
- Do not aggregate by county or location type during geography reconciliation.

Frozen-snapshot reconciliation must account for 18,993 direct-reference rows,
213 outside-universe rows, and 77 missing or invalid rows, totaling 19,283.

## Planned private outputs

If this specification is accepted and later implemented, geography processing
may create only:

1. one 3,144-row `county_reference` table;
2. one row-preserving geography-map table for each of the six staging tables;
   and
3. one geography manifest containing input identities, rule identity, counts,
   schema fingerprints, canonical hashes, code commit, and environment.

Each source geography-map row must include:

- `source_table_id`;
- `source_row_number`;
- original source geography value or values;
- nullable `canonical_fips`;
- `mapping_status`;
- stable `mapping_rule_id`; and
- nullable diagnostic reason.

These are private checkpoints. They are not a joined county evidence table.
No source measure may be aggregated or combined across source families at this
stage.

## Determinism and lineage

- Preserve every staging row and its `source_row_number`.
- Sort serialized map outputs by `source_row_number`; sort the county reference
  by `canonical_fips`.
- Bind the geography manifest to the staging build identity, staging manifest
  hash, geography-rule hash, code commit, and locked environment.
- Publish atomically into a new content-addressed private path and refuse
  overwrite.
- Reopen every artifact and verify schema, row count, mapping counts,
  canonical content, byte count, and file hash.

## Fail-closed conditions

Stop without publishing a complete geography checkpoint when:

- the input staging build or any artifact fails verification;
- Census does not yield exactly 3,144 unique county FIPS plus 51 summaries;
- any canonical FIPS is malformed or duplicated;
- the eligible and `OUT_OF_SCOPE` counts are not 3,133 and 11;
- the `OUT_OF_SCOPE` set differs from the declared 11 FIPS;
- an undeclared replacement or allocation is attempted;
- either HHS replacement source code appears in FEMA or HRSA, whether or not a
  replacement is attempted;
- an unresolved Alaska or Connecticut row receives a canonical FIPS;
- an eligible unit lacks current HHS or FEMA core evidence;
- FEMA does not map one-to-one to all 3,144 reference units;
- valid HPSA FIPS fields conflict;
- any staging row is lost, duplicated, reordered without recorded lineage, or
  mapped to more than one county;
- names, ZIP Codes, coordinates, or fuzzy logic affect a mapping;
- mapping counts differ from the frozen invariants above; or
- a completed artifact differs from its manifest.

## Acceptance test specification

All implementation tests must use invented FIPS and labels unless a test is
explicitly validating the accepted constant sets. No fixture may copy a real
source record or measure value.

### Positive contract tests

| Test ID | Required evidence |
|---|---|
| `GEO-P01` | Five-character FIPS remains text and preserves leading zeroes. |
| `GEO-P02` | Census components produce one unique canonical county key. |
| `GEO-P03` | State-summary rows are accounted for but excluded from the county reference. |
| `GEO-P04` | A direct source FIPS maps to exactly one reference unit. |
| `GEO-P05` | Each of the two HHS replacements maps one-to-one with its rule ID. |
| `GEO-P06` | All 11 declared reference units receive `OUT_OF_SCOPE`. |
| `GEO-P07` | Accepted legacy HHS rows remain unresolved with null canonical FIPS. |
| `GEO-P08` | Territorial rows remain outside the reference universe, not `OUT_OF_SCOPE`. |
| `GEO-P09` | Agreeing HPSA FIPS fields produce one direct mapping. |
| `GEO-P10` | One valid HPSA field may serve as a recorded fallback when the other is invalid. |
| `GEO-P11` | Missing site FIPS remains explicit and does not use address or ZIP fallback. |
| `GEO-P12` | Every source map preserves input row count and source-row lineage. |
| `GEO-P13` | Input-row shuffling does not change canonical outputs or hashes. |
| `GEO-P14` | Geography artifacts contain no aggregation or cross-source columns. |
| `GEO-P15` | Independent artifact verification reproduces all manifest claims. |

### Negative and fail-closed tests

| Test ID | Required rejection |
|---|---|
| `GEO-N01` | Integer, short, long, signed, decimal, whitespace-padded, or nondigit FIPS. |
| `GEO-N02` | Automatic trimming, padding, numeric coercion, or name-based repair. |
| `GEO-N03` | Duplicate or missing Census county key. |
| `GEO-N04` | Reference count other than 3,144 or state-summary count other than 51. |
| `GEO-N05` | Replacement other than the accepted two. |
| `GEO-N06` | Either HHS replacement source code appears in FEMA or HRSA. |
| `GEO-N07` | Allocation of `02261` to either Alaska successor. |
| `GEO-N08` | Allocation of a legacy Connecticut county to a planning region. |
| `GEO-N09` | `OUT_OF_SCOPE` set or count differs from the accepted 11. |
| `GEO-N10` | FEMA duplicate, missing reference county, or replacement. |
| `GEO-N11` | Two valid HPSA FIPS fields disagree. |
| `GEO-N12` | Missing HRSA FIPS inferred from address, ZIP, name, or coordinates. |
| `GEO-N13` | Source row loss, duplication, one-to-many assignment, or lineage change. |
| `GEO-N14` | Frozen mapping count differs from a declared source invariant. |
| `GEO-N15` | Existing output path, dirty release tree, input mutation, or artifact tampering. |

### Frozen-build acceptance checks

Before any real geography output can be accepted, one controlled run must show:

- verified input staging build identity;
- exact source-specific mapping counts from this specification;
- a 3,144-row reference with 3,133 eligible and 11 `OUT_OF_SCOPE` rows;
- one current HHS and one FEMA core record for every eligible county;
- no allocation of unresolved legacy geography;
- row preservation across all six source maps;
- deterministic canonical hashes across two fresh local outputs; and
- a second clean Linux or Colab reproduction before cross-platform equality is
  claimed.

## Implementation and review result

The specification was accepted for synthetic implementation on 2026-10-04.
The machine-readable contract, schemas, deterministic reconciliation logic,
checkpoint controls, trusted staging-input boundary, and all 30 named
acceptance tests are implemented. The full repository suite passes 117 tests.
One explicitly authorized production attempt accepted the staging evidence but
failed closed on the contracted `DIRECT_REFERENCE` count for
`stg_hhs_empower_history_county`. A read-only representation audit found all
3,228 `FIPS_Code` values in that table carry trailing whitespace, while this
specification requires exact five-digit text and forbids trimming or repair.
No geography checkpoint was published. See the separate
[geography readiness review](geography_readiness.md). Do not rerun until the
snapshot-versus-specification decision is resolved and a new explicit
authorization is given.

Acceptance authorized only:

1. a machine-readable geography contract and JSON Schema;
2. implementation using invented fixtures;
3. the positive and negative tests above; and
4. a readiness review after the complete synthetic suite passes.

It did not authorize opening the private Parquet artifacts for geography
execution, creating real geography maps, constructing county evidence,
aggregating HPSA or site records, or calculating analytical criteria.
