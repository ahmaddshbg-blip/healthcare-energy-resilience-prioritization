# Data Attribution and Reuse Notes

This repository does not redistribute the audited raw source files. Users must
obtain current files from the official publishers and preserve their own
retrieval timestamps, versions, hashes, and use conditions.

## HHS emPOWER

- Program and historical files:
  <https://empowerprogram.hhs.gov/about-empowermap.html>
- Public REST service:
  <https://services2.arcgis.com/ZQ4jTQn6k7VPXEwO/arcgis/rest/services/HHS_emPOWER_REST_Service_Public/FeatureServer>
- Audited geography: county layer `2`.
- Attribution: CMS, HHS.

The data represent Medicare administrative evidence, not the full population.
Cells from 1 through 10 are masked and displayed as 11. The source metadata
does not state a named open-data license, so public access must not be described
as unrestricted permission to redistribute the raw files.

## FEMA National Risk Index

- County feature layer:
  <https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0>
- Technical documentation:
  <https://www.fema.gov/sites/default/files/documents/fema_national-risk-index-technical-documentation.pdf>
- Item metadata and terms:
  <https://www.arcgis.com/sharing/rest/content/items/39485e8035d446a5bff03259508ae355/info/metadata/metadata.xml?format=default&output=html>
- Audited version: December 2025, v1.20.0.

FEMA data support broad planning comparisons and do not replace local risk
assessment. This project is not a FEMA product and is not endorsed by FEMA or
the U.S. Department of Homeland Security.

## HRSA Primary Care HPSA

- Dashboard and context:
  <https://data.hrsa.gov/topics/health-workforce/shortage-areas/dashboard>
- Official CSV:
  <https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv>

The source contains designation components and repeated HPSA identifiers. Rows
must not be counted as independent shortages without status, type, component,
and duplication controls.

## HRSA Health Center Sites

- Download catalogue:
  <https://data.hrsa.gov/data/download?titleFilter=Health+Center>
- Official CSV:
  <https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv>

The roster covers active Health Center Program service-delivery and look-alike
sites. It is not a census of all healthcare facilities and contains no evidence
of backup-power readiness or service capacity.

## U.S. Census Bureau

- Audited Vintage 2025 county population file:
  <https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv>

The Census file supplies the reference county-equivalent universe and optional
population context. Medicare beneficiaries, not total population, are the
defensible denominator for the emPOWER DME prevalence measure.

## License boundary

The repository's MIT License covers only original code and documentation. It
does not alter publisher ownership, terms, attribution requirements, privacy
rules, or non-endorsement conditions for source data.
