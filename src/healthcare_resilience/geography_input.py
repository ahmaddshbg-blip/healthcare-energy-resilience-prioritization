"""Trusted read-only staging boundary for county geography reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from .contracts import load_json, validate_repository_contracts, validate_schema
from .geography import build_geography_outputs
from .geography_checkpoint import (
    StagingInputIdentity,
    _write_geography_checkpoint,
)
from .hashing import sha256_file, sha256_json
from .staging_build import (
    BUILD_MANIFEST_FILENAME,
    StagingBuildError,
    capture_repository_identity,
)
from .staging_checkpoint import (
    MANIFEST_FILENAME as STAGING_CHECKPOINT_MANIFEST_FILENAME,
    verify_staging_checkpoint_artifacts,
)


class GeographyInputError(ValueError):
    """Raised when accepted staging evidence cannot be trusted or loaded."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeographyInputError(message)


def _staging_checkpoint_summary(
    checkpoint_directory: Path,
    checkpoint_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path = checkpoint_directory / STAGING_CHECKPOINT_MANIFEST_FILENAME
    return {
        "relative_path": "checkpoint",
        "manifest_canonical_sha256": sha256_json(checkpoint_manifest),
        "manifest_file_sha256": sha256_file(manifest_path),
        "table_count": checkpoint_manifest["table_count"],
        "total_row_count": checkpoint_manifest["total_row_count"],
        "tables": [
            {
                "staging_table_id": table["staging_table_id"],
                "canonical_content_sha256": table["canonical_content_sha256"],
                "schema_sha256": table["schema_sha256"],
                "artifact_sha256": table["artifact_sha256"],
            }
            for table in checkpoint_manifest["tables"]
        ],
    }


def verify_staging_geography_input(
    build_directory: Path,
    repository_root: Path,
    geography_contract: Mapping[str, Any],
    staging_contract: Mapping[str, Any],
    source_table_contract: Mapping[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
) -> StagingInputIdentity:
    """Verify exact build evidence and all six staging artifacts without writes."""

    build_directory = build_directory.resolve()
    repository_root = repository_root.resolve()
    _require(build_directory.is_dir(), "staging build directory is missing")
    _require(
        not build_directory.is_relative_to(repository_root),
        "staging build must remain outside the public repository",
    )
    build_manifest_path = build_directory / BUILD_MANIFEST_FILENAME
    checkpoint_directory = build_directory / "checkpoint"
    checkpoint_manifest_path = (
        checkpoint_directory / STAGING_CHECKPOINT_MANIFEST_FILENAME
    )
    try:
        build_manifest = load_json(build_manifest_path)
        checkpoint_manifest = load_json(checkpoint_manifest_path)
    except (OSError, ValueError) as error:
        raise GeographyInputError("staging input manifest cannot be read") from error

    validate_schema(build_manifest, staging_build_schema, "staging build manifest")
    identity_inputs = build_manifest["build_identity_inputs"]
    _require(
        build_manifest["build_identity"] == sha256_json(identity_inputs),
        "staging build identity differs from canonical inputs",
    )
    _require(
        build_manifest["build_identity"]
        == geography_contract["input_staging_build_identity"],
        "staging build identity differs from geography contract",
    )
    _require(
        build_directory.name == build_manifest["build_identity"],
        "staging build path is not content-addressed by build identity",
    )
    _require(identity_inputs["repository_clean"] is True, "staging build was not clean")
    _require(
        identity_inputs["source_snapshot_id"]
        == staging_contract["source_snapshot_id"]
        == geography_contract["source_snapshot_id"],
        "staging input source snapshot identity differs",
    )
    _require(
        identity_inputs["source_contract_sha256"] == source_contract_sha256,
        "staging input source-contract identity differs",
    )
    _require(
        identity_inputs["source_table_contract_sha256"]
        == source_table_contract_sha256
        == staging_contract["source_table_contract_sha256"],
        "staging input source-table-contract identity differs",
    )
    _require(
        identity_inputs["staging_table_contract_sha256"]
        == staging_contract_sha256
        == geography_contract["staging_table_contract_sha256"],
        "staging input staging-contract identity differs",
    )
    verification = build_manifest["snapshot_verification"]
    _require(
        verification["reports_identical"] is True
        and verification["pre_build_report_sha256"]
        == verification["post_build_report_sha256"]
        and verification["expected_file_count"]
        == verification["verified_file_count"],
        "staging build snapshot-verification evidence is inconsistent",
    )
    expected_source_table_count = source_table_contract.get(
        "expected_table_count", len(source_table_contract["table_contracts"])
    )
    _require(
        build_manifest["source_table_profile"]["table_count"]
        == expected_source_table_count,
        "staging build source-table profile count differs",
    )
    _require(
        build_manifest["independent_verification"] is True,
        "staging build lacks independent verification",
    )

    build_manifest_file_sha256 = sha256_file(build_manifest_path)
    checkpoint_manifest_canonical_sha256 = sha256_json(checkpoint_manifest)
    checkpoint_manifest_file_sha256 = sha256_file(checkpoint_manifest_path)
    observed_identity = StagingInputIdentity(
        build_manifest["build_identity"],
        build_manifest_file_sha256,
        checkpoint_manifest_canonical_sha256,
        checkpoint_manifest_file_sha256,
    )
    expected_identity = StagingInputIdentity(
        geography_contract["input_staging_build_identity"],
        geography_contract["input_staging_build_manifest_file_sha256"],
        geography_contract[
            "input_staging_checkpoint_manifest_canonical_sha256"
        ],
        geography_contract["input_staging_checkpoint_manifest_file_sha256"],
    )
    _require(
        observed_identity == expected_identity,
        "staging manifest evidence differs from geography contract",
    )
    _require(
        build_manifest["checkpoint"]
        == _staging_checkpoint_summary(checkpoint_directory, checkpoint_manifest),
        "staging build checkpoint summary differs from artifacts",
    )

    expected_ids = [item["id"] for item in staging_contract["staging_tables"]]
    geography_ids = [
        item["staging_table_id"] for item in geography_contract["source_rules"]
    ]
    context_ids = list(geography_contract["context_only_staging_table_ids"])
    _require(
        len(expected_ids) == 6
        and len(geography_ids) == 5
        and len(context_ids) == 1
        and set(expected_ids) == set(geography_ids).union(context_ids),
        "staging table set differs from mapped and context-only geography scope",
    )
    _require(
        checkpoint_manifest["table_count"] == len(expected_ids) == 6,
        "staging geography input must contain exactly six tables",
    )
    expected_files = {BUILD_MANIFEST_FILENAME}
    expected_files.add(f"checkpoint/{STAGING_CHECKPOINT_MANIFEST_FILENAME}")
    expected_files.update(
        f"checkpoint/{table['relative_path']}"
        for table in checkpoint_manifest["tables"]
    )
    observed_files = {
        path.relative_to(build_directory).as_posix()
        for path in build_directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    _require(
        observed_files == expected_files,
        "staging build contains missing or unexpected files",
    )
    _require(
        not any(path.is_symlink() for path in build_directory.rglob("*")),
        "staging build contains a symbolic link",
    )
    verify_staging_checkpoint_artifacts(
        checkpoint_directory,
        checkpoint_manifest,
        staging_checkpoint_schema,
        dict(staging_contract),
        dict(source_table_contract),
        source_contract_sha256,
        staging_contract_sha256,
    )
    return observed_identity


def _quoted_identifier(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _required_geography_fields(
    geography_contract: Mapping[str, Any],
    rule: Mapping[str, Any],
) -> list[str]:
    if rule["rule_kind"] != "CENSUS_REFERENCE":
        return list(rule["geography_fields"])
    reference = geography_contract["reference"]
    return [
        reference["summary_level_field"],
        reference["state_field"],
        reference["county_field"],
        reference["state_name_field"],
        reference["county_name_field"],
        reference["population_field"],
    ]


def load_verified_geography_rows(
    build_directory: Path,
    repository_root: Path,
    geography_contract: Mapping[str, Any],
    staging_contract: Mapping[str, Any],
    source_table_contract: Mapping[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
) -> tuple[dict[str, list[dict[str, Any]]], StagingInputIdentity]:
    """Load only lineage and contracted geography fields between two verifications."""

    verification_arguments = (
        build_directory,
        repository_root,
        geography_contract,
        staging_contract,
        source_table_contract,
        staging_build_schema,
        staging_checkpoint_schema,
        source_contract_sha256,
        source_table_contract_sha256,
        staging_contract_sha256,
    )
    before = verify_staging_geography_input(*verification_arguments)
    checkpoint_directory = build_directory / "checkpoint"
    checkpoint_manifest = load_json(
        checkpoint_directory / STAGING_CHECKPOINT_MANIFEST_FILENAME
    )
    manifest_tables = {
        item["staging_table_id"]: item for item in checkpoint_manifest["tables"]
    }
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    connection = duckdb.connect(database=":memory:")
    try:
        for rule in geography_contract["source_rules"]:
            table_id = rule["staging_table_id"]
            fields = ["source_row_number", *_required_geography_fields(geography_contract, rule)]
            _require(
                len(fields) == len(set(fields)),
                f"{table_id}: geography field selection contains duplicates",
            )
            artifact_path = checkpoint_directory / manifest_tables[table_id]["relative_path"]
            relation = connection.read_parquet(str(artifact_path))
            _require(
                set(fields).issubset(relation.columns),
                f"{table_id}: contracted geography field is missing",
            )
            projection = ", ".join(_quoted_identifier(field) for field in fields)
            values = relation.project(projection).order('"source_row_number"').fetchall()
            rows_by_table[table_id] = [
                dict(zip(fields, row_values)) for row_values in values
            ]
    finally:
        connection.close()
    after = verify_staging_geography_input(*verification_arguments)
    _require(before == after, "staging evidence changed while geography fields were read")
    return rows_by_table, before


def _build_geography_from_verified_staging(
    build_directory: Path,
    output_root: Path,
    repository_root: Path,
    geography_contract: dict[str, Any],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    geography_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
    geography_contract_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    """Build geography outputs only through the trusted staging verifier."""

    try:
        initial_commit = capture_repository_identity(repository_root)
    except StagingBuildError as error:
        raise GeographyInputError(str(error)) from error

    verification_arguments = (
        build_directory,
        repository_root,
        geography_contract,
        staging_contract,
        source_table_contract,
        staging_build_schema,
        staging_checkpoint_schema,
        source_contract_sha256,
        source_table_contract_sha256,
        staging_contract_sha256,
    )

    def trusted_probe() -> StagingInputIdentity:
        return verify_staging_geography_input(*verification_arguments)

    rows_by_table, input_identity = load_verified_geography_rows(
        *verification_arguments
    )
    outputs = build_geography_outputs(rows_by_table, geography_contract)
    _require(trusted_probe() == input_identity, "staging evidence changed after reconciliation")
    try:
        _require(
            capture_repository_identity(repository_root) == initial_commit,
            "repository identity changed during geography reconciliation",
        )
    except StagingBuildError as error:
        raise GeographyInputError(str(error)) from error
    return _write_geography_checkpoint(
        output_root,
        outputs,
        geography_contract,
        geography_contract_sha256,
        geography_checkpoint_schema,
        repository_root,
        trusted_probe,
    )


def run_frozen_geography_reconciliation(
    data_root: Path,
    repository_root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Use only accepted public contracts; this function has no bypass option."""

    repository_root = repository_root.resolve()
    data_root = data_root.resolve()
    _require(
        not data_root.is_relative_to(repository_root),
        "private data root must remain outside the public repository",
    )
    validate_repository_contracts(repository_root)
    config_dir = repository_root / "configs"
    geography_contract = load_json(config_dir / "geography.json")
    staging_contract = load_json(config_dir / "staging_tables.json")
    source_table_contract = load_json(config_dir / "source_tables.json")
    build_directory = (
        data_root
        / "checkpoints"
        / geography_contract["source_snapshot_id"]
        / "source_preserving_staging"
        / geography_contract["input_staging_build_identity"]
    )
    output_root = (
        data_root
        / "checkpoints"
        / geography_contract["source_snapshot_id"]
        / "geography_reconciliation"
    )
    return _build_geography_from_verified_staging(
        build_directory,
        output_root,
        repository_root,
        geography_contract,
        staging_contract,
        source_table_contract,
        load_json(config_dir / "staging_build.schema.json"),
        load_json(config_dir / "staging_checkpoint.schema.json"),
        load_json(config_dir / "geography_checkpoint.schema.json"),
        sha256_file(config_dir / "sources.json"),
        sha256_file(config_dir / "source_tables.json"),
        sha256_file(config_dir / "staging_tables.json"),
        sha256_file(config_dir / "geography.json"),
    )
