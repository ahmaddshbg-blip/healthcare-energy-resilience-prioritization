"""Atomic checkpoint publication for verified county source evidence."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

import duckdb

from .contracts import validate_schema
from .hashing import sha256_file, sha256_json
from .staging_build import (
    StagingBuildError,
    capture_environment_identity,
    capture_repository_identity,
)

MANIFEST_FILENAME = "county_evidence_manifest.json"
ARTIFACT_FILENAME = "county_evidence.parquet"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EvidenceInputIdentity(NamedTuple):
    staging_build_identity: str
    staging_build_manifest_file_sha256: str
    staging_checkpoint_manifest_canonical_sha256: str
    staging_checkpoint_manifest_file_sha256: str
    geography_checkpoint_identity: str
    geography_manifest_canonical_sha256: str
    geography_manifest_file_sha256: str


class CountyEvidenceCheckpointError(ValueError):
    """Raised when an evidence checkpoint fails an integrity control."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CountyEvidenceCheckpointError(message)


def _duckdb_type(output_type: str) -> str:
    return {
        "STRING": "VARCHAR",
        "INTEGER": "BIGINT",
        "NUMBER": "DOUBLE",
        "BOOLEAN": "BOOLEAN",
    }[output_type]


def _physical_columns(relation: duckdb.DuckDBPyRelation) -> list[dict[str, str]]:
    return [
        {"name": name, "duckdb_type": str(data_type)}
        for name, data_type in zip(relation.columns, relation.types)
    ]


def validate_county_evidence_rows(
    rows: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> None:
    columns = contract["output_columns"]
    names = [item["name"] for item in columns]
    _require(
        len(rows) == contract["reference"]["expected_county_count"],
        "county evidence row count differs",
    )
    for position, row in enumerate(rows, start=1):
        _require(list(row) == names, f"county evidence row {position} columns differ")
        for column in columns:
            value = row[column["name"]]
            if value is None:
                _require(column["null_allowed"], f"{column['name']}: forbidden null")
            elif column["output_type"] == "STRING":
                _require(isinstance(value, str), f"{column['name']}: not text")
            elif column["output_type"] == "INTEGER":
                _require(type(value) is int, f"{column['name']}: not integer")
            elif column["output_type"] == "NUMBER":
                _require(
                    type(value) in (int, float) and math.isfinite(value),
                    f"{column['name']}: not finite number",
                )
            else:
                _require(type(value) is bool, f"{column['name']}: not boolean")
    fips = [row["canonical_fips"] for row in rows]
    _require(fips == sorted(fips) and len(fips) == len(set(fips)), "county evidence grain differs")
    eligible = 0
    out_of_scope = 0
    for row in rows:
        status = row["decision_scope_status"]
        _require(
            re.fullmatch(r"[0-9]{5}", row["canonical_fips"]) is not None
            and row["canonical_fips"] == row["state_fips"] + row["county_code"]
            and row["population"] > 0,
            "county reference semantics differ",
        )
        _require(row["evidence_valid"] is True, "county evidence validity flag differs")
        _require(row["fema_present"] is True, "FEMA presence must be true")
        _require(
            row["fema_mapping_status"] == "DIRECT_REFERENCE"
            and row["fema_source_row_number"] > 0
            and 0 <= row["fema_risk_score"] <= 100,
            "FEMA evidence semantics differ",
        )
        for code in contract["hazard_codes"]:
            prefix = f"fema_{code.lower()}_risk"
            score = row[f"{prefix}_score"]
            rating = row[f"{prefix}_rating"]
            _require(
                rating != "Not Applicable" or score is None,
                f"{code}: Not Applicable hazard score must remain null",
            )
        _require(SHA256_PATTERN.fullmatch(row["hpsa_lineage_sha256"]) is not None, "HPSA lineage hash differs")
        _require(SHA256_PATTERN.fullmatch(row["site_lineage_sha256"]) is not None, "site lineage hash differs")
        for prefix in ("hpsa", "site"):
            count = row[f"{prefix}_mapped_source_row_count"]
            _require(count >= 0, f"{prefix} mapped count is negative")
            _require(row[f"{prefix}_present"] is (count > 0), f"{prefix} presence differs")
        for count_field, max_field in (
            ("hpsa_designated_eligible_row_count", "hpsa_designated_max_raw_score"),
            ("hpsa_designated_with_proposed_eligible_row_count", "hpsa_designated_with_proposed_max_raw_score"),
        ):
            _require(
                (row[count_field] == 0) is (row[max_field] is None),
                f"{max_field}: null/count relationship differs",
            )
        for field in ("site_status_counts_json", "site_location_type_counts_json"):
            try:
                counts = json.loads(row[field])
            except (TypeError, json.JSONDecodeError) as error:
                raise CountyEvidenceCheckpointError(f"{field}: invalid JSON") from error
            _require(
                isinstance(counts, dict)
                and all(isinstance(key, str) and type(value) is int and value >= 0 for key, value in counts.items())
                and sum(counts.values()) == row["site_mapped_source_row_count"],
                f"{field}: category counts differ",
            )
            canonical = json.dumps(
                dict(sorted(counts.items())), ensure_ascii=True, allow_nan=False,
                separators=(",", ":"), sort_keys=True,
            )
            _require(row[field] == canonical, f"{field}: encoding is not canonical")
        _require(
            0 <= row["hpsa_exact_duplicate_count"] <= row["hpsa_mapped_source_row_count"]
            and 0 <= row["hpsa_distinct_id_count"] <= row["hpsa_mapped_source_row_count"],
            "HPSA count diagnostics differ",
        )
        if row["hpsa_mapped_source_row_count"] == 0:
            _require(row["hpsa_lineage_sha256"] == sha256_json([]), "empty HPSA lineage hash differs")
        if row["site_mapped_source_row_count"] == 0:
            _require(row["site_lineage_sha256"] == sha256_json([]), "empty site lineage hash differs")
        if status == "ELIGIBLE":
            eligible += 1
            _require(row["hhs_present"] is True, "eligible county lacks HHS")
            _require(row["hhs_source_row_number"] is not None, "eligible HHS lineage is null")
            _require(
                row["hhs_mapping_status"] in {"DIRECT_REFERENCE", "EXACT_REPLACEMENT"}
                and row["hhs_source_row_number"] > 0
                and row["hhs_medicare_benes"] >= 0
                and row["hhs_power_dependent_devices_dme"] >= 0
                and row["hhs_power_dependent_devices_dme"] <= row["hhs_medicare_benes"]
                and row["hhs_dme_ambiguous_11"]
                is (row["hhs_power_dependent_devices_dme"] == 11),
                "eligible HHS evidence semantics differ",
            )
        elif status == "OUT_OF_SCOPE":
            out_of_scope += 1
            _require(row["hhs_present"] is False, "out-of-scope HHS presence differs")
            _require(
                all(row[field] is None for field in (
                    "hhs_source_row_number", "hhs_mapping_status", "hhs_mapping_rule_id",
                    "hhs_medicare_benes", "hhs_power_dependent_devices_dme",
                )) and row["hhs_dme_ambiguous_11"] is False,
                "out-of-scope HHS null semantics differ",
            )
        else:
            raise CountyEvidenceCheckpointError("unknown decision scope status")
    _require(
        eligible == contract["reference"]["eligible_count"]
        and out_of_scope == contract["reference"]["out_of_scope_count"],
        "county evidence scope counts differ",
    )


def _write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    names = [item["name"] for item in columns]
    definitions = ", ".join(
        f'"{item["name"]}" {_duckdb_type(item["output_type"])}'
        for item in columns
    )
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE TABLE county_evidence ({definitions})")
        placeholders = ", ".join("?" for _ in names)
        connection.executemany(
            f"INSERT INTO county_evidence VALUES ({placeholders})",
            [[row[name] for name in names] for row in rows],
        )
        relation = connection.table("county_evidence")
        relation.write_parquet(str(path), compression="zstd")
        observed = connection.read_parquet(str(path))
        _require(observed.columns == names, "county evidence Parquet columns changed")
        return _physical_columns(observed)
    finally:
        connection.close()


def _expected_input_identity(contract: Mapping[str, Any]) -> EvidenceInputIdentity:
    return EvidenceInputIdentity(
        contract["input_staging_build_identity"],
        contract["input_staging_build_manifest_file_sha256"],
        contract["input_staging_checkpoint_manifest_canonical_sha256"],
        contract["input_staging_checkpoint_manifest_file_sha256"],
        contract["input_geography_checkpoint_identity"],
        contract["input_geography_manifest_canonical_sha256"],
        contract["input_geography_manifest_file_sha256"],
    )


def validate_county_evidence_manifest(
    manifest: dict[str, Any],
    schema: dict[str, Any],
    contract: Mapping[str, Any],
    contract_sha256: str,
) -> None:
    validate_schema(manifest, schema, "county evidence checkpoint manifest")
    identity = manifest["checkpoint_identity_inputs"]
    _require(manifest["checkpoint_identity"] == sha256_json(identity), "evidence checkpoint identity differs")
    _require(identity["county_evidence_contract_sha256"] == contract_sha256, "evidence contract identity differs")
    for field in (
        "source_contract_sha256", "source_table_contract_sha256",
        "staging_table_contract_sha256", "method_contract_sha256",
        "geography_contract_sha256", "input_geography_contract_sha256",
        "input_geography_specification_sha256", "input_staging_build_identity",
        "input_staging_build_manifest_file_sha256",
        "input_staging_checkpoint_manifest_canonical_sha256",
        "input_staging_checkpoint_manifest_file_sha256",
        "input_geography_checkpoint_identity",
        "input_geography_manifest_canonical_sha256",
        "input_geography_manifest_file_sha256",
    ):
        _require(identity[field] == contract[field], f"manifest {field} differs")
    artifact = manifest["artifact"]
    columns = contract["output_columns"]
    physical = [
        {"name": item["name"], "duckdb_type": _duckdb_type(item["output_type"])}
        for item in columns
    ]
    _require(artifact["columns"] == columns, "evidence manifest logical columns differ")
    _require(artifact["physical_columns"] == physical, "evidence manifest physical columns differ")
    _require(artifact["row_count"] == contract["reference"]["expected_county_count"], "evidence manifest row count differs")
    _require(artifact["column_count"] == len(columns), "evidence manifest column count differs")
    _require(artifact["logical_schema_sha256"] == sha256_json(columns), "logical schema hash differs")
    _require(artifact["physical_schema_sha256"] == sha256_json(physical), "physical schema hash differs")
    _require(
        artifact["schema_sha256"] == sha256_json({"logical_columns": columns, "physical_columns": physical}),
        "combined schema hash differs",
    )


def verify_county_evidence_checkpoint(
    checkpoint_directory: Path,
    manifest: dict[str, Any],
    schema: dict[str, Any],
    contract: Mapping[str, Any],
    contract_sha256: str,
) -> None:
    _require(checkpoint_directory.is_dir(), "county evidence checkpoint is missing")
    validate_county_evidence_manifest(manifest, schema, contract, contract_sha256)
    manifest_path = checkpoint_directory / MANIFEST_FILENAME
    try:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CountyEvidenceCheckpointError("county evidence manifest cannot be read") from error
    _require(stored == manifest, "stored county evidence manifest differs")
    observed = {
        path.relative_to(checkpoint_directory).as_posix()
        for path in checkpoint_directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    _require(observed == {MANIFEST_FILENAME, ARTIFACT_FILENAME}, "evidence checkpoint file membership differs")
    _require(not any(path.is_symlink() for path in checkpoint_directory.rglob("*")), "evidence checkpoint contains symbolic link")
    artifact = manifest["artifact"]
    path = checkpoint_directory / ARTIFACT_FILENAME
    _require(path.stat().st_size == artifact["artifact_bytes"], "evidence artifact byte count differs")
    _require(sha256_file(path) == artifact["artifact_sha256"], "evidence artifact hash differs")
    connection = duckdb.connect(database=":memory:")
    try:
        relation = connection.read_parquet(str(path))
        _require(relation.columns == [item["name"] for item in artifact["columns"]], "evidence artifact columns differ")
        _require(_physical_columns(relation) == artifact["physical_columns"], "evidence artifact physical schema differs")
        rows = [dict(zip(relation.columns, values)) for values in relation.fetchall()]
    finally:
        connection.close()
    validate_county_evidence_rows(rows, contract)
    _require(len(rows) == artifact["row_count"], "evidence artifact row count differs")
    _require(sha256_json(rows) == artifact["canonical_content_sha256"], "evidence canonical content differs")


def write_county_evidence_checkpoint(
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    contract_sha256: str,
    manifest_schema: dict[str, Any],
    repository_root: Path,
    input_identity_probe: Callable[[], EvidenceInputIdentity],
) -> tuple[Path, dict[str, Any]]:
    repository_root = repository_root.resolve()
    output_root = output_root.resolve()
    _require(not output_root.is_relative_to(repository_root), "evidence checkpoint root must remain outside public repository")
    validate_county_evidence_rows(rows, contract)
    try:
        code_commit = capture_repository_identity(repository_root)
        lock_sha256, environment = capture_environment_identity(repository_root)
    except StagingBuildError as error:
        raise CountyEvidenceCheckpointError(str(error)) from error
    input_identity = input_identity_probe()
    _require(input_identity == _expected_input_identity(contract), "evidence input identity differs from contract")
    identity_inputs = {
        "county_evidence_contract_sha256": contract_sha256,
        "source_contract_sha256": contract["source_contract_sha256"],
        "source_table_contract_sha256": contract["source_table_contract_sha256"],
        "staging_table_contract_sha256": contract["staging_table_contract_sha256"],
        "method_contract_sha256": contract["method_contract_sha256"],
        "geography_contract_sha256": contract["geography_contract_sha256"],
        "input_geography_contract_sha256": contract["input_geography_contract_sha256"],
        "input_geography_specification_sha256": contract["input_geography_specification_sha256"],
        "input_staging_build_identity": input_identity.staging_build_identity,
        "input_staging_build_manifest_file_sha256": input_identity.staging_build_manifest_file_sha256,
        "input_staging_checkpoint_manifest_canonical_sha256": input_identity.staging_checkpoint_manifest_canonical_sha256,
        "input_staging_checkpoint_manifest_file_sha256": input_identity.staging_checkpoint_manifest_file_sha256,
        "input_geography_checkpoint_identity": input_identity.geography_checkpoint_identity,
        "input_geography_manifest_canonical_sha256": input_identity.geography_manifest_canonical_sha256,
        "input_geography_manifest_file_sha256": input_identity.geography_manifest_file_sha256,
        "code_commit": code_commit,
        "repository_clean": True,
        "requirements_lock_sha256": lock_sha256,
        "environment": environment,
    }
    identity = sha256_json(identity_inputs)
    output = output_root / identity
    _require(not output.exists(), "county evidence checkpoint output already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".{identity}.tmp-{uuid4().hex}"
    temporary.mkdir()
    try:
        artifact_path = temporary / ARTIFACT_FILENAME
        physical = _write_parquet(artifact_path, rows, contract["output_columns"])
        artifact = {
            "artifact_id": "county_evidence",
            "relative_path": ARTIFACT_FILENAME,
            "row_count": len(rows),
            "column_count": len(contract["output_columns"]),
            "columns": contract["output_columns"],
            "logical_schema_sha256": sha256_json(contract["output_columns"]),
            "physical_columns": physical,
            "physical_schema_sha256": sha256_json(physical),
            "schema_sha256": sha256_json({"logical_columns": contract["output_columns"], "physical_columns": physical}),
            "canonical_content_sha256": sha256_json(rows),
            "artifact_sha256": sha256_file(artifact_path),
            "artifact_bytes": artifact_path.stat().st_size,
        }
        _require(input_identity_probe() == input_identity, "evidence input changed during checkpoint build")
        manifest = {
            "schema_version": "1.0.0",
            "manifest_type": "COUNTY_SOURCE_EVIDENCE_CHECKPOINT",
            "status": "VALID",
            "checkpoint_identity_algorithm": "SHA256_CANONICAL_COUNTY_EVIDENCE_INPUTS_V1",
            "checkpoint_identity": identity,
            "checkpoint_identity_inputs": identity_inputs,
            "content_hash_algorithm": "SHA256_CANONICAL_TYPED_ROWS_V1",
            "schema_hash_algorithm": "SHA256_CANONICAL_LOGICAL_AND_PHYSICAL_SCHEMA_V1",
            "artifact_hash_algorithm": "SHA256_FILE_BYTES",
            "parquet_hash_portability": "LOCAL_BINARY_EXACT_NOT_CROSS_PLATFORM_GUARANTEED",
            "artifact_count": 1,
            "artifact": artifact,
        }
        validate_county_evidence_manifest(manifest, manifest_schema, contract, contract_sha256)
        (temporary / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        verify_county_evidence_checkpoint(temporary, manifest, manifest_schema, contract, contract_sha256)
        _require(input_identity_probe() == input_identity, "evidence input changed after checkpoint verification")
        try:
            final_commit = capture_repository_identity(repository_root)
        except StagingBuildError as error:
            raise CountyEvidenceCheckpointError(str(error)) from error
        _require(final_commit == code_commit, "repository identity changed during evidence build")
        os.replace(temporary, output)
        return output, manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
