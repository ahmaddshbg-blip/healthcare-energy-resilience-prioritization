from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import duckdb
import pytest
from openpyxl import Workbook

from healthcare_resilience.contracts import load_json
from healthcare_resilience.hashing import sha256_file
from healthcare_resilience.source_adapters import extract_staging_tables_from_files
from healthcare_resilience.staging_checkpoint import (
    StagingCheckpointError,
    validate_staging_checkpoint_manifest,
    verify_staging_checkpoint_artifacts,
    write_staging_checkpoint,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
SOURCE_CONTRACT_SHA256 = "2" * 64


@pytest.fixture
def checkpoint_inputs(tmp_path: Path) -> tuple[dict, dict, dict, dict]:
    source_contract = load_json(
        FIXTURE_DIR / "synthetic_source_table_contract.json"
    )
    staging_contract = load_json(FIXTURE_DIR / "synthetic_staging_contract.json")
    manifest_schema = load_json(CONFIG_DIR / "staging_checkpoint.schema.json")
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    (raw_root / "synthetic_measurements.csv").write_bytes(
        b"unit_id,amount\n01001,11\n02020,\n03030,4.50\n"
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Regions"
    sheet.append(["region_id", "label"])
    sheet.append(["R-01", "Not Applicable"])
    sheet.append(["R-01", "Not Applicable"])
    workbook.save(raw_root / "synthetic_regions.xlsx")
    workbook.close()
    rows = extract_staging_tables_from_files(
        raw_root, staging_contract, source_contract
    )
    return rows, staging_contract, source_contract, manifest_schema


def _write(
    output: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> dict:
    rows, staging_contract, source_contract, manifest_schema = checkpoint_inputs
    return write_staging_checkpoint(
        output,
        rows,
        staging_contract,
        source_contract,
        SOURCE_CONTRACT_SHA256,
        sha256_file(FIXTURE_DIR / "synthetic_staging_contract.json"),
        manifest_schema,
    )


def test_checkpoint_manifest_and_artifacts_are_valid(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    output = tmp_path / "checkpoint"
    manifest = _write(output, checkpoint_inputs)
    rows, staging_contract, source_contract, manifest_schema = checkpoint_inputs
    validate_staging_checkpoint_manifest(
        manifest,
        manifest_schema,
        staging_contract,
        source_contract,
        SOURCE_CONTRACT_SHA256,
        sha256_file(FIXTURE_DIR / "synthetic_staging_contract.json"),
    )
    verify_staging_checkpoint_artifacts(output, manifest)
    assert manifest["table_count"] == 2
    assert manifest["total_row_count"] == 5
    assert str(tmp_path) not in json.dumps(manifest)
    assert load_json(output / "staging_checkpoint_manifest.json") == manifest

    measurement_path = output / "tables" / "stg_synthetic_measurements.parquet"
    values = duckdb.read_parquet(str(measurement_path)).order(
        "source_row_number"
    ).fetchall()
    assert values[0][1:] == ("01001", pytest.approx(11))
    assert values[1][1:] == ("02020", None)


def test_checkpoint_manifest_is_deterministic_in_same_environment(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    first = _write(tmp_path / "first", checkpoint_inputs)
    second = _write(tmp_path / "second", checkpoint_inputs)
    assert first == second


def test_checkpoint_preserves_nullable_integer_and_datetime_types(
    tmp_path: Path,
) -> None:
    source_contract = {
        "table_contracts": [
            {
                "id": "synthetic_typed",
                "required_columns": [
                    {
                        "name": "record_id",
                        "parser_type": "STRING",
                        "null_allowed": False,
                    },
                    {
                        "name": "count",
                        "parser_type": "INTEGER",
                        "null_allowed": True,
                    },
                    {
                        "name": "created_at",
                        "parser_type": "DATETIME",
                        "null_allowed": True,
                    },
                ],
            }
        ]
    }
    staging_contract = {
        "source_snapshot_id": "1" * 64,
        "source_table_contract_sha256": "3" * 64,
        "staging_tables": [
            {
                "id": "stg_synthetic_typed",
                "source_table_id": "synthetic_typed",
                "expected_staging_row_count": 2,
            }
        ],
    }
    rows = {
        "stg_synthetic_typed": [
            {
                "source_row_number": 1,
                "record_id": "001",
                "count": 11,
                "created_at": datetime(2026, 10, 2),
            },
            {
                "source_row_number": 2,
                "record_id": "002",
                "count": None,
                "created_at": None,
            },
        ]
    }
    output = tmp_path / "typed"
    manifest = write_staging_checkpoint(
        output,
        rows,
        staging_contract,
        source_contract,
        SOURCE_CONTRACT_SHA256,
        "4" * 64,
        load_json(CONFIG_DIR / "staging_checkpoint.schema.json"),
    )
    values = duckdb.read_parquet(
        str(output / "tables" / "stg_synthetic_typed.parquet")
    ).order("source_row_number").fetchall()
    assert values == [
        (1, "001", 11, datetime(2026, 10, 2)),
        (2, "002", None, None),
    ]
    assert manifest["tables"][0]["columns"][2]["output_type"] == "INTEGER"


def test_failed_checkpoint_never_publishes_output(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    rows, staging_contract, source_contract, manifest_schema = checkpoint_inputs
    broken = deepcopy(rows)
    del broken["stg_synthetic_regions"][0]["label"]
    output = tmp_path / "failed"
    with pytest.raises(StagingCheckpointError, match="columns or order differ"):
        write_staging_checkpoint(
            output,
            broken,
            staging_contract,
            source_contract,
            SOURCE_CONTRACT_SHA256,
            sha256_file(FIXTURE_DIR / "synthetic_staging_contract.json"),
            manifest_schema,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".failed.tmp-*"))


def test_checkpoint_refuses_overwrite(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    output = tmp_path / "checkpoint"
    _write(output, checkpoint_inputs)
    with pytest.raises(StagingCheckpointError, match="already exists"):
        _write(output, checkpoint_inputs)


def test_artifact_tampering_is_detected(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    output = tmp_path / "checkpoint"
    manifest = _write(output, checkpoint_inputs)
    artifact = output / "tables" / "stg_synthetic_measurements.parquet"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(StagingCheckpointError, match="byte count differs"):
        verify_staging_checkpoint_artifacts(output, manifest)


def test_manifest_file_tampering_is_detected(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    output = tmp_path / "checkpoint"
    manifest = _write(output, checkpoint_inputs)
    manifest_path = output / "staging_checkpoint_manifest.json"
    changed = deepcopy(manifest)
    changed["status"] = "INVALID"
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(StagingCheckpointError, match="manifest file differs"):
        verify_staging_checkpoint_artifacts(output, manifest)


def test_manifest_rejects_contract_hash_drift(
    tmp_path: Path, checkpoint_inputs: tuple[dict, dict, dict, dict]
) -> None:
    manifest = _write(tmp_path / "checkpoint", checkpoint_inputs)
    rows, staging_contract, source_contract, manifest_schema = checkpoint_inputs
    changed = deepcopy(manifest)
    changed["staging_table_contract_sha256"] = "f" * 64
    with pytest.raises(StagingCheckpointError, match="different staging contract"):
        validate_staging_checkpoint_manifest(
            changed,
            manifest_schema,
            staging_contract,
            source_contract,
            SOURCE_CONTRACT_SHA256,
            sha256_file(FIXTURE_DIR / "synthetic_staging_contract.json"),
        )
