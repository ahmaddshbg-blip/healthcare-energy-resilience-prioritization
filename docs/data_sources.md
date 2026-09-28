# Data Sources

## Source roles

| Source | Analytical role | Update behavior | Primary caution |
|---|---|---|---|
| HHS emPOWER county data | Electricity-dependent DME burden count and Medicare-relative rate | Monthly | Counts 1-10 are masked as 11; Medicare scope only |
| FEMA National Risk Index county data | Composite and hazard-specific modeled risk evidence | Periodic versioned release | Broad planning model, not local risk assessment or forecast |
| HRSA Primary Care HPSA | Current administrative shortage evidence | Daily | Component rows and repeated IDs are not independent shortages |
| HRSA Health Center Sites | Contextual active-site presence | Daily | Not all facilities; no backup-power or capacity evidence |
| Census county population estimates | Reference geography and population context | Annual vintage | Not the denominator for Medicare DME prevalence |

Official URLs and attribution requirements are listed in
[Data Attribution](../DATA_ATTRIBUTION.md).

## Audited scale

The complete audited family contains 144,294 material rows, including 35,203
rows in the HHS historical workbook. No sampling is required. The size is
appropriate for local SQL and Python processing and does not justify a
distributed-computing claim.

## Geography

The Census Vintage 2025 file defines 3,144 county-equivalents across the 50
states and District of Columbia. HHS supports 3,133 comparable units after two
exact historical-name replacements. Two Alaska successor areas and nine
Connecticut planning regions remain outside automated comparison because the
available HHS geography cannot be allocated without making unsupported
assumptions.

## Frozen and current sources

The accepted frozen snapshot is privately preserved and identified by file
hashes. Its snapshot identity is
`cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb`.
It is not included in Git.

`configs/sources.json` records every required filename, private relative path,
retrieval time, byte count, SHA-256, publisher, official URL, analytical role,
and use note. The snapshot identity is SHA-256 over the explicitly ordered
UTF-8 lines `filename|bytes|sha256`; the order is itself stored and validated.
Official current-source URLs are mutable, so a newly downloaded file is a new
evidence vintage rather than a reproduction of the frozen snapshot.
