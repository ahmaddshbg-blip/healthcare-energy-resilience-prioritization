from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import load_json
from healthcare_resilience.geography import (
    MAP_COLUMNS,
    REFERENCE_COLUMNS,
    GeographyError,
    build_geography_outputs,
    geography_content_hashes,
    validate_geography_contract,
)
from healthcare_resilience.geography_checkpoint import (
    GeographyCheckpointError,
    verify_geography_checkpoint_artifacts,
    write_geography_checkpoint,
)
from healthcare_resilience.staging_build import StagingBuildError

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
SYNTHETIC_COMMIT = "a" * 40
SYNTHETIC_LOCK = "b" * 64
SYNTHETIC_INPUT_MANIFEST = "c" * 64
SYNTHETIC_ENVIRONMENT = {
    "python_version": "3.13.0",
    "python_implementation": "CPython",
    "platform_system": "SyntheticOS",
    "platform_machine": "synthetic64",
    "dependencies": {"duckdb": "1.5.5"},
}


def _synthetic_contract() -> dict:
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


def _rows() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_geography_rows.json")


def _outputs() -> tuple[dict, dict, dict]:
    contract = _synthetic_contract()
    rows = _rows()
    return build_geography_outputs(rows, contract), rows, contract


def _patch_release_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "healthcare_resilience.geography_checkpoint.capture_repository_identity",
        lambda _: SYNTHETIC_COMMIT,
    )
    monkeypatch.setattr(
        "healthcare_resilience.geography_checkpoint.capture_environment_identity",
        lambda _: (SYNTHETIC_LOCK, SYNTHETIC_ENVIRONMENT),
    )


def _write_checkpoint(
    output_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe=None,
) -> tuple[Path, dict, dict]:
    outputs, _, contract = _outputs()
    _patch_release_identity(monkeypatch)
    if probe is None:
        probe = lambda: (
            contract["input_staging_build_identity"],
            SYNTHETIC_INPUT_MANIFEST,
        )
    output, manifest = write_geography_checkpoint(
        output_root,
        outputs,
        contract,
        "d" * 64,
        load_json(CONFIG_DIR / "geography_checkpoint.schema.json"),
        ROOT,
        probe,
    )
    return output, manifest, contract


def test_geo_p01_fips_text_preserves_leading_zeroes() -> None:
    outputs, _, _ = _outputs()
    leading_zero = next(row for row in outputs["county_reference"] if row["canonical_fips"] == "02158")
    assert leading_zero["canonical_fips"].startswith("0")
    assert isinstance(leading_zero["canonical_fips"], str)


def test_geo_p02_census_components_produce_unique_county_keys() -> None:
    outputs, _, _ = _outputs()
    keys = [row["canonical_fips"] for row in outputs["county_reference"]]
    assert len(keys) == len(set(keys)) == 15


def test_geo_p03_state_summaries_are_accounted_for_not_referenced() -> None:
    outputs, _, _ = _outputs()
    census_map = outputs["source_maps"]["stg_census_county_population_2025"]
    summaries = [row for row in census_map if row["mapping_status"] == "STATE_SUMMARY_NOT_COUNTY"]
    assert len(summaries) == 2
    assert all(row["canonical_fips"] is None for row in summaries)


def test_geo_p04_direct_fips_maps_to_one_reference() -> None:
    outputs, _, _ = _outputs()
    mapped = outputs["source_maps"]["stg_hhs_empower_county"][0]
    assert (mapped["mapping_status"], mapped["canonical_fips"]) == (
        "DIRECT_REFERENCE", "88001"
    )


def test_geo_p05_two_hhs_replacements_are_one_to_one_with_rule_ids() -> None:
    outputs, _, _ = _outputs()
    replacements = [
        row for row in outputs["source_maps"]["stg_hhs_empower_county"]
        if row["mapping_status"] == "EXACT_REPLACEMENT"
    ]
    assert [(row["source_fips_primary"], row["canonical_fips"], row["mapping_rule_id"]) for row in replacements] == [
        ("02270", "02158", "HHS_WADE_HAMPTON_TO_KUSILVAK"),
        ("46113", "46102", "HHS_SHANNON_TO_OGLALA_LAKOTA"),
    ]


def test_geo_p06_all_declared_units_are_out_of_scope() -> None:
    outputs, _, contract = _outputs()
    observed = {
        row["canonical_fips"] for row in outputs["county_reference"]
        if row["decision_scope_status"] == "OUT_OF_SCOPE"
    }
    assert observed == set(contract["reference"]["out_of_scope_fips"])
    assert len(observed) == 11


def test_geo_p07_hhs_legacy_rows_remain_unresolved() -> None:
    outputs, _, _ = _outputs()
    unresolved = [
        row for row in outputs["source_maps"]["stg_hhs_empower_county"]
        if row["mapping_status"] == "UNRESOLVED_LEGACY_GEOGRAPHY"
    ]
    assert len(unresolved) == 9
    assert all(row["canonical_fips"] is None for row in unresolved)


def test_geo_p08_territorial_row_is_outside_not_out_of_scope() -> None:
    outputs, _, _ = _outputs()
    outside = outputs["source_maps"]["stg_hhs_empower_county"][13]
    assert outside["mapping_status"] == "OUTSIDE_REFERENCE_UNIVERSE"
    assert outside["canonical_fips"] is None


def test_geo_p09_agreeing_hpsa_fields_produce_one_mapping() -> None:
    outputs, _, _ = _outputs()
    row = outputs["source_maps"]["stg_hrsa_primary_care_hpsa"][0]
    assert row["canonical_fips"] == "88001"
    assert row["mapping_rule_id"] == "HPSA_PRIMARY_FIPS"


def test_geo_p10_valid_hpsa_fallback_is_recorded() -> None:
    outputs, _, _ = _outputs()
    row = outputs["source_maps"]["stg_hrsa_primary_care_hpsa"][1]
    assert row["canonical_fips"] == "88003"
    assert row["mapping_rule_id"] == "HPSA_FALLBACK_FIPS"


def test_geo_p11_missing_site_fips_remains_explicit() -> None:
    outputs, _, _ = _outputs()
    row = outputs["source_maps"]["stg_hrsa_health_center_sites"][2]
    assert row["mapping_status"] == "MISSING_SOURCE_FIPS"
    assert row["canonical_fips"] is None


def test_geo_p12_every_source_map_preserves_count_and_lineage() -> None:
    outputs, rows, _ = _outputs()
    for table_id, source_rows in rows.items():
        mapped = outputs["source_maps"][table_id]
        assert len(mapped) == len(source_rows)
        assert [row["source_row_number"] for row in mapped] == list(range(1, len(source_rows) + 1))


def test_geo_p13_input_shuffle_does_not_change_outputs_or_hashes() -> None:
    outputs, rows, contract = _outputs()
    shuffled = {table_id: list(reversed(table_rows)) for table_id, table_rows in rows.items()}
    repeated = build_geography_outputs(shuffled, contract)
    assert repeated == outputs
    assert geography_content_hashes(repeated) == geography_content_hashes(outputs)


def test_geo_p14_artifacts_have_only_reference_or_map_columns() -> None:
    outputs, _, _ = _outputs()
    assert all(tuple(row) == REFERENCE_COLUMNS for row in outputs["county_reference"])
    assert all(
        tuple(row) == MAP_COLUMNS
        for mapped in outputs["source_maps"].values()
        for row in mapped
    )


def test_geo_p15_independent_verification_reproduces_manifest_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, manifest, contract = _write_checkpoint(tmp_path / "checkpoints", monkeypatch)
    second_output, second_manifest, _ = _write_checkpoint(
        tmp_path / "second-checkpoints", monkeypatch
    )
    verify_geography_checkpoint_artifacts(
        output,
        manifest,
        load_json(CONFIG_DIR / "geography_checkpoint.schema.json"),
        contract,
        "d" * 64,
    )
    verify_geography_checkpoint_artifacts(
        second_output,
        second_manifest,
        load_json(CONFIG_DIR / "geography_checkpoint.schema.json"),
        contract,
        "d" * 64,
    )
    assert manifest["table_count"] == 7
    assert manifest["total_row_count"] == 85
    assert second_manifest == manifest


def test_geo_n01_malformed_or_nontext_fips_never_maps() -> None:
    invalid_text = ["1", "1234", "123456", "+1001", "10.01", " 88001", "88001 ", "A1001"]
    for value in invalid_text:
        rows = _rows()
        rows["stg_hrsa_health_center_sites"][3]["State and County Federal Information Processing Standard Code"] = value
        mapped = build_geography_outputs(rows, _synthetic_contract())["source_maps"]["stg_hrsa_health_center_sites"][3]
        assert mapped["mapping_status"] == "INVALID_SOURCE_FIPS"
        assert mapped["canonical_fips"] is None
    rows = _rows()
    rows["stg_hrsa_health_center_sites"][3]["State and County Federal Information Processing Standard Code"] = 1001
    with pytest.raises(GeographyError, match="must remain text"):
        build_geography_outputs(rows, _synthetic_contract())


def test_geo_n02_no_trimming_padding_coercion_or_name_repair() -> None:
    outputs, _, _ = _outputs()
    invalid = outputs["source_maps"]["stg_hrsa_health_center_sites"][3]
    missing = outputs["source_maps"]["stg_hrsa_health_center_sites"][2]
    assert invalid["source_fips_primary"] == " 88003 "
    assert invalid["mapping_status"] == "INVALID_SOURCE_FIPS"
    assert missing["mapping_status"] == "MISSING_SOURCE_FIPS"
    assert missing["canonical_fips"] is None


def test_geo_n03_duplicate_or_missing_census_key_is_rejected() -> None:
    duplicate = _rows()
    duplicate["stg_census_county_population_2025"][1]["COUNTY"] = "001"
    with pytest.raises(GeographyError, match="duplicate Census county key"):
        build_geography_outputs(duplicate, _synthetic_contract())
    missing = _rows()
    missing["stg_census_county_population_2025"][14]["SUMLEV"] = "040"
    with pytest.raises(GeographyError, match="reference count differs"):
        build_geography_outputs(missing, _synthetic_contract())


def test_geo_n04_accepted_reference_or_summary_count_drift_is_rejected() -> None:
    schema = load_json(CONFIG_DIR / "geography.schema.json")
    for field, value in (("expected_county_count", 3143), ("expected_state_summary_count", 50)):
        contract = load_json(CONFIG_DIR / "geography.json")
        contract["reference"][field] = value
        if field == "expected_county_count":
            contract["reference"]["eligible_count"] = 3132
        with pytest.raises(GeographyError, match="accepted reference universe"):
            validate_geography_contract(contract, schema)


def test_geo_n05_undeclared_replacement_is_rejected() -> None:
    contract = load_json(CONFIG_DIR / "geography.json")
    contract["exact_replacements"][1] = {
        **contract["exact_replacements"][1],
        "source_fips": "99998",
        "canonical_fips": "88001",
    }
    with pytest.raises(GeographyError, match="accepted replacements"):
        validate_geography_contract(contract, load_json(CONFIG_DIR / "geography.schema.json"))


def test_geo_n06_hhs_replacement_code_in_fema_or_hrsa_is_rejected() -> None:
    cases = [
        ("stg_fema_nri_counties", "STCOFIPS"),
        ("stg_hrsa_primary_care_hpsa", "State and County Federal Information Processing Standard Code"),
        ("stg_hrsa_health_center_sites", "State and County Federal Information Processing Standard Code"),
    ]
    for table_id, field in cases:
        rows = _rows()
        rows[table_id][0][field] = "02270"
        with pytest.raises(GeographyError, match="replacement source code is prohibited"):
            build_geography_outputs(rows, _synthetic_contract())


def test_geo_n07_alaska_legacy_allocation_is_rejected() -> None:
    contract = _synthetic_contract()
    contract["exact_replacements"][0]["source_fips"] = "02261"
    with pytest.raises(GeographyError, match="legacy FIPS cannot also be a replacement"):
        validate_geography_contract(
            contract, load_json(CONFIG_DIR / "geography.schema.json"),
            enforce_accepted_contract=False,
        )


def test_geo_n08_connecticut_legacy_allocation_is_rejected() -> None:
    contract = _synthetic_contract()
    contract["exact_replacements"][0]["source_fips"] = "09001"
    with pytest.raises(GeographyError, match="legacy FIPS cannot also be a replacement"):
        validate_geography_contract(
            contract, load_json(CONFIG_DIR / "geography.schema.json"),
            enforce_accepted_contract=False,
        )


def test_geo_n09_out_of_scope_set_drift_is_rejected() -> None:
    contract = load_json(CONFIG_DIR / "geography.json")
    contract["reference"]["out_of_scope_fips"][-1] = "09191"
    with pytest.raises(GeographyError):
        validate_geography_contract(contract, load_json(CONFIG_DIR / "geography.schema.json"))


def test_geo_n10_fema_duplicate_missing_or_replacement_is_rejected() -> None:
    duplicate = _rows()
    duplicate["stg_fema_nri_counties"][1]["STCOFIPS"] = "88001"
    with pytest.raises(GeographyError, match="coverage is not exactly one-to-one"):
        build_geography_outputs(duplicate, _synthetic_contract())
    missing = _rows()
    missing["stg_fema_nri_counties"].pop(14)
    for number, row in enumerate(missing["stg_fema_nri_counties"], start=1):
        row["source_row_number"] = number
    with pytest.raises(GeographyError, match="source mapping total differs"):
        build_geography_outputs(missing, _synthetic_contract())
    replacement = _rows()
    replacement["stg_fema_nri_counties"][0]["STCOFIPS"] = "46113"
    with pytest.raises(GeographyError, match="replacement source code is prohibited"):
        build_geography_outputs(replacement, _synthetic_contract())


def test_geo_n11_conflicting_valid_hpsa_fields_are_rejected() -> None:
    rows = _rows()
    rows["stg_hrsa_primary_care_hpsa"][0]["Common State County FIPS Code"] = "88003"
    with pytest.raises(GeographyError, match="FIPS fields conflict"):
        build_geography_outputs(rows, _synthetic_contract())


def test_geo_n12_missing_hrsa_fips_is_not_inferred_from_context() -> None:
    rows = _rows()
    site = rows["stg_hrsa_health_center_sites"][2]
    site["Complete County Name"] = "Alpha One"
    site["Site Postal Code"] = "88001"
    site["Site Address"] = "88001 Exact Match Avenue"
    mapped = build_geography_outputs(rows, _synthetic_contract())["source_maps"]["stg_hrsa_health_center_sites"][2]
    assert mapped["mapping_status"] == "MISSING_SOURCE_FIPS"
    assert mapped["canonical_fips"] is None


def test_geo_n13_row_loss_duplication_or_lineage_change_is_rejected() -> None:
    lost = _rows()
    lost["stg_hrsa_health_center_sites"].pop()
    with pytest.raises(GeographyError, match="mapping total differs"):
        build_geography_outputs(lost, _synthetic_contract())
    duplicated = _rows()
    duplicated["stg_hrsa_health_center_sites"][1]["source_row_number"] = 1
    with pytest.raises(GeographyError, match="lineage is duplicated"):
        build_geography_outputs(duplicated, _synthetic_contract())
    changed = _rows()
    changed["stg_hrsa_health_center_sites"][3]["source_row_number"] = 5
    with pytest.raises(GeographyError, match="lineage is incomplete or changed"):
        build_geography_outputs(changed, _synthetic_contract())


def test_geo_n14_declared_mapping_count_drift_is_rejected() -> None:
    rows = _rows()
    rows["stg_hhs_empower_county"][13]["FIPS_Code"] = "bad"
    with pytest.raises(GeographyError, match="mapping count differs"):
        build_geography_outputs(rows, _synthetic_contract())


def test_geo_n15_overwrite_dirty_tree_input_mutation_and_tampering_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "checkpoints"
    output, manifest, contract = _write_checkpoint(output_root, monkeypatch)
    with pytest.raises(GeographyCheckpointError, match="already exists"):
        _write_checkpoint(output_root, monkeypatch)

    monkeypatch.setattr(
        "healthcare_resilience.geography_checkpoint.capture_repository_identity",
        lambda _: (_ for _ in ()).throw(StagingBuildError("repository working tree is not clean")),
    )
    with pytest.raises(GeographyCheckpointError, match="not clean"):
        write_geography_checkpoint(
            tmp_path / "dirty", _outputs()[0], contract, "d" * 64,
            load_json(CONFIG_DIR / "geography_checkpoint.schema.json"), ROOT,
            lambda: (contract["input_staging_build_identity"], SYNTHETIC_INPUT_MANIFEST),
        )

    _patch_release_identity(monkeypatch)
    identities = iter([
        (contract["input_staging_build_identity"], SYNTHETIC_INPUT_MANIFEST),
        (contract["input_staging_build_identity"], "e" * 64),
    ])
    with pytest.raises(GeographyCheckpointError, match="changed during"):
        write_geography_checkpoint(
            tmp_path / "mutated", _outputs()[0], contract, "d" * 64,
            load_json(CONFIG_DIR / "geography_checkpoint.schema.json"), ROOT,
            lambda: next(identities),
        )
    assert not list((tmp_path / "mutated").iterdir())

    artifact = output / manifest["tables"][0]["relative_path"]
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(GeographyCheckpointError, match="byte count differs"):
        verify_geography_checkpoint_artifacts(
            output, manifest,
            load_json(CONFIG_DIR / "geography_checkpoint.schema.json"),
            contract, "d" * 64,
        )
