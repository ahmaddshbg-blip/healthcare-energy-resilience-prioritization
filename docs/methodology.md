# Methodology

## Method family

The project uses robust preference-scenario portfolio analysis. Hard evidence
rules are applied before value aggregation. Each declared evidence and
preference configuration produces an at-most-`K` county portfolio. Stability
across configurations determines the decision status.

No mathematical optimizer is used because cardinality is the only portfolio
constraint. A deterministic top-`K` operation is clearer and produces the same
decision without decorative optimization.

## Primary criteria

The four primary criteria are:

1. HHS emPOWER electricity-dependent DME count percentile;
2. HHS emPOWER DME rate per 1,000 Medicare beneficiaries percentile;
3. FEMA National Risk Index composite risk score divided by 100; and
4. maximum eligible Primary Care HPSA score divided by 25.

HRSA health-center presence is contextual evidence. It is not a monotonic score
criterion because site presence can indicate either existing service capacity
or underlying need.

## Preference and uncertainty design

Five fixed preference profiles represent balanced, burden-magnitude, burden-
prevalence, hazard-emphasis, and shortage-emphasis perspectives. The 20 primary
configurations combine those profiles with two masked-count bounds and two
small-denominator rate bounds at capacity 25.

The full 480-configuration design adds one-factor sensitivities for capacities
10 and 50, denominator thresholds 500 and 2,000, proposed-withdrawal HPSA
records, and 18 hazard-specific FEMA families. The configurations are not a
probability distribution and selection frequency is not a calibrated
probability.

## Selection and status

Calculations use `float64` and explicit deterministic ordering. An unresolved
tie crossing the portfolio boundary leaves slots unused; county FIPS is never a
substantive tie-breaker.

- `ADVANCE`: selected in all 20 primary configurations.
- `NOT_ADVANCED`: selected in none of the 20 primary configurations.
- `ABSTAIN`: selected in one through 19 primary configurations or affected by
  an unresolved evidence or boundary condition.
- `OUT_OF_SCOPE`: excluded under the accepted geography contract.

## Anti-tuning rule

The method, configurations, tie behavior, and status rules were fixed before
any complete county portfolio was calculated. Later changes must preserve prior
outputs, record a new content identity, and disclose whether observed results
influenced the change.
