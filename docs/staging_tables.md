# Source-Preserving Staging Tables

## Purpose

`configs/staging_tables.json` defines the first record-level boundary after a
source has passed frozen-file and source-table verification. It does not read
private data, reconcile geography, or calculate analytical fields. Its purpose
is to make any later extraction fail unless source rows and declared meanings
are preserved.

The contract is bound to both the accepted source snapshot and the exact
SHA-256 of `configs/source_tables.json`. A changed source-table contract
therefore requires a reviewed staging-contract update rather than silently
changing the extraction surface.

## Staged tables

| Staging table | Source rows | Retained semantic key | Key meaning |
|---|---:|---|---|
| `stg_hhs_empower_county` | 3,233 | `OBJECTID` | unique source identifier |
| `stg_fema_nri_counties` | 3,232 | `NRI_ID` | unique source identifier |
| `stg_hrsa_primary_care_hpsa` | 80,199 | `HPSA ID` | nonunique designation identifier |
| `stg_hrsa_health_center_sites` | 19,283 | `BPHC Assigned Number` | unique source identifier |
| `stg_census_county_population_2025` | 3,195 | `SUMLEV + STATE + COUNTY` | unique source composite |
| `stg_hhs_empower_history_county` | 3,228 | `FIPS_Code` | unique source identifier |

Every source data row must produce exactly one staging row in source order. A
generated `source_row_number` records the one-based physical data-row ordinal;
it is lineage, not a replacement semantic key. Repeated identifiers and exact
duplicate rows remain repeated.

The HHS historical `State` and `Zip Code` sheets remain structurally verified
but are explicitly validation-only. State is not the accepted county decision
unit, and allocating ZIP Code records to counties would require a geographic
method that has not been accepted.

## Column and type policy

Each staging table retains the corresponding source-table contract's
`required_columns` in declared order. Names, parser types, and null policies are
inherited without overrides. The source-table contract hash makes that
reference immutable.

This is a source-preserving projection, not a claim that every physical source
column is copied. Complete raw files remain immutable and authoritative. In
particular, only the contracted September fields from the HHS historical county
sheet are staged in this increment. Other monthly fields cannot enter analysis
until a reviewed contract extension explicitly defines their retained columns
and types.

The synthetic extractor implements these output representations:

- `STRING`: nonempty source text is retained exactly, including leading zeroes,
  spaces, case, and labels such as `Not Applicable`;
- `INTEGER`: a strictly parseable integer;
- `NUMBER`: a finite `Decimal`, avoiding an unnecessary binary-float rewrite;
- `DATETIME`: a parsed Python `datetime`; and
- an empty source cell becomes null only when the source-table contract allows
  null.

Additional source columns are not emitted. Retained columns are never renamed.

## Semantic preservation

Staging is prohibited from filtering, sorting, deduplicating, aggregating,
imputing, trimming text, replacing geography identifiers, or interpreting
source categories. Consequently:

- HHS displayed values of 11 remain 11; staging does not infer a hidden count
  from the publisher's 1-through-10 masking rule;
- FEMA `Not Applicable` ratings remain text and are not converted to zero;
- HPSA component rows, repeated IDs, and exact duplicates remain present;
- HRSA site status values remain present without an active-site filter;
- all 3,144 Census county rows and 51 state-summary rows remain present, with no
  `SUMLEV` filter; and
- historical HHS evidence remains context, not a forecast or criterion.

## Executable boundary

`src/healthcare_resilience/staging.py` accepts already-opened row mappings and
returns in-memory staging rows. It contains no CSV or workbook opener, no
private path, and no checkpoint writer. Current tests use invented records only
and verify row order, lineage, text and masking preservation, null handling,
numeric parsing, duplicate preservation, missing-column failure, type failure,
row-count failure, and contract-hash failure.

No real source record has been extracted by this increment. Geography
reconciliation, joined county evidence, criteria, scores, portfolios, and
county statuses remain outside the implemented boundary.
