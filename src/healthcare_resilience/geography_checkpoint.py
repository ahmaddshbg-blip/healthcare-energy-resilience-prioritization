"""Atomic Parquet checkpoints for county geography reconciliation outputs."""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from .contracts import validate_schema
from .geography import FIPS_PATTERN, MAPPING_STATUSES
from .hashing import sha256_file, sha256_json
from .staging_build import (
    StagingBuildError,
    capture_environment_identity,
    capture_repository_identity,
)

MANIFEST_FILENAME = "geography_checkpoint_manifest.json"

REFERENCE_SCHEMA = [
    {"name": "canonical_fips", "output_type": "STRING", "null_allowed": False},
    {"name": "state_fips", "output_type": "STRING", "null_allowed": False},
    {"name": "county_code", "output_type": "STRING", "null_allowed": False},
    {"name": "state_name", "output_type": "STRING", "null_allowed": False},
    {"name": "county_name", "output_type": "STRING", "null_allowed": False},
    {"name": "population", "output_type": "INTEGER", "null_allowed": False},
    {"name": "decision_scope_status", "output_type": "STRING", "null_allowed": False},
    {"name": "scope_reason", "output_type": "STRING", "null_allowed": True},
]
MAP_SCHEMA = [
    {"name": "source_table_id", "output_type": "STRING", "null_allowed": False},
    {"name": "source_row_number", "output_type": "INTEGER", "null_allowed": False},
    {"name": "source_fips_primary", "output_type": "STRING", "null_allowed": True},
    {"name": "source_fips_secondary", "output_type": "STRING", "null_allowed": True},
    {"name": "canonical_fips", "output_type": "STRING", "null_allowed": True},
    {"name": "mapping_status", "output_type": "STRING", "null_allowed": False},
    {"name": "mapping_rule_id", "output_type": "STRING", "null_allowed": False},
    {"name": "diagnostic_reason", "output_type": "STRING", "null_allowed": True},
]


class GeographyCheckpointError(ValueError):
    """Raised when a geography checkpoint fails an integrity control."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeographyCheckpointError(message)


def _physical_columns(relation: duckdb.DuckDBPyRelation) -> list[dict[str, str]]:
    return [
        {"name": name, "duckdb_type": str(data_type)}
        for name, data_type in zip(relation.columns, relation.types)
    ]


def _validate_rows(
    artifact_id: str,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
) -> None:
    names = [item["name"] for item in columns]
    for position, row in enumerate(rows, start=1):
        _require(list(row) == names, f"{artifact_id}: columns or order differ")
        for column in columns:
            value = row[column["name"]]
            if value is None:
                _require(
                    column["null_allowed"],
                    f"{artifact_id}: row {position} has forbidden null",
                )
            elif column["output_type"] == "STRING":
                _require(isinstance(value, str), f"{artifact_id}: value is not text")
            else:
                _require(type(value) is int, f"{artifact_id}: value is not an integer")


def _write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    names = [item["name"] for item in columns]
    definitions = ", ".join(
        f'"{item["name"].replace(chr(34), chr(34) * 2)}" '
        + ("VARCHAR" if item["output_type"] == "STRING" else "BIGINT")
        for item in columns
    )
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE TABLE geography_data ({definitions})")
        placeholders = ", ".join("?" for _ in names)
        connection.executemany(
            f"INSERT INTO geography_data VALUES ({placeholders})",
            [[row[name] for name in names] for row in rows],
        )
        relation = connection.table("geography_data")
        relation.write_parquet(str(path), compression="zstd")
        observed = connection.read_parquet(str(path))
        _require(observed.columns == names, f"{path.name}: Parquet columns changed")
        _require(observed.fetchall() == [tuple(row[name] for name in names) for row in rows],
                 f"{path.name}: Parquet values changed")
        return _physical_columns(observed)
    finally:
        connection.close()


def _table_definitions(
    outputs: Mapping[str, Any], contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    definitions = [
        {
            "artifact_id": "county_reference",
            "artifact_kind": "COUNTY_REFERENCE",
            "source_table_id": None,
            "rows": outputs["county_reference"],
            "columns": REFERENCE_SCHEMA,
        }
    ]
    for rule in contract["source_rules"]:
        table_id = rule["staging_table_id"]
        definitions.append(
            {
                "artifact_id": f"map_{table_id}",
                "artifact_kind": "SOURCE_GEOGRAPHY_MAP",
                "source_table_id": table_id,
                "rows": outputs["source_maps"][table_id],
                "columns": MAP_SCHEMA,
            }
        )
    return definitions


def _mapping_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(row["mapping_status"] for row in rows)
    return {status: counts[status] for status in MAPPING_STATUSES}


def _validate_checkpoint_semantics(
    reference_rows: Sequence[Mapping[str, Any]],
    source_maps: Mapping[str, Sequence[Mapping[str, Any]]],
    contract: Mapping[str, Any],
) -> None:
    reference_rule = contract["reference"]
    keys = [row["canonical_fips"] for row in reference_rows]
    _require(keys == sorted(keys), "county reference is not sorted by canonical FIPS")
    _require(len(keys) == len(set(keys)), "county reference contains duplicate FIPS")
    _require(all(FIPS_PATTERN.fullmatch(key) for key in keys), "county reference contains malformed FIPS")
    _require(
        all(
            row["canonical_fips"] == row["state_fips"] + row["county_code"]
            and row["decision_scope_status"] in {"ELIGIBLE", "OUT_OF_SCOPE"}
            and type(row["population"]) is int
            and row["population"] > 0
            for row in reference_rows
        ),
        "county reference row semantics differ",
    )
    observed_out = {
        row["canonical_fips"]
        for row in reference_rows
        if row["decision_scope_status"] == "OUT_OF_SCOPE"
    }
    _require(
        observed_out == set(reference_rule["out_of_scope_fips"]),
        "county reference out-of-scope set differs",
    )
    _require(
        sum(row["decision_scope_status"] == "ELIGIBLE" for row in reference_rows)
        == reference_rule["eligible_count"],
        "county reference eligible count differs",
    )

    reference_set = set(keys)
    eligible_set = {
        row["canonical_fips"]
        for row in reference_rows
        if row["decision_scope_status"] == "ELIGIBLE"
    }
    replacements = {
        item["source_fips"]: (item["canonical_fips"], item["rule_id"])
        for item in contract["exact_replacements"]
    }
    legacy = {
        fips: item["rule_id"]
        for item in contract["unresolved_legacy_groups"]
        for fips in item["source_fips"]
    }
    rules = {item["staging_table_id"]: item for item in contract["source_rules"]}
    for table_id, rows in source_maps.items():
        rule = rules[table_id]
        for row in rows:
            _require(row["source_table_id"] == table_id, f"{table_id}: source table lineage differs")
            status = row["mapping_status"]
            canonical = row["canonical_fips"]
            primary = row["source_fips_primary"]
            secondary = row["source_fips_secondary"]
            valid_values = [
                value for value in (primary, secondary)
                if isinstance(value, str) and FIPS_PATTERN.fullmatch(value)
            ]
            if rule["rule_kind"] != "HHS_SINGLE_FIPS":
                _require(
                    not set(valid_values).intersection(replacements),
                    f"{table_id}: HHS replacement code appears outside HHS",
                )
            if rule["rule_kind"] == "DIRECT_DUAL_FIPS" and len(valid_values) == 2:
                _require(
                    valid_values[0] == valid_values[1],
                    f"{table_id}: valid HPSA FIPS fields conflict",
                )
            _require(status in MAPPING_STATUSES, f"{table_id}: unknown mapping status")
            if status in {"DIRECT_REFERENCE", "EXACT_REPLACEMENT"}:
                _require(
                    isinstance(canonical, str)
                    and FIPS_PATTERN.fullmatch(canonical) is not None
                    and canonical in reference_set,
                    f"{table_id}: mapped canonical FIPS is invalid",
                )
            else:
                _require(canonical is None, f"{table_id}: nonmapped status has canonical FIPS")

            if status == "EXACT_REPLACEMENT":
                _require(
                    rule["rule_kind"] == "HHS_SINGLE_FIPS"
                    and primary in replacements
                    and replacements[primary] == (canonical, row["mapping_rule_id"]),
                    f"{table_id}: replacement semantics differ",
                )
            elif status == "UNRESOLVED_LEGACY_GEOGRAPHY":
                _require(
                    rule["rule_kind"] == "HHS_SINGLE_FIPS"
                    and primary in legacy
                    and legacy[primary] == row["mapping_rule_id"],
                    f"{table_id}: unresolved legacy semantics differ",
                )
            elif status == "DIRECT_REFERENCE":
                if rule["rule_kind"] == "CENSUS_REFERENCE":
                    _require(canonical == primary + secondary, f"{table_id}: Census key differs")
                elif rule["rule_kind"] == "DIRECT_DUAL_FIPS":
                    _require(
                        row["mapping_rule_id"]
                        in {"HPSA_PRIMARY_FIPS", "HPSA_FALLBACK_FIPS"},
                        f"{table_id}: HPSA mapping rule differs",
                    )
                    chosen = primary if row["mapping_rule_id"] == "HPSA_PRIMARY_FIPS" else secondary
                    _require(chosen == canonical, f"{table_id}: HPSA field provenance differs")
                else:
                    _require(
                        primary == canonical
                        and row["mapping_rule_id"] == "EXACT_SOURCE_FIPS",
                        f"{table_id}: direct FIPS differs",
                    )
            elif status == "OUTSIDE_REFERENCE_UNIVERSE":
                _require(
                    valid_values and all(value not in reference_set for value in valid_values),
                    f"{table_id}: outside-universe semantics differ",
                )
            elif status == "MISSING_SOURCE_FIPS":
                _require(primary in (None, "") and secondary in (None, ""), f"{table_id}: missing-FIPS semantics differ")
            elif status == "INVALID_SOURCE_FIPS":
                values = [value for value in (primary, secondary) if value not in (None, "")]
                _require(
                    values and not any(
                        isinstance(value, str) and FIPS_PATTERN.fullmatch(value)
                        for value in values
                    ),
                    f"{table_id}: invalid-FIPS semantics differ",
                )
            elif status == "STATE_SUMMARY_NOT_COUNTY":
                _require(rule["rule_kind"] == "CENSUS_REFERENCE", f"{table_id}: state summary appears outside Census")

        coverage = rule["required_reference_coverage"]
        if coverage != "NONE":
            expected = reference_set if coverage == "ALL_REFERENCE_EXACTLY_ONCE" else eligible_set
            observed = Counter(
                row["canonical_fips"] for row in rows if row["canonical_fips"] is not None
            )
            _require(
                set(observed) == expected and all(count == 1 for count in observed.values()),
                f"{table_id}: checkpoint reference coverage differs",
            )


def validate_geography_checkpoint_manifest(
    manifest: dict[str, Any],
    manifest_schema: dict[str, Any],
    contract: Mapping[str, Any],
    geography_contract_sha256: str,
) -> None:
    """Validate manifest identity, table layout, and declared frozen counts."""

    validate_schema(manifest, manifest_schema, "geography checkpoint manifest")
    identity = manifest["checkpoint_identity_inputs"]
    _require(
        manifest["checkpoint_identity"] == sha256_json(identity),
        "geography checkpoint identity differs from canonical inputs",
    )
    _require(
        identity["geography_contract_sha256"] == geography_contract_sha256,
        "geography checkpoint references a different geography contract",
    )
    _require(
        identity["input_staging_build_identity"]
        == contract["input_staging_build_identity"],
        "geography checkpoint references a different staging build",
    )
    expected_ids = ["county_reference"] + [
        f"map_{item['staging_table_id']}" for item in contract["source_rules"]
    ]
    _require(
        [item["artifact_id"] for item in manifest["tables"]] == expected_ids,
        "geography checkpoint table order or identity differs",
    )
    _require(
        manifest["table_count"] == len(expected_ids) == len(manifest["tables"]),
        "geography checkpoint table count differs",
    )
    _require(
        manifest["tables"][0]["row_count"]
        == contract["reference"]["expected_county_count"],
        "county-reference row count differs",
    )
    rule_by_table = {
        item["staging_table_id"]: item for item in contract["source_rules"]
    }
    for table in manifest["tables"][1:]:
        rule = rule_by_table[table["source_table_id"]]
        _require(
            table["row_count"] == rule["expected_total_count"],
            f"{table['source_table_id']}: checkpoint row count differs",
        )
        for expected in rule["expected_mapping_counts"]:
            observed = sum(table["mapping_counts"][status] for status in expected["statuses"])
            _require(
                observed == expected["expected_count"],
                f"{table['source_table_id']}: checkpoint mapping count differs",
            )
    _require(
        manifest["total_row_count"] == sum(item["row_count"] for item in manifest["tables"]),
        "geography checkpoint total row count differs",
    )
    for table in manifest["tables"]:
        expected_kind = (
            "COUNTY_REFERENCE"
            if table["artifact_id"] == "county_reference"
            else "SOURCE_GEOGRAPHY_MAP"
        )
        expected_source = (
            None
            if expected_kind == "COUNTY_REFERENCE"
            else table["artifact_id"].removeprefix("map_")
        )
        expected_columns = (
            REFERENCE_SCHEMA if expected_kind == "COUNTY_REFERENCE" else MAP_SCHEMA
        )
        _require(
            table["artifact_kind"] == expected_kind,
            f"{table['artifact_id']}: artifact kind differs",
        )
        _require(
            table["source_table_id"] == expected_source,
            f"{table['artifact_id']}: source table identity differs",
        )
        _require(
            table["relative_path"] == f"tables/{table['artifact_id']}.parquet",
            f"{table['artifact_id']}: relative path differs",
        )
        columns = table["columns"]
        physical = table["physical_columns"]
        _require(
            columns == expected_columns,
            f"{table['artifact_id']}: logical columns differ",
        )
        _require(
            physical
            == [
                {
                    "name": column["name"],
                    "duckdb_type": (
                        "VARCHAR" if column["output_type"] == "STRING" else "BIGINT"
                    ),
                }
                for column in expected_columns
            ],
            f"{table['artifact_id']}: physical columns differ",
        )
        _require(table["column_count"] == len(columns), f"{table['artifact_id']}: column count differs")
        _require(table["logical_schema_sha256"] == sha256_json(columns), f"{table['artifact_id']}: logical schema hash differs")
        _require(table["physical_schema_sha256"] == sha256_json(physical), f"{table['artifact_id']}: physical schema hash differs")
        _require(
            table["schema_sha256"] == sha256_json({"logical_columns": columns, "physical_columns": physical}),
            f"{table['artifact_id']}: combined schema hash differs",
        )


def verify_geography_checkpoint_artifacts(
    checkpoint_directory: Path,
    manifest: dict[str, Any],
    manifest_schema: dict[str, Any],
    contract: Mapping[str, Any],
    geography_contract_sha256: str,
) -> None:
    """Independently reopen every artifact and reproduce manifest claims."""

    _require(checkpoint_directory.is_dir(), "geography checkpoint directory is missing")
    validate_geography_checkpoint_manifest(
        manifest, manifest_schema, contract, geography_contract_sha256
    )
    manifest_path = checkpoint_directory / MANIFEST_FILENAME
    try:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeographyCheckpointError("geography checkpoint manifest cannot be read") from error
    _require(stored == manifest, "stored geography manifest differs")
    expected_files = {MANIFEST_FILENAME} | {
        item["relative_path"] for item in manifest["tables"]
    }
    observed_files = {
        path.relative_to(checkpoint_directory).as_posix()
        for path in checkpoint_directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    _require(observed_files == expected_files, "geography checkpoint has missing or unexpected files")
    _require(
        not any(path.is_symlink() for path in checkpoint_directory.rglob("*")),
        "geography checkpoint contains a symbolic link",
    )
    connection = duckdb.connect(database=":memory:")
    reference_rows: list[dict[str, Any]] = []
    source_maps: dict[str, list[dict[str, Any]]] = {}
    try:
        for table in manifest["tables"]:
            path = checkpoint_directory / table["relative_path"]
            _require(path.stat().st_size == table["artifact_bytes"], f"{table['artifact_id']}: artifact byte count differs")
            _require(sha256_file(path) == table["artifact_sha256"], f"{table['artifact_id']}: artifact hash differs")
            relation = connection.read_parquet(str(path))
            _require(relation.columns == [item["name"] for item in table["columns"]], f"{table['artifact_id']}: artifact columns differ")
            _require(_physical_columns(relation) == table["physical_columns"], f"{table['artifact_id']}: physical schema differs")
            values = relation.fetchall()
            rows = [dict(zip(relation.columns, value)) for value in values]
            _validate_rows(table["artifact_id"], rows, table["columns"])
            _require(len(rows) == table["row_count"], f"{table['artifact_id']}: artifact row count differs")
            _require(sha256_json(rows) == table["canonical_content_sha256"], f"{table['artifact_id']}: canonical content differs")
            if table["artifact_kind"] == "SOURCE_GEOGRAPHY_MAP":
                _require(_mapping_counts(rows) == table["mapping_counts"], f"{table['artifact_id']}: mapping counts differ")
                _require(
                    [row["source_row_number"] for row in rows] == list(range(1, len(rows) + 1)),
                    f"{table['artifact_id']}: source lineage differs",
                )
                source_maps[table["source_table_id"]] = rows
            else:
                reference_rows = rows
    finally:
        connection.close()
    _validate_checkpoint_semantics(reference_rows, source_maps, contract)


def write_geography_checkpoint(
    output_root: Path,
    outputs: Mapping[str, Any],
    contract: Mapping[str, Any],
    geography_contract_sha256: str,
    manifest_schema: dict[str, Any],
    repository_root: Path,
    input_identity_probe: Callable[[], tuple[str, str]],
) -> tuple[Path, dict[str, Any]]:
    """Publish a verified checkpoint atomically from already-reconciled rows."""

    repository_root = repository_root.resolve()
    output_root = output_root.resolve()
    _require(
        not output_root.is_relative_to(repository_root),
        "geography checkpoint root must remain outside the public repository",
    )
    try:
        code_commit = capture_repository_identity(repository_root)
        requirements_lock_sha256, environment = capture_environment_identity(repository_root)
    except StagingBuildError as error:
        raise GeographyCheckpointError(str(error)) from error
    input_identity = input_identity_probe()
    _require(
        input_identity[0] == contract["input_staging_build_identity"],
        "input staging build identity differs from geography contract",
    )
    _require(
        len(input_identity[1]) == 64
        and all(character in "0123456789abcdef" for character in input_identity[1]),
        "input staging manifest identity is invalid",
    )
    definitions = _table_definitions(outputs, contract)
    _require(len(definitions) == 7, "geography outputs do not contain seven tables")
    identity_inputs = {
        "geography_contract_sha256": geography_contract_sha256,
        "input_staging_build_identity": input_identity[0],
        "input_staging_manifest_sha256": input_identity[1],
        "code_commit": code_commit,
        "repository_clean": True,
        "requirements_lock_sha256": requirements_lock_sha256,
        "environment": environment,
    }
    checkpoint_identity = sha256_json(identity_inputs)
    output_directory = output_root / checkpoint_identity
    _require(not output_directory.exists(), "geography checkpoint output already exists")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".{checkpoint_identity}.tmp-{uuid4().hex}"
    temporary.mkdir()
    try:
        tables_directory = temporary / "tables"
        tables_directory.mkdir()
        table_entries: list[dict[str, Any]] = []
        for definition in definitions:
            artifact_id = definition["artifact_id"]
            rows = definition["rows"]
            columns = definition["columns"]
            _validate_rows(artifact_id, rows, columns)
            artifact = tables_directory / f"{artifact_id}.parquet"
            physical = _write_parquet(artifact, rows, columns)
            table_entries.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_kind": definition["artifact_kind"],
                    "source_table_id": definition["source_table_id"],
                    "relative_path": f"tables/{artifact_id}.parquet",
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "columns": columns,
                    "logical_schema_sha256": sha256_json(columns),
                    "physical_columns": physical,
                    "physical_schema_sha256": sha256_json(physical),
                    "schema_sha256": sha256_json({"logical_columns": columns, "physical_columns": physical}),
                    "canonical_content_sha256": sha256_json(rows),
                    "artifact_sha256": sha256_file(artifact),
                    "artifact_bytes": artifact.stat().st_size,
                    "mapping_counts": None if definition["artifact_kind"] == "COUNTY_REFERENCE" else _mapping_counts(rows),
                }
            )
        _require(input_identity_probe() == input_identity, "input staging evidence changed during checkpoint build")
        manifest = {
            "schema_version": "1.0.0",
            "manifest_type": "COUNTY_GEOGRAPHY_RECONCILIATION_CHECKPOINT",
            "status": "VALID",
            "checkpoint_identity_algorithm": "SHA256_CANONICAL_GEOGRAPHY_INPUTS_V1",
            "checkpoint_identity": checkpoint_identity,
            "checkpoint_identity_inputs": identity_inputs,
            "content_hash_algorithm": "SHA256_CANONICAL_TYPED_ROWS_V1",
            "schema_hash_algorithm": "SHA256_CANONICAL_LOGICAL_AND_PHYSICAL_SCHEMA_V1",
            "artifact_hash_algorithm": "SHA256_FILE_BYTES",
            "parquet_hash_portability": "LOCAL_BINARY_EXACT_NOT_CROSS_PLATFORM_GUARANTEED",
            "table_count": len(table_entries),
            "total_row_count": sum(item["row_count"] for item in table_entries),
            "tables": table_entries,
        }
        validate_geography_checkpoint_manifest(manifest, manifest_schema, contract, geography_contract_sha256)
        manifest_path = temporary / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        verify_geography_checkpoint_artifacts(temporary, manifest, manifest_schema, contract, geography_contract_sha256)
        try:
            final_commit = capture_repository_identity(repository_root)
        except StagingBuildError as error:
            raise GeographyCheckpointError(str(error)) from error
        _require(final_commit == code_commit, "repository identity changed during checkpoint build")
        os.replace(temporary, output_directory)
        return output_directory, manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
