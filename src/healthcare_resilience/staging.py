"""Source-preserving staging extraction for already-opened source rows."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any


class StagingExtractionError(ValueError):
    """Raised when an input row cannot satisfy the staging contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StagingExtractionError(message)


def _is_empty_source_cell(value: Any) -> bool:
    return value is None or value == ""


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if not isinstance(value, str):
        raise ValueError("value is not a datetime")

    text = value.strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for pattern in (
        "%Y/%m/%d",
        "%Y/%m/%d %H:%M:%S",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    raise ValueError("unsupported datetime text")


def _parse_value(value: Any, parser_type: str) -> Any:
    if parser_type == "STRING":
        if not isinstance(value, str):
            raise ValueError("value is not text")
        return value

    if parser_type == "INTEGER":
        if isinstance(value, bool):
            raise ValueError("boolean is not an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                raise ValueError("value is not an integer")
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        raise ValueError("value is not an integer")

    if parser_type == "NUMBER":
        if isinstance(value, bool):
            raise ValueError("boolean is not a number")
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as error:
            raise ValueError("value is not numeric") from error
        if not parsed.is_finite():
            raise ValueError("number is not finite")
        return parsed

    if parser_type == "DATETIME":
        return _parse_datetime(value)

    raise ValueError(f"unsupported parser type {parser_type}")


def extract_staging_rows(
    source_rows: Iterable[Mapping[str, Any]],
    staging_table: Mapping[str, Any],
    source_table: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project retained columns without filtering, sorting, or deduplication.

    The caller remains responsible for opening the source file according to its
    source-table contract. This boundary accepts mappings so synthetic tests can
    exercise staging behavior without any private data or file parser.
    """

    staging_id = str(staging_table["id"])
    _require(
        staging_table["source_table_id"] == source_table["id"],
        f"{staging_id}: source-table identity mismatch",
    )
    _require(
        staging_table["expected_source_row_count"]
        == staging_table["expected_staging_row_count"]
        == source_table["data_row_count"],
        f"{staging_id}: row-count contract does not preserve all source rows",
    )
    _require(
        staging_table["semantic_key"]["columns"]
        == source_table["record_key"]["columns"],
        f"{staging_id}: semantic key differs from source-table contract",
    )

    columns = source_table["required_columns"]
    column_names = [column["name"] for column in columns]
    _require(
        "source_row_number" not in column_names,
        f"{staging_id}: source column collides with lineage column",
    )

    staged_rows: list[dict[str, Any]] = []
    for source_row_number, source_row in enumerate(source_rows, start=1):
        _require(
            isinstance(source_row, Mapping),
            f"{staging_id}: source row {source_row_number} is not a mapping",
        )
        output: dict[str, Any] = {"source_row_number": source_row_number}
        for column in columns:
            name = column["name"]
            _require(
                name in source_row,
                f"{staging_id}: source row {source_row_number} is missing column {name}",
            )
            value = source_row[name]
            if _is_empty_source_cell(value):
                _require(
                    column["null_allowed"],
                    f"{staging_id}: source row {source_row_number} has forbidden null in {name}",
                )
                output[name] = None
                continue
            try:
                output[name] = _parse_value(value, column["parser_type"])
            except (TypeError, ValueError) as error:
                raise StagingExtractionError(
                    f"{staging_id}: source row {source_row_number} cannot parse "
                    f"{name} as {column['parser_type']}: {error}"
                ) from error
        staged_rows.append(output)

    _require(
        len(staged_rows) == staging_table["expected_source_row_count"],
        f"{staging_id}: source-to-staging row-count mismatch; expected "
        f"{staging_table['expected_source_row_count']}, observed {len(staged_rows)}",
    )
    return staged_rows
