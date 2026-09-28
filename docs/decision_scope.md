# Decision Scope

## Supported decision

Which U.S. county-equivalents should advance into a standardized first-stage
technical-assistance assessment for healthcare-continuity energy resilience,
given at most 25 assessment slots in one 12-month planning cycle?

One slot means that one county advances to structured feasibility assessment.
It does not mean that the county receives equipment, funding, engineering
approval, procurement authorization, or emergency-response priority.

## Unit and universe

The unit is county or county-equivalent. The reference universe contains 3,144
units in the 50 states and District of Columbia. The accepted automated analysis
contains 3,133 comparable units after two exact historical FIPS replacements.
Eleven units remain explicitly `OUT_OF_SCOPE` because the source geographies do
not support a defensible one-to-one match.

## Output

Each unit receives `ADVANCE`, `ABSTAIN`, `NOT_ADVANCED`, or `OUT_OF_SCOPE`,
together with evidence provenance, uncertainty flags, primary selection
frequency, and compact sensitivity diagnostics.

## Intended user

The intended user is a hypothetical public-interest planning team allocating a
limited queue of technical-assistance assessments. A healthcare provider,
commercial vendor, or investor may use the output only as public-need screening
context, not as a facility or investment decision.

## Non-goals

The project does not:

- estimate unmet healthcare demand;
- measure facility-level backup-power readiness;
- forecast outages or health outcomes;
- prescribe equipment or engineering designs;
- optimize procurement or funding awards;
- estimate project cost, revenue, or return; or
- rank emergency response priority.
