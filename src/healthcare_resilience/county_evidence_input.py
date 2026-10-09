"""Trusted read-only inputs and orchestration for county source evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from .contracts import load_json, validate_repository_contracts
from .county_evidence import build_county_evidence
from .county_evidence_checkpoint import (
    EvidenceInputIdentity,
    write_county_evidence_checkpoint,
)
from .geography_checkpoint import (
    MANIFEST_FILENAME as GEOGRAPHY_MANIFEST_FILENAME,
    verify_geography_checkpoint_artifacts,
)
from .geography_input import verify_staging_geography_input
from .hashing import sha256_file, sha256_json
from .staging_build import StagingBuildError, capture_repository_identity
from .staging_checkpoint import MANIFEST_FILENAME as STAGING_MANIFEST_FILENAME


class CountyEvidenceInputError(ValueError):
    """Raised when staging or geography evidence cannot be trusted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CountyEvidenceInputError(message)


def verify_county_evidence_inputs(
    staging_build_directory: Path,
    geography_checkpoint_directory: Path,
    repository_root: Path,
    evidence_contract: Mapping[str, Any],
    geography_contract: Mapping[str, Any],
    staging_contract: Mapping[str, Any],
    source_table_contract: Mapping[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    geography_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
    geography_contract_sha256: str,
) -> EvidenceInputIdentity:
    """Verify accepted staging and geography artifacts without modifying them."""

    repository_root = repository_root.resolve()
    geography_checkpoint_directory = geography_checkpoint_directory.resolve()
    _require(geography_checkpoint_directory.is_dir(), "geography checkpoint directory is missing")
    _require(
        not geography_checkpoint_directory.is_relative_to(repository_root),
        "geography checkpoint must remain outside public repository",
    )
    staging_identity = verify_staging_geography_input(
        staging_build_directory,
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
    manifest_path = geography_checkpoint_directory / GEOGRAPHY_MANIFEST_FILENAME
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError) as error:
        raise CountyEvidenceInputError("geography manifest cannot be read") from error
    verify_geography_checkpoint_artifacts(
        geography_checkpoint_directory,
        manifest,
        geography_checkpoint_schema,
        geography_contract,
        geography_contract_sha256,
    )
    _require(
        geography_checkpoint_directory.name == manifest["checkpoint_identity"],
        "geography checkpoint path is not content-addressed",
    )
    identity = EvidenceInputIdentity(
        staging_identity.build_identity,
        staging_identity.build_manifest_file_sha256,
        staging_identity.checkpoint_manifest_canonical_sha256,
        staging_identity.checkpoint_manifest_file_sha256,
        manifest["checkpoint_identity"],
        sha256_json(manifest),
        sha256_file(manifest_path),
    )
    expected = EvidenceInputIdentity(
        evidence_contract["input_staging_build_identity"],
        evidence_contract["input_staging_build_manifest_file_sha256"],
        evidence_contract["input_staging_checkpoint_manifest_canonical_sha256"],
        evidence_contract["input_staging_checkpoint_manifest_file_sha256"],
        evidence_contract["input_geography_checkpoint_identity"],
        evidence_contract["input_geography_manifest_canonical_sha256"],
        evidence_contract["input_geography_manifest_file_sha256"],
    )
    _require(identity == expected, "accepted evidence input identities differ")
    geography_inputs = manifest["checkpoint_identity_inputs"]
    _require(
        geography_inputs["input_staging_build_identity"] == staging_identity.build_identity
        and geography_inputs["input_staging_build_manifest_file_sha256"]
        == staging_identity.build_manifest_file_sha256
        and geography_inputs["input_staging_checkpoint_manifest_canonical_sha256"]
        == staging_identity.checkpoint_manifest_canonical_sha256
        and geography_inputs["input_staging_checkpoint_manifest_file_sha256"]
        == staging_identity.checkpoint_manifest_file_sha256,
        "geography checkpoint is not bound to the accepted staging evidence",
    )
    return identity


def _quoted(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def load_verified_county_evidence_inputs(
    staging_build_directory: Path,
    geography_checkpoint_directory: Path,
    repository_root: Path,
    evidence_contract: Mapping[str, Any],
    geography_contract: Mapping[str, Any],
    staging_contract: Mapping[str, Any],
    source_table_contract: Mapping[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    geography_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
    geography_contract_sha256: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], EvidenceInputIdentity]:
    """Read only contracted fields between two complete input verifications."""

    arguments = (
        staging_build_directory,
        geography_checkpoint_directory,
        repository_root,
        evidence_contract,
        geography_contract,
        staging_contract,
        source_table_contract,
        staging_build_schema,
        staging_checkpoint_schema,
        geography_checkpoint_schema,
        source_contract_sha256,
        source_table_contract_sha256,
        staging_contract_sha256,
        geography_contract_sha256,
    )
    before = verify_county_evidence_inputs(*arguments)
    staging_checkpoint = staging_build_directory / "checkpoint"
    staging_manifest = load_json(staging_checkpoint / STAGING_MANIFEST_FILENAME)
    staging_artifacts = {
        item["staging_table_id"]: item for item in staging_manifest["tables"]
    }
    geography_manifest = load_json(
        geography_checkpoint_directory / GEOGRAPHY_MANIFEST_FILENAME
    )
    geography_artifacts = {
        item["artifact_id"]: item for item in geography_manifest["tables"]
    }
    _require(
        "stg_hhs_empower_history_county"
        not in {role["staging_table_id"] for role in evidence_contract["source_roles"]},
        "historical HHS is prohibited from evidence selection",
    )
    staging_rows: dict[str, list[dict[str, Any]]] = {}
    source_maps: dict[str, list[dict[str, Any]]] = {}
    connection = duckdb.connect(database=":memory:")
    try:
        for role in evidence_contract["source_roles"]:
            table_id = role["staging_table_id"]
            fields = ["source_row_number", *role["required_fields"]]
            artifact = staging_checkpoint / staging_artifacts[table_id]["relative_path"]
            relation = connection.read_parquet(str(artifact))
            _require(set(fields).issubset(relation.columns), f"{table_id}: evidence field is missing")
            projection = ", ".join(_quoted(field) for field in fields)
            selected = relation.project(projection).order('"source_row_number"')
            staging_rows[table_id] = [
                dict(zip(fields, values)) for values in selected.fetchall()
            ]
            map_artifact = geography_checkpoint_directory / geography_artifacts[role["map_artifact_id"]]["relative_path"]
            mapped = connection.read_parquet(str(map_artifact)).order('"source_row_number"')
            source_maps[table_id] = [
                dict(zip(mapped.columns, values)) for values in mapped.fetchall()
            ]
        reference_artifact = geography_checkpoint_directory / geography_artifacts[evidence_contract["reference"]["artifact_id"]]["relative_path"]
        reference = connection.read_parquet(str(reference_artifact)).order('"canonical_fips"')
        county_reference = [
            dict(zip(reference.columns, values)) for values in reference.fetchall()
        ]
    finally:
        connection.close()
    after = verify_county_evidence_inputs(*arguments)
    _require(before == after, "accepted evidence inputs changed while being read")
    return staging_rows, {"county_reference": county_reference, "source_maps": source_maps}, before


def _build_county_evidence_from_verified_inputs(
    staging_build_directory: Path,
    geography_checkpoint_directory: Path,
    output_root: Path,
    repository_root: Path,
    evidence_contract: dict[str, Any],
    geography_contract: dict[str, Any],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    staging_build_schema: dict[str, Any],
    staging_checkpoint_schema: dict[str, Any],
    geography_checkpoint_schema: dict[str, Any],
    evidence_checkpoint_schema: dict[str, Any],
    source_contract_sha256: str,
    source_table_contract_sha256: str,
    staging_contract_sha256: str,
    geography_contract_sha256: str,
    evidence_contract_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    try:
        initial_commit = capture_repository_identity(repository_root)
    except StagingBuildError as error:
        raise CountyEvidenceInputError(str(error)) from error
    verification_arguments = (
        staging_build_directory,
        geography_checkpoint_directory,
        repository_root,
        evidence_contract,
        geography_contract,
        staging_contract,
        source_table_contract,
        staging_build_schema,
        staging_checkpoint_schema,
        geography_checkpoint_schema,
        source_contract_sha256,
        source_table_contract_sha256,
        staging_contract_sha256,
        geography_contract_sha256,
    )

    def probe() -> EvidenceInputIdentity:
        return verify_county_evidence_inputs(*verification_arguments)

    staging_rows, geography_outputs, identity = load_verified_county_evidence_inputs(
        *verification_arguments
    )
    rows = build_county_evidence(staging_rows, geography_outputs, evidence_contract)
    _require(probe() == identity, "accepted evidence inputs changed after transformation")
    try:
        _require(
            capture_repository_identity(repository_root) == initial_commit,
            "repository identity changed during evidence transformation",
        )
    except StagingBuildError as error:
        raise CountyEvidenceInputError(str(error)) from error
    return write_county_evidence_checkpoint(
        output_root,
        rows,
        evidence_contract,
        evidence_contract_sha256,
        evidence_checkpoint_schema,
        repository_root,
        probe,
    )


def run_frozen_county_evidence_build(
    data_root: Path, repository_root: Path
) -> tuple[Path, dict[str, Any]]:
    """Run only accepted public contracts; no bypass or override is exposed."""

    repository_root = repository_root.resolve()
    data_root = data_root.resolve()
    _require(not data_root.is_relative_to(repository_root), "private data root must remain outside public repository")
    validate_repository_contracts(repository_root)
    config = repository_root / "configs"
    evidence_contract = load_json(config / "county_evidence.json")
    geography_contract = load_json(config / "geography.json")
    staging_contract = load_json(config / "staging_tables.json")
    source_table_contract = load_json(config / "source_tables.json")
    snapshot = evidence_contract["source_snapshot_id"]
    staging_directory = data_root / "checkpoints" / snapshot / "source_preserving_staging" / evidence_contract["input_staging_build_identity"]
    geography_directory = data_root / "checkpoints" / snapshot / "geography_reconciliation" / evidence_contract["input_geography_checkpoint_identity"]
    output_root = data_root / "checkpoints" / snapshot / "county_evidence"
    return _build_county_evidence_from_verified_inputs(
        staging_directory,
        geography_directory,
        output_root,
        repository_root,
        evidence_contract,
        geography_contract,
        staging_contract,
        source_table_contract,
        load_json(config / "staging_build.schema.json"),
        load_json(config / "staging_checkpoint.schema.json"),
        load_json(config / "geography_checkpoint.schema.json"),
        load_json(config / "county_evidence_checkpoint.schema.json"),
        sha256_file(config / "sources.json"),
        sha256_file(config / "source_tables.json"),
        sha256_file(config / "staging_tables.json"),
        sha256_file(config / "geography.json"),
        sha256_file(config / "county_evidence.json"),
    )
