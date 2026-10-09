from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import load_json
from healthcare_resilience.county_evidence import (
    CountyEvidenceError,
    build_county_evidence,
    validate_county_evidence_contract,
)
from healthcare_resilience.hashing import sha256_json
from tests.county_evidence_support import (
    CONFIG_DIR,
    ROOT,
    synthetic_county_evidence_contract,
    synthetic_county_evidence_inputs,
)


def _build() -> tuple[list[dict], dict, dict, dict]:
    contract = synthetic_county_evidence_contract()
    staging, geography = synthetic_county_evidence_inputs()
    rows = build_county_evidence(staging, geography, contract)
    return rows, contract, staging, geography


def test_public_county_evidence_contract_is_valid() -> None:
    validate_county_evidence_contract(
        load_json(CONFIG_DIR / "county_evidence.json"),
        load_json(CONFIG_DIR / "county_evidence.schema.json"),
        ROOT,
    )


def test_contract_rejects_input_identity_and_source_field_drift() -> None:
    contract = load_json(CONFIG_DIR / "county_evidence.json")
    schema = load_json(CONFIG_DIR / "county_evidence.schema.json")
    changed_identity = deepcopy(contract)
    changed_identity["input_geography_checkpoint_identity"] = "0" * 64
    with pytest.raises(CountyEvidenceError, match="accepted input_geography_checkpoint_identity differs"):
        validate_county_evidence_contract(changed_identity, schema)
    changed_field = deepcopy(contract)
    changed_field["source_roles"][0]["required_fields"].append("Invented Extra")
    with pytest.raises(CountyEvidenceError, match="source role semantics differ"):
        validate_county_evidence_contract(changed_field, schema)


def test_one_row_per_reference_and_no_analytical_fields() -> None:
    rows, contract, _, _ = _build()
    assert [row["canonical_fips"] for row in rows] == ["88001", "88003", "88005", "88007"]
    assert all(list(row) == [item["name"] for item in contract["output_columns"]] for row in rows)
    assert not any(name.startswith("C_") for name in rows[0])
    assert not {"score", "portfolio", "county_status"}.intersection(rows[0])


def test_hhs_ambiguity_and_out_of_scope_nulls_are_explicit() -> None:
    rows, _, _, _ = _build()
    by_fips = {row["canonical_fips"]: row for row in rows}
    assert by_fips["88001"]["hhs_dme_ambiguous_11"] is True
    assert by_fips["88001"]["hhs_power_dependent_devices_dme"] == 11
    excluded = by_fips["88007"]
    assert excluded["hhs_source_row_number"] is None
    assert excluded["hhs_medicare_benes"] is None
    assert excluded["hhs_dme_ambiguous_11"] is False


def test_fema_hazards_preserve_null_and_not_applicable() -> None:
    rows, _, _, _ = _build()
    county = next(row for row in rows if row["canonical_fips"] == "88003")
    assert county["fema_tsun_risk_score"] is None
    assert county["fema_tsun_risk_rating"] == "Not Applicable"
    assert county["fema_avln_risk_score"] == pytest.approx(4.01)


def test_hpsa_duplicate_and_two_status_families_are_separate() -> None:
    rows, _, _, _ = _build()
    county = next(row for row in rows if row["canonical_fips"] == "88001")
    assert county["hpsa_mapped_source_row_count"] == 3
    assert county["hpsa_exact_duplicate_count"] == 1
    assert county["hpsa_distinct_id_count"] == 2
    assert county["hpsa_designated_eligible_row_count"] == 1
    assert county["hpsa_designated_max_raw_score"] == 12
    assert county["hpsa_designated_with_proposed_eligible_row_count"] == 2
    assert county["hpsa_designated_with_proposed_max_raw_score"] == 17


def test_site_maps_retain_all_categories_and_lineage() -> None:
    rows, _, _, _ = _build()
    county = next(row for row in rows if row["canonical_fips"] == "88001")
    assert county["site_mapped_source_row_count"] == 2
    assert county["site_status_counts_json"] == '{"Active":2}'
    assert county["site_location_type_counts_json"] == '{"Mobile":1,"Permanent":1}'
    assert county["site_lineage_sha256"] == sha256_json([1, 2])


def test_output_is_deterministic_under_shuffled_input_order() -> None:
    rows, contract, staging, geography = _build()
    shuffled_staging = {key: list(reversed(value)) for key, value in staging.items()}
    shuffled_geography = {
        "county_reference": list(reversed(geography["county_reference"])),
        "source_maps": {key: list(reversed(value)) for key, value in geography["source_maps"].items()},
    }
    assert build_county_evidence(shuffled_staging, shuffled_geography, contract) == rows


def test_missing_duplicate_and_invalid_hhs_fail_closed() -> None:
    _, contract, staging, geography = _build()
    missing = deepcopy(geography)
    missing["source_maps"]["stg_hhs_empower_county"][0]["canonical_fips"] = None
    missing["source_maps"]["stg_hhs_empower_county"][0]["mapping_status"] = "MISSING_SOURCE_FIPS"
    with pytest.raises(CountyEvidenceError, match="mapped count differs"):
        build_county_evidence(staging, missing, contract)
    invalid = deepcopy(staging)
    invalid["stg_hhs_empower_county"][0]["Power_Dependent_Devices_DME"] = 101
    with pytest.raises(CountyEvidenceError, match="HHS source values are invalid"):
        build_county_evidence(invalid, geography, contract)


def test_fema_coverage_and_score_fail_closed() -> None:
    _, contract, staging, geography = _build()
    duplicate = deepcopy(geography)
    duplicate["source_maps"]["stg_fema_nri_counties"][1]["canonical_fips"] = "88007"
    with pytest.raises(CountyEvidenceError, match="duplicate county coverage"):
        build_county_evidence(staging, duplicate, contract)
    invalid = deepcopy(staging)
    invalid["stg_fema_nri_counties"][0]["RISK_SCORE"] = 101.0
    with pytest.raises(CountyEvidenceError, match="FEMA composite score is invalid"):
        build_county_evidence(invalid, geography, contract)


def test_lineage_field_and_context_only_mutations_fail_closed() -> None:
    _, contract, staging, geography = _build()
    changed = deepcopy(staging)
    changed["stg_hrsa_health_center_sites"][1]["source_row_number"] = 1
    with pytest.raises(CountyEvidenceError, match="staging lineage is duplicated"):
        build_county_evidence(changed, geography, contract)
    extra = deepcopy(staging)
    extra["stg_hhs_empower_history_county"] = []
    with pytest.raises(CountyEvidenceError, match="staging table set differs"):
        build_county_evidence(extra, geography, contract)


def test_unmapped_hpsa_and_site_rows_do_not_enter_summaries() -> None:
    rows, _, _, _ = _build()
    assert sum(row["hpsa_mapped_source_row_count"] for row in rows) == 5
    assert sum(row["site_mapped_source_row_count"] for row in rows) == 3
    assert all("INV-OUT" not in row["site_status_counts_json"] for row in rows)
