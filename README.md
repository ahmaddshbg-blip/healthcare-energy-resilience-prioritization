# Healthcare Energy Resilience Assessment Prioritization

A reproducible public-data decision workflow for prioritizing a limited number
of U.S. county-equivalents for first-stage healthcare-continuity energy-
resilience technical-assistance assessment.

The workflow is designed to support an **at-most-25-county assessment queue for
one 12-month planning cycle**. Selection does not award funding, authorize an
engineering design, certify facility readiness, predict an outage, or establish
investment return.

## Current status

The decision contract, data feasibility audit, analytical method, and
engineering design are complete. Machine-readable source and method contracts,
eight source-table contracts, the deterministic 480-configuration manifest,
synthetic contract tests, and a hash-only frozen-snapshot verifier are
implemented. The accepted private snapshot passes exact-set, byte-size, and
SHA-256 verification for all 15 required files. No source record has entered
the analytical pipeline, and no county-level criterion, portfolio, or final
status has been calculated or published.

## Decision output

The future reviewed output will assign each reference county-equivalent one of
four statuses:

- `ADVANCE`: selected under all 20 primary evidence and preference
  configurations;
- `ABSTAIN`: selected under some but not all primary configurations;
- `NOT_ADVANCED`: selected under none of the primary configurations; or
- `OUT_OF_SCOPE`: excluded because the accepted public sources do not support a
  defensible automated geography match.

The output is a screening aid for deciding where a standardized feasibility
assessment should occur next. It is not a final operational recommendation.

## Evidence base

The design combines:

- HHS emPOWER Medicare administrative evidence on electricity-dependent durable
  medical equipment and related services;
- FEMA National Risk Index modeled hazard-risk evidence;
- HRSA Primary Care Health Professional Shortage Area designations;
- HRSA Health Center site presence as contextual evidence; and
- U.S. Census county geography and population estimates.

The audited source family contains 144,294 material rows. That scale supports a
local Python and DuckDB workflow; it does not justify Spark or distributed
processing. Raw source files are not redistributed in this repository. See
[data sources](docs/data_sources.md),
[source table contracts](docs/source_table_contracts.md), and
[data attribution](DATA_ATTRIBUTION.md).

## Method summary

The accepted design uses robust preference-scenario portfolio analysis. Four
criteria are evaluated under five declared preference profiles, bounded source
uncertainty, three capacity scenarios, FEMA hazard-family sensitivities, and an
HPSA-status sensitivity. The configuration set contains 20 primary and 480
total deterministic configurations.

Boundary ties are not broken with county identifiers: unresolved ties leave
assessment slots unused. The complete public explanation is in
[methodology](docs/methodology.md).

## Reproducibility boundary

Real source data and generated runs remain outside Git under the private
`HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT`. The future pipeline will support:

1. synthetic tests with no real source data;
2. frozen reproduction from an exact hash-verified snapshot; and
3. current-source refresh into a separate immutable snapshot.

A refresh will never silently replace or impersonate the frozen analytical
snapshot. The current executable surface validates file and table contracts,
tests invented structural profiles, and hashes frozen files without running a
real-data analytical parser or calculating county results. See
[reproducibility](docs/reproducibility.md).

## Claim boundary

This project may prioritize county-level assessment attention from incomplete
public evidence. It cannot determine facility backup-power readiness, emergency
response priority, causal health outcomes, project engineering requirements,
procurement choices, funding awards, or commercial returns. See
[limitations](docs/limitations.md) and [decision scope](docs/decision_scope.md).

## Repository policy

The MIT License applies to original code and documentation in this repository.
It does not relicense the underlying HHS, FEMA, HRSA, or Census data. Source-
specific terms, attribution, masking, and non-endorsement requirements remain
applicable.
