from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from healthcare_resilience.contracts import load_json
from healthcare_resilience.geography import validate_geography_contract

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"


def synthetic_geography_contract() -> dict:
    contract = deepcopy(load_json(CONFIG_DIR / "geography.json"))
    reference = contract["reference"]
    reference["expected_county_count"] = 15
    reference["expected_state_summary_count"] = 2
    reference["eligible_count"] = 4
    expected = {
        "stg_census_county_population_2025": (
            17,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 15),
             ("STATE_SUMMARY_NOT_COUNTY", ["STATE_SUMMARY_NOT_COUNTY"], 2)],
        ),
        "stg_hhs_empower_county": (
            15,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 2),
             ("EXACT_REPLACEMENT", ["EXACT_REPLACEMENT"], 2),
             ("UNRESOLVED_LEGACY_GEOGRAPHY", ["UNRESOLVED_LEGACY_GEOGRAPHY"], 9),
             ("OUTSIDE_REFERENCE_UNIVERSE", ["OUTSIDE_REFERENCE_UNIVERSE"], 1),
             ("MISSING_SOURCE_FIPS", ["MISSING_SOURCE_FIPS"], 1)],
        ),
        "stg_hhs_empower_history_county": (
            14,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 2),
             ("EXACT_REPLACEMENT", ["EXACT_REPLACEMENT"], 2),
             ("UNRESOLVED_LEGACY_GEOGRAPHY", ["UNRESOLVED_LEGACY_GEOGRAPHY"], 9),
             ("OUTSIDE_REFERENCE_UNIVERSE", ["OUTSIDE_REFERENCE_UNIVERSE"], 1)],
        ),
        "stg_fema_nri_counties": (
            16,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 15),
             ("OUTSIDE_REFERENCE_UNIVERSE", ["OUTSIDE_REFERENCE_UNIVERSE"], 1)],
        ),
        "stg_hrsa_primary_care_hpsa": (
            4,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 2),
             ("OUTSIDE_REFERENCE_UNIVERSE", ["OUTSIDE_REFERENCE_UNIVERSE"], 1),
             ("WITHOUT_VALID_SOURCE_FIPS", ["MISSING_SOURCE_FIPS", "INVALID_SOURCE_FIPS"], 1)],
        ),
        "stg_hrsa_health_center_sites": (
            4,
            [("DIRECT_REFERENCE", ["DIRECT_REFERENCE"], 1),
             ("OUTSIDE_REFERENCE_UNIVERSE", ["OUTSIDE_REFERENCE_UNIVERSE"], 1),
             ("WITHOUT_VALID_SOURCE_FIPS", ["MISSING_SOURCE_FIPS", "INVALID_SOURCE_FIPS"], 2)],
        ),
    }
    for rule in contract["source_rules"]:
        total, counts = expected[rule["staging_table_id"]]
        rule["expected_total_count"] = total
        rule["expected_mapping_counts"] = [
            {"count_id": count_id, "statuses": statuses, "expected_count": count}
            for count_id, statuses, count in counts
        ]
    validate_geography_contract(
        contract,
        load_json(CONFIG_DIR / "geography.schema.json"),
        enforce_accepted_contract=False,
    )
    return contract


def synthetic_geography_rows() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_geography_rows.json")
