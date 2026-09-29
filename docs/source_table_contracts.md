# Source Table Contracts

## Purpose

`configs/source_tables.json` freezes the structural expectations for the five
CSV inputs and the three sheets in the HHS emPOWER historical workbook. It is
tied to the accepted private snapshot but contains no source records. The
contract exists to stop execution when a publisher changes a file shape or
when a parser would silently reinterpret a source.

Metadata JSON, XML, and workbook files are not analytical tables. Their exact
files remain protected by the source manifest's byte counts and SHA-256 hashes;
they are not given artificial table keys.

## Contracted tables

| Table or sheet | Encoding | Data rows | Header cells | Named columns | Record key |
|---|---:|---:|---:|---:|---|
| HHS emPOWER county CSV | UTF-8 | 3,233 | 18 | 18 | unique `OBJECTID` |
| FEMA NRI counties CSV | UTF-8 | 3,232 | 467 | 467 | unique `NRI_ID` |
| HRSA Primary Care HPSA CSV | UTF-8 | 80,199 | 66 | 65 | nonunique `HPSA ID` |
| HRSA Health Center Sites CSV | UTF-8 | 19,283 | 56 | 55 | unique `BPHC Assigned Number` |
| Census population-estimates CSV | Windows-1252 | 3,195 | 99 | 99 | unique `SUMLEV + STATE + COUNTY` |
| HHS historical `State` sheet | binary XLSX | 56 | 65 | 65 | unique `State_FIPS_Code` |
| HHS historical `County` sheet | binary XLSX | 3,228 | 68 | 68 | unique `FIPS_Code` |
| HHS historical `Zip Code` sheet | binary XLSX | 31,919 | 69 | 69 | unique `Zip_Code` |

The Census row count is the physical raw-file count. It consists of 3,144
`SUMLEV=050` county rows and 51 state-summary rows. The table contract does not
filter either group. The HPSA and Health Center Sites CSV headers each contain
one trailing empty header cell while every data row has only the named fields;
that publisher artifact is frozen explicitly rather than silently discarded.

`HPSA ID` is not a row key. The frozen file contains 80,199 component rows,
17,847 distinct HPSA IDs, and 4 exact duplicate rows beyond the first copy. The
contract preserves those facts and does not create a synthetic identifier.

## Columns and types

Every table declares the columns required by the accepted decision and context
design. Each required column has a parser type, a null policy, and an evidence
source. Publisher field metadata is used where available; otherwise the Gate 1
structural profile is named explicitly. Identifier columns are strings so that
leading zeroes are not lost.

An ordered-header SHA-256 protects every complete header, including columns not
listed individually as required. This combination keeps the public contract
readable while still detecting any added, removed, renamed, or reordered
column.

## Failure policy

Validation must stop before transformation when any of these conditions is
observed:

- a table or workbook sheet is missing or unexpected;
- text encoding, byte-order mark, CSV dialect, or line ending differs;
- physical row count, header width, named-column count, or data-row width
  differs;
- the ordered-header fingerprint differs;
- a required column is missing or has a different parser type;
- key nullability, distinct count, or duplicate count differs; or
- the exact duplicate-row count differs.

A current-source refresh is expected to change row counts and possibly file
shape. It must create a new immutable snapshot and a reviewed contract; it may
not weaken or overwrite the frozen contract.

## Current executable boundary

The repository validates the contract document and compares invented observed
profiles with invented contracts. Synthetic tests cover encoding, row count,
header, required type, table or sheet presence, key cardinality, and duplicate
failure paths. No public command yet parses the real source tables, normalizes
county identifiers, reconciles geography, or calculates criteria, scores,
portfolios, or statuses.
