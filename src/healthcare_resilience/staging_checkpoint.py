"""Atomic Parquet checkpoints and deterministic manifests for staging rows."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from .contracts import validate_schema
from .hashing import sha256_file, sha256_json

MANIFEST_FILENAME = "staging_checkpoint_manifest.json"


class StagingCheckpointError(ValueError):
    """Raised when a staging checkpoint would violate its contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StagingCheckpointError(message)


def _table_columns(source_table: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": "source_row_number",
            "output_type": "INTEGER",
            "null_allowed": False,
        },
        *[
            {
                "name": column["name"],
                "output_type": column["parser_type"],
                "null_allowed": column["null_allowed"],
            }
            for column in source_table["required_columns"]
        ],
    ]


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, Decimal):
        normalized = format(value.normalize(), "f")
        if Decimal(normalized) == 0:
            normalized = "0"
        return {"decimal": normalized}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"datetime": datetime.combine(value, datetime.min.time()).isoformat()}
    raise StagingCheckpointError(
        f"unsupported canonical staging value type {type(value).__name__}"
    )


def _canonical_content_hash(
    rows: Sequence[Mapping[str, Any]], columns: list[dict[str, Any]]
) -> str:
    names = [column["name"] for column in columns]
    payload = {
        "columns": names,
        "rows": [
            [_canonical_value(row[name]) for name in names]
            for row in rows
        ],
    }
    return sha256_json(payload)


def _validate_staging_rows(
    rows: Sequence[Mapping[str, Any]],
    staging_table: Mapping[str, Any],
    columns: list[dict[str, Any]],
) -> None:
    table_id = staging_table["id"]
    expected_names = [column["name"] for column in columns]
    _require(
        len(rows) == staging_table["expected_staging_row_count"],
        f"{table_id}: checkpoint row count differs from staging contract",
    )
    for expected_row_number, row in enumerate(rows, start=1):
        _require(
            list(row) == expected_names,
            f"{table_id}: row {expected_row_number} columns or order differ",
        )
        _require(
            row["source_row_number"] == expected_row_number,
            f"{table_id}: source row lineage is not consecutive",
        )
        for column in columns:
            name = column["name"]
            value = row[name]
            if value is None:
                _require(
                    column["null_allowed"],
                    f"{table_id}: row {expected_row_number} has forbidden null in {name}",
                )
                continue
            output_type = column["output_type"]
            if output_type == "STRING":
                valid = isinstance(value, str)
            elif output_type == "INTEGER":
                valid = type(value) is int
            elif output_type == "NUMBER":
                valid = isinstance(value, Decimal) and value.is_finite()
            elif output_type == "DATETIME":
                valid = isinstance(value, datetime)
            else:
                raise StagingCheckpointError(
                    f"{table_id}: unsupported logical type {output_type} for {name}"
                )
            _require(
                valid,
                f"{table_id}: row {expected_row_number} has invalid "
                f"{output_type} value in {name}",
            )


def _quoted_identifier(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def _decimal_type(values: Sequence[Any]) -> str:
    maximum_integer_digits = 0
    maximum_scale = 0
    found_value = False
    for value in values:
        if value is None:
            continue
        _require(isinstance(value, Decimal), "NUMBER column contains a non-Decimal")
        found_value = True
        _, digits, exponent = value.as_tuple()
        scale = max(-exponent, 0)
        integer_digits = max(len(digits) - scale, 0) + max(exponent, 0)
        maximum_integer_digits = max(maximum_integer_digits, integer_digits)
        maximum_scale = max(maximum_scale, scale)
    if not found_value:
        return "DECIMAL(38,18)"
    precision = max(1, maximum_integer_digits + maximum_scale)
    _require(precision <= 38, "NUMBER column exceeds DuckDB DECIMAL precision")
    return f"DECIMAL({precision},{maximum_scale})"


def _duckdb_type(
    column: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> str:
    output_type = column["output_type"]
    if output_type == "STRING":
        return "VARCHAR"
    if output_type == "INTEGER":
        return "BIGINT"
    if output_type == "DATETIME":
        return "TIMESTAMP"
    if output_type == "NUMBER":
        return _decimal_type([row[column["name"]] for row in rows])
    raise StagingCheckpointError(f"unsupported checkpoint type {output_type}")


def _physical_columns(relation: duckdb.DuckDBPyRelation) -> list[dict[str, str]]:
    return [
        {"name": name, "duckdb_type": str(data_type)}
        for name, data_type in zip(relation.columns, relation.types)
    ]


def _physical_type_matches_logical(logical_type: str, physical_type: str) -> bool:
    exact = {
        "STRING": "VARCHAR",
        "INTEGER": "BIGINT",
        "DATETIME": "TIMESTAMP",
    }
    if logical_type in exact:
        return physical_type == exact[logical_type]
    if logical_type != "NUMBER":
        return False
    match = re.fullmatch(r"DECIMAL\((\d+),(\d+)\)", physical_type)
    if match is None:
        return False
    precision, scale = (int(value) for value in match.groups())
    return 1 <= precision <= 38 and 0 <= scale <= precision


def _write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: list[dict[str, Any]],
    expected_content_sha256: str,
) -> list[dict[str, str]]:
    names = [column["name"] for column in columns]
    connection = duckdb.connect(database=":memory:")
    try:
        expected_physical_columns = [
            {
                "name": column["name"],
                "duckdb_type": _duckdb_type(column, rows),
            }
            for column in columns
        ]
        definitions = ", ".join(
            f"{_quoted_identifier(column['name'])} {column['duckdb_type']}"
            for column in expected_physical_columns
        )
        connection.execute(f"CREATE TABLE staging_data ({definitions})")
        placeholders = ", ".join("?" for _ in names)
        connection.executemany(
            f"INSERT INTO staging_data VALUES ({placeholders})",
            [[row[name] for name in names] for row in rows],
        )
        relation = connection.table("staging_data")
        relation.write_parquet(str(path), compression="zstd")
        observed = connection.read_parquet(str(path))
        _require(observed.columns == names, f"{path.name}: Parquet columns changed")
        observed_physical_columns = _physical_columns(observed)
        _require(
            observed_physical_columns == expected_physical_columns,
            f"{path.name}: Parquet physical schema changed",
        )
        observed_count = observed.aggregate("count(*) AS row_count").fetchone()[0]
        _require(
            observed_count == len(rows),
            f"{path.name}: Parquet row count differs after writing",
        )
        observed_values = observed.order('"source_row_number"').fetchall()
        observed_rows = [dict(zip(names, values)) for values in observed_values]
        _require(
            _canonical_content_hash(observed_rows, columns)
            == expected_content_sha256,
            f"{path.name}: Parquet values differ after writing",
        )
        return observed_physical_columns
    finally:
        connection.close()


def validate_staging_checkpoint_manifest(
    manifest: dict[str, Any],
    manifest_schema: dict[str, Any],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    expected_source_contract_sha256: str,
    expected_staging_contract_sha256: str,
) -> None:
    """Validate manifest lineage, table order, counts, and schema fingerprints."""

    validate_schema(manifest, manifest_schema, "staging checkpoint manifest")
    _require(
        manifest["source_snapshot_id"] == staging_contract["source_snapshot_id"],
        "checkpoint manifest references a different source snapshot",
    )
    _require(
        manifest["source_contract_sha256"] == expected_source_contract_sha256,
        "checkpoint manifest references a different source contract",
    )
    _require(
        manifest["source_table_contract_sha256"]
        == staging_contract["source_table_contract_sha256"],
        "checkpoint manifest references a different source-table contract",
    )
    _require(
        manifest["staging_table_contract_sha256"]
        == expected_staging_contract_sha256,
        "checkpoint manifest references a different staging contract",
    )

    staging_tables = staging_contract["staging_tables"]
    source_tables = {
        item["id"]: item for item in source_table_contract["table_contracts"]
    }
    _require(
        manifest["table_count"] == len(staging_tables) == len(manifest["tables"]),
        "checkpoint manifest table count is inconsistent",
    )
    expected_total = sum(
        item["expected_staging_row_count"] for item in staging_tables
    )
    _require(
        manifest["total_row_count"] == expected_total,
        "checkpoint manifest total row count differs from staging contract",
    )

    for observed, staging_table in zip(manifest["tables"], staging_tables):
        source_table = source_tables[staging_table["source_table_id"]]
        columns = _table_columns(source_table)
        table_id = staging_table["id"]
        _require(
            observed["staging_table_id"] == table_id
            and observed["source_table_id"] == source_table["id"],
            f"{table_id}: checkpoint table identity differs",
        )
        _require(
            observed["relative_path"] == f"tables/{table_id}.parquet",
            f"{table_id}: checkpoint relative path differs",
        )
        _require(
            observed["row_count"] == staging_table["expected_staging_row_count"],
            f"{table_id}: checkpoint row count differs",
        )
        _require(
            observed["column_count"] == len(columns)
            and observed["columns"] == columns,
            f"{table_id}: checkpoint columns differ",
        )
        _require(
            observed["logical_schema_sha256"] == sha256_json(columns),
            f"{table_id}: checkpoint logical schema hash differs",
        )
        physical_columns = observed["physical_columns"]
        _require(
            len(physical_columns) == len(columns)
            and [item["name"] for item in physical_columns]
            == [item["name"] for item in columns],
            f"{table_id}: checkpoint physical columns differ",
        )
        _require(
            all(
                _physical_type_matches_logical(
                    logical["output_type"], physical["duckdb_type"]
                )
                for logical, physical in zip(columns, physical_columns)
            ),
            f"{table_id}: checkpoint physical types are incompatible with logical schema",
        )
        _require(
            observed["physical_schema_sha256"] == sha256_json(physical_columns),
            f"{table_id}: checkpoint physical schema hash differs",
        )
        _require(
            observed["schema_sha256"]
            == sha256_json(
                {
                    "logical_columns": columns,
                    "physical_columns": physical_columns,
                }
            ),
            f"{table_id}: checkpoint combined schema hash differs",
        )


def verify_staging_checkpoint_artifacts(
    checkpoint_directory: Path,
    manifest: dict[str, Any],
    manifest_schema: dict[str, Any],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    expected_source_contract_sha256: str,
    expected_staging_contract_sha256: str,
) -> None:
    """Independently verify exact files, schemas, lineage, and decoded values."""

    _require(checkpoint_directory.is_dir(), "checkpoint directory is missing")
    validate_staging_checkpoint_manifest(
        manifest,
        manifest_schema,
        staging_contract,
        source_table_contract,
        expected_source_contract_sha256,
        expected_staging_contract_sha256,
    )
    manifest_path = checkpoint_directory / MANIFEST_FILENAME
    try:
        stored_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StagingCheckpointError("checkpoint manifest cannot be read") from error
    _require(
        stored_manifest == manifest,
        "checkpoint manifest file differs from the validated manifest",
    )
    expected_files = {MANIFEST_FILENAME}
    expected_files.update(item["relative_path"] for item in manifest["tables"])
    observed_files = {
        path.relative_to(checkpoint_directory).as_posix()
        for path in checkpoint_directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    _require(
        observed_files == expected_files,
        "checkpoint directory contains missing or unexpected files",
    )
    _require(
        not any(path.is_symlink() for path in checkpoint_directory.rglob("*")),
        "checkpoint directory contains a symbolic link",
    )
    staging_tables = {
        item["id"]: item for item in staging_contract["staging_tables"]
    }
    source_tables = {
        item["id"]: item for item in source_table_contract["table_contracts"]
    }
    connection = duckdb.connect(database=":memory:")
    try:
        for table in manifest["tables"]:
            table_id = table["staging_table_id"]
            path = checkpoint_directory / Path(table["relative_path"])
            _require(
                path.stat().st_size == table["artifact_bytes"],
                f"{table_id}: artifact byte count differs",
            )
            _require(
                sha256_file(path) == table["artifact_sha256"],
                f"{table_id}: artifact hash differs",
            )

            staging_table = staging_tables[table_id]
            source_table = source_tables[staging_table["source_table_id"]]
            columns = _table_columns(source_table)
            names = [column["name"] for column in columns]
            try:
                observed = connection.read_parquet(str(path))
                observed_physical_columns = _physical_columns(observed)
                observed_values = observed.fetchall()
            except (duckdb.Error, OSError) as error:
                raise StagingCheckpointError(
                    f"{table_id}: Parquet artifact cannot be read"
                ) from error
            _require(
                observed.columns == names,
                f"{table_id}: Parquet columns differ from contract",
            )
            _require(
                observed_physical_columns == table["physical_columns"],
                f"{table_id}: Parquet physical schema differs from manifest",
            )
            _require(
                sha256_json(observed_physical_columns)
                == table["physical_schema_sha256"],
                f"{table_id}: Parquet physical schema hash differs",
            )
            observed_rows = [dict(zip(names, values)) for values in observed_values]
            _validate_staging_rows(observed_rows, staging_table, columns)
            _require(
                _canonical_content_hash(observed_rows, columns)
                == table["canonical_content_sha256"],
                f"{table_id}: canonical checkpoint content differs",
            )
    finally:
        connection.close()


def write_staging_checkpoint(
    output_directory: Path,
    rows_by_staging_table: Mapping[str, Sequence[Mapping[str, Any]]],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    source_contract_sha256: str,
    staging_contract_sha256: str,
    manifest_schema: dict[str, Any],
) -> dict[str, Any]:
    """Write a complete checkpoint directory and publish it by atomic rename."""

    _require(not output_directory.exists(), "checkpoint output already exists")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = output_directory.parent / (
        f".{output_directory.name}.tmp-{uuid4().hex}"
    )
    temporary_directory.mkdir()
    try:
        expected_ids = [item["id"] for item in staging_contract["staging_tables"]]
        _require(
            set(rows_by_staging_table) == set(expected_ids),
            "checkpoint rows do not cover the exact staging-table set",
        )
        source_tables = {
            item["id"]: item for item in source_table_contract["table_contracts"]
        }
        tables_directory = temporary_directory / "tables"
        tables_directory.mkdir()
        table_entries: list[dict[str, Any]] = []

        for staging_table in staging_contract["staging_tables"]:
            table_id = staging_table["id"]
            source_table = source_tables[staging_table["source_table_id"]]
            rows = rows_by_staging_table[table_id]
            columns = _table_columns(source_table)
            _validate_staging_rows(rows, staging_table, columns)
            artifact_path = tables_directory / f"{table_id}.parquet"
            canonical_content_sha256 = _canonical_content_hash(rows, columns)
            physical_columns = _write_parquet(
                artifact_path,
                rows,
                columns,
                canonical_content_sha256,
            )
            table_entries.append(
                {
                    "staging_table_id": table_id,
                    "source_table_id": source_table["id"],
                    "relative_path": f"tables/{table_id}.parquet",
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "columns": columns,
                    "logical_schema_sha256": sha256_json(columns),
                    "physical_columns": physical_columns,
                    "physical_schema_sha256": sha256_json(physical_columns),
                    "schema_sha256": sha256_json(
                        {
                            "logical_columns": columns,
                            "physical_columns": physical_columns,
                        }
                    ),
                    "canonical_content_sha256": canonical_content_sha256,
                    "artifact_sha256": sha256_file(artifact_path),
                    "artifact_bytes": artifact_path.stat().st_size,
                }
            )

        manifest = {
            "schema_version": "1.1.0",
            "manifest_type": "SOURCE_PRESERVING_STAGING_CHECKPOINT",
            "status": "VALID",
            "source_snapshot_id": staging_contract["source_snapshot_id"],
            "source_contract_sha256": source_contract_sha256,
            "source_table_contract_sha256": staging_contract[
                "source_table_contract_sha256"
            ],
            "staging_table_contract_sha256": staging_contract_sha256,
            "content_hash_algorithm": "SHA256_CANONICAL_TYPED_ROWS_V1",
            "schema_hash_algorithm": (
                "SHA256_CANONICAL_LOGICAL_AND_PHYSICAL_SCHEMA_V1"
            ),
            "artifact_hash_algorithm": "SHA256_FILE_BYTES",
            "parquet_hash_portability": (
                "LOCAL_BINARY_EXACT_NOT_CROSS_PLATFORM_GUARANTEED"
            ),
            "table_count": len(table_entries),
            "total_row_count": sum(item["row_count"] for item in table_entries),
            "tables": table_entries,
        }
        validate_staging_checkpoint_manifest(
            manifest,
            manifest_schema,
            staging_contract,
            source_table_contract,
            source_contract_sha256,
            staging_contract_sha256,
        )
        manifest_path = temporary_directory / MANIFEST_FILENAME
        text = json.dumps(manifest, ensure_ascii=True, allow_nan=False, indent=2)
        manifest_path.write_text(f"{text}\n", encoding="utf-8", newline="\n")
        verify_staging_checkpoint_artifacts(
            temporary_directory,
            manifest,
            manifest_schema,
            staging_contract,
            source_table_contract,
            source_contract_sha256,
            staging_contract_sha256,
        )
        os.replace(temporary_directory, output_directory)
        return manifest
    except Exception:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
        raise
