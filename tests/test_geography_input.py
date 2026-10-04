from __future__ import annotations

import json
from inspect import signature
from pathlib import Path

import pytest

from healthcare_resilience.contracts import load_json
from healthcare_resilience.geography import build_geography_outputs, validate_geography_contract
from healthcare_resilience.geography_input import (
    GeographyInputError,
    _build_geography_from_verified_staging,
    _staging_checkpoint_summary,
    load_verified_geography_rows,
    run_frozen_geography_reconciliation,
    verify_staging_geography_input,
)
from healthcare_resilience.hashing import sha256_file, sha256_json
from healthcare_resilience.staging_checkpoint import write_staging_checkpoint
from tests.geography_support import synthetic_geography_contract, synthetic_geography_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
SYNTHETIC_COMMIT = "a" * 40
SYNTHETIC_LOCK = "b" * 64
SOURCE_CONTRACT_SHA256 = "c" * 64
SOURCE_SNAPSHOT_ID = "d" * 64
SYNTHETIC_ENVIRONMENT = {
    "python_version": "3.13.0",
    "python_implementation": "CPython",
    "platform_system": "SyntheticOS",
    "platform_machine": "synthetic64",
    "dependencies": {
        "duckdb": "1.5.5",
        "jsonschema": "4.26.0",
        "numpy": "2.5.3",
        "openpyxl": "3.1.5",
        "pandas": "3.0.6",
    },
}


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _source_and_staging_contracts(
    rows_by_table: dict,
    geography_contract: dict,
    config_directory: Path,
) -> tuple[dict, dict, str, str]:
    source_tables = []
    staging_tables = []
    for rule in geography_contract["source_rules"]:
        table_id = rule["staging_table_id"]
        source_id = table_id.removeprefix("stg_")
        rows = rows_by_table[table_id]
        source_fields = [name for name in rows[0] if name != "source_row_number"]
        required_columns = []
        for field in source_fields:
            values = [row[field] for row in rows]
            required_columns.append(
                {
                    "name": field,
                    "parser_type": (
                        "INTEGER"
                        if all(value is None or type(value) is int for value in values)
                        else "STRING"
                    ),
                    "null_allowed": any(value is None for value in values),
                }
            )
        source_tables.append(
            {"id": source_id, "required_columns": required_columns}
        )
        staging_tables.append(
            {
                "id": table_id,
                "source_table_id": source_id,
                "expected_staging_row_count": len(rows),
            }
        )
    source_table_contract = {
        "expected_table_count": len(source_tables),
        "table_contracts": source_tables,
    }
    source_table_path = config_directory / "source_tables.json"
    _write_json(source_table_path, source_table_contract)
    source_table_sha256 = sha256_file(source_table_path)
    staging_contract = {
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "source_table_contract_sha256": source_table_sha256,
        "staging_tables": staging_tables,
    }
    staging_path = config_directory / "staging_tables.json"
    _write_json(staging_path, staging_contract)
    return (
        source_table_contract,
        staging_contract,
        source_table_sha256,
        sha256_file(staging_path),
    )


@pytest.fixture
def invented_staging_build(tmp_path: Path) -> dict:
    rows = synthetic_geography_rows()
    geography_contract = synthetic_geography_contract()
    config_directory = tmp_path / "invented_contracts"
    config_directory.mkdir()
    (
        source_table_contract,
        staging_contract,
        source_table_sha256,
        staging_sha256,
    ) = _source_and_staging_contracts(rows, geography_contract, config_directory)
    geography_contract["source_snapshot_id"] = SOURCE_SNAPSHOT_ID
    geography_contract["staging_table_contract_sha256"] = staging_sha256

    identity_inputs = {
        "execution_mode": "FROZEN_SOURCE_PRESERVING_STAGING",
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "source_contract_sha256": SOURCE_CONTRACT_SHA256,
        "source_table_contract_sha256": source_table_sha256,
        "staging_table_contract_sha256": staging_sha256,
        "code_commit": SYNTHETIC_COMMIT,
        "repository_clean": True,
        "requirements_lock_sha256": SYNTHETIC_LOCK,
        "environment": SYNTHETIC_ENVIRONMENT,
    }
    build_identity = sha256_json(identity_inputs)
    geography_contract["input_staging_build_identity"] = build_identity
    build_directory = tmp_path / "private_staging" / build_identity
    build_directory.mkdir(parents=True)
    checkpoint_directory = build_directory / "checkpoint"
    checkpoint_manifest = write_staging_checkpoint(
        checkpoint_directory,
        rows,
        staging_contract,
        source_table_contract,
        SOURCE_CONTRACT_SHA256,
        staging_sha256,
        load_json(CONFIG_DIR / "staging_checkpoint.schema.json"),
    )
    report_sha256 = "e" * 64
    build_manifest = {
        "schema_version": "1.0.0",
        "manifest_type": "FROZEN_SOURCE_PRESERVING_STAGING_BUILD",
        "status": "COMPLETE",
        "build_identity_algorithm": "SHA256_CANONICAL_BUILD_INPUTS_V1",
        "build_identity": build_identity,
        "build_identity_inputs": identity_inputs,
        "snapshot_verification": {
            "pre_build_report_sha256": report_sha256,
            "post_build_report_sha256": report_sha256,
            "reports_identical": True,
            "expected_file_count": 6,
            "verified_file_count": 6,
        },
        "source_table_profile": {
            "canonical_sha256": "f" * 64,
            "table_count": 6,
        },
        "checkpoint": _staging_checkpoint_summary(
            checkpoint_directory, checkpoint_manifest
        ),
        "independent_verification": True,
    }
    build_manifest_path = build_directory / "staging_build_manifest.json"
    _write_json(build_manifest_path, build_manifest)
    geography_contract["input_staging_build_manifest_file_sha256"] = sha256_file(
        build_manifest_path
    )
    geography_contract[
        "input_staging_checkpoint_manifest_canonical_sha256"
    ] = sha256_json(checkpoint_manifest)
    geography_contract["input_staging_checkpoint_manifest_file_sha256"] = sha256_file(
        checkpoint_directory / "staging_checkpoint_manifest.json"
    )
    validate_geography_contract(
        geography_contract,
        load_json(CONFIG_DIR / "geography.schema.json"),
        enforce_accepted_contract=False,
    )
    return {
        "build_directory": build_directory,
        "geography_contract": geography_contract,
        "staging_contract": staging_contract,
        "source_table_contract": source_table_contract,
        "source_table_sha256": source_table_sha256,
        "staging_sha256": staging_sha256,
        "staging_build_schema": load_json(CONFIG_DIR / "staging_build.schema.json"),
        "staging_checkpoint_schema": load_json(
            CONFIG_DIR / "staging_checkpoint.schema.json"
        ),
        "geography_checkpoint_schema": load_json(
            CONFIG_DIR / "geography_checkpoint.schema.json"
        ),
    }


def _verification_arguments(case: dict) -> tuple:
    return (
        case["build_directory"],
        ROOT,
        case["geography_contract"],
        case["staging_contract"],
        case["source_table_contract"],
        case["staging_build_schema"],
        case["staging_checkpoint_schema"],
        SOURCE_CONTRACT_SHA256,
        case["source_table_sha256"],
        case["staging_sha256"],
    )


def _patch_release_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "healthcare_resilience.geography_input.capture_repository_identity",
        lambda _: SYNTHETIC_COMMIT,
    )
    monkeypatch.setattr(
        "healthcare_resilience.geography_checkpoint.capture_repository_identity",
        lambda _: SYNTHETIC_COMMIT,
    )
    monkeypatch.setattr(
        "healthcare_resilience.geography_checkpoint.capture_environment_identity",
        lambda _: (SYNTHETIC_LOCK, SYNTHETIC_ENVIRONMENT),
    )


def _orchestration_arguments(case: dict, output_root: Path) -> tuple:
    return (
        case["build_directory"],
        output_root,
        ROOT,
        case["geography_contract"],
        case["staging_contract"],
        case["source_table_contract"],
        case["staging_build_schema"],
        case["staging_checkpoint_schema"],
        case["geography_checkpoint_schema"],
        SOURCE_CONTRACT_SHA256,
        case["source_table_sha256"],
        case["staging_sha256"],
        "1" * 64,
    )


def test_read_only_boundary_verifies_and_exposes_only_geography_fields(
    invented_staging_build: dict,
) -> None:
    case = invented_staging_build
    verified = verify_staging_geography_input(*_verification_arguments(case))
    rows, loaded_identity = load_verified_geography_rows(
        *_verification_arguments(case)
    )
    assert loaded_identity == verified
    assert set(rows) == {
        rule["staging_table_id"]
        for rule in case["geography_contract"]["source_rules"]
    }
    site_rows = rows["stg_hrsa_health_center_sites"]
    assert list(site_rows[0]) == [
        "source_row_number",
        "State and County Federal Information Processing Standard Code",
    ]
    assert "Site Address" not in site_rows[0]
    outputs = build_geography_outputs(rows, case["geography_contract"])
    assert len(outputs["county_reference"]) == 15


def test_production_entrypoint_has_no_contract_or_probe_override() -> None:
    assert list(signature(run_frozen_geography_reconciliation).parameters) == [
        "data_root",
        "repository_root",
    ]


def test_public_staging_and_geography_contracts_cover_same_table_set() -> None:
    staging = load_json(CONFIG_DIR / "staging_tables.json")
    geography = load_json(CONFIG_DIR / "geography.json")
    staging_ids = [item["id"] for item in staging["staging_tables"]]
    geography_ids = [item["staging_table_id"] for item in geography["source_rules"]]
    assert set(staging_ids) == set(geography_ids)
    assert staging_ids != geography_ids


def test_read_only_boundary_rejects_unexpected_build_membership(
    invented_staging_build: dict,
) -> None:
    case = invented_staging_build
    (case["build_directory"] / "unexpected.txt").write_text(
        "invented", encoding="utf-8"
    )
    with pytest.raises(GeographyInputError, match="missing or unexpected"):
        verify_staging_geography_input(*_verification_arguments(case))


def test_read_only_boundary_rejects_schema_valid_build_manifest_tampering(
    invented_staging_build: dict,
) -> None:
    case = invented_staging_build
    path = case["build_directory"] / "staging_build_manifest.json"
    manifest = load_json(path)
    manifest["source_table_profile"]["canonical_sha256"] = "0" * 64
    _write_json(path, manifest)
    with pytest.raises(GeographyInputError, match="manifest evidence differs"):
        verify_staging_geography_input(*_verification_arguments(case))


def test_read_only_boundary_rejects_parquet_tampering(
    invented_staging_build: dict,
) -> None:
    case = invented_staging_build
    artifact = next(
        (case["build_directory"] / "checkpoint" / "tables").glob("*.parquet")
    )
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="byte count differs"):
        verify_staging_geography_input(*_verification_arguments(case))


def test_loader_reverifies_after_read_and_detects_mutation(
    invented_staging_build: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = invented_staging_build
    from healthcare_resilience import geography_input

    original = geography_input.verify_staging_geography_input
    calls = 0

    def mutate_before_second_verification(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            artifact = next(
                (case["build_directory"] / "checkpoint" / "tables").glob(
                    "*.parquet"
                )
            )
            artifact.write_bytes(artifact.read_bytes() + b"changed")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        geography_input,
        "verify_staging_geography_input",
        mutate_before_second_verification,
    )
    with pytest.raises(ValueError, match="byte count differs"):
        load_verified_geography_rows(*_verification_arguments(case))
    assert calls == 2


def test_trusted_orchestrator_writes_verified_geography_checkpoint(
    invented_staging_build: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = invented_staging_build
    _patch_release_context(monkeypatch)
    output, manifest = _build_geography_from_verified_staging(
        *_orchestration_arguments(case, tmp_path / "geography_output")
    )
    assert output.name == manifest["checkpoint_identity"]
    assert manifest["checkpoint_identity_inputs"]["input_staging_build_identity"] == case["geography_contract"]["input_staging_build_identity"]


def test_trusted_orchestrator_rejects_input_mutation_during_output(
    invented_staging_build: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = invented_staging_build
    _patch_release_context(monkeypatch)
    from healthcare_resilience import geography_checkpoint

    original = geography_checkpoint.verify_geography_checkpoint_artifacts
    mutated = False

    def verify_then_mutate(*args, **kwargs):
        nonlocal mutated
        result = original(*args, **kwargs)
        if not mutated:
            artifact = next(
                (case["build_directory"] / "checkpoint" / "tables").glob(
                    "*.parquet"
                )
            )
            artifact.write_bytes(artifact.read_bytes() + b"changed")
            mutated = True
        return result

    monkeypatch.setattr(
        geography_checkpoint,
        "verify_geography_checkpoint_artifacts",
        verify_then_mutate,
    )
    output_root = tmp_path / "geography_output"
    with pytest.raises(ValueError, match="byte count differs"):
        _build_geography_from_verified_staging(
            *_orchestration_arguments(case, output_root)
        )
    assert not list(output_root.glob("*"))
