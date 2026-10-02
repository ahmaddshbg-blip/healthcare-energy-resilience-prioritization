from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from healthcare_resilience.contracts import (
    ContractError,
    load_json,
    validate_staging_contract,
)
from healthcare_resilience.hashing import sha256_file
from healthcare_resilience.staging import (
    StagingExtractionError,
    extract_staging_rows,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"


def synthetic_source_tables() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_source_table_contract.json")


def synthetic_staging() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_staging_contract.json")


def table_by_id(contract: dict, table_id: str) -> dict:
    return next(item for item in contract["table_contracts"] if item["id"] == table_id)


def stage_by_source(contract: dict, source_id: str) -> dict:
    return next(
        item for item in contract["staging_tables"]
        if item["source_table_id"] == source_id
    )


def test_accepted_staging_contract_is_valid() -> None:
    source_tables = load_json(CONFIG_DIR / "source_tables.json")
    validate_staging_contract(
        load_json(CONFIG_DIR / "staging_tables.json"),
        load_json(CONFIG_DIR / "staging_tables.schema.json"),
        source_tables,
        sha256_file(CONFIG_DIR / "source_tables.json"),
    )


def test_synthetic_staging_contract_is_valid() -> None:
    source_tables = synthetic_source_tables()
    validate_staging_contract(
        synthetic_staging(),
        load_json(CONFIG_DIR / "staging_tables.schema.json"),
        source_tables,
        sha256_file(FIXTURE_DIR / "synthetic_source_table_contract.json"),
        enforce_accepted_tables=False,
    )


def test_extraction_preserves_order_strings_masked_value_and_null() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"unit_id": "01001", "amount": "11", "ignored": "not retained"},
        {"unit_id": " 02020 ", "amount": ""},
        {"unit_id": "03030", "amount": "4.50"},
    ]

    result = extract_staging_rows(
        rows,
        stage_by_source(staging_contract, "synthetic_measurements"),
        table_by_id(source_contract, "synthetic_measurements"),
    )

    assert [row["source_row_number"] for row in result] == [1, 2, 3]
    assert result[0] == {
        "source_row_number": 1,
        "unit_id": "01001",
        "amount": Decimal("11"),
    }
    assert result[1]["unit_id"] == " 02020 "
    assert result[1]["amount"] is None
    assert result[2]["amount"] == Decimal("4.50")


def test_extraction_preserves_repeated_identifiers_and_rows() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"region_id": "R-01", "label": "Not Applicable"},
        {"region_id": "R-01", "label": "Not Applicable"},
    ]

    result = extract_staging_rows(
        rows,
        stage_by_source(staging_contract, "synthetic_regions"),
        table_by_id(source_contract, "synthetic_regions"),
    )

    assert len(result) == 2
    assert result[0]["region_id"] == result[1]["region_id"] == "R-01"
    assert result[0]["label"] == result[1]["label"] == "Not Applicable"
    assert [row["source_row_number"] for row in result] == [1, 2]


def test_extraction_parses_integer_and_datetime_without_semantic_changes() -> None:
    source_table = {
        "id": "synthetic_typed",
        "data_row_count": 1,
        "required_columns": [
            {"name": "record_id", "parser_type": "STRING", "null_allowed": False},
            {"name": "count", "parser_type": "INTEGER", "null_allowed": False},
            {"name": "created_at", "parser_type": "DATETIME", "null_allowed": False},
        ],
        "record_key": {"columns": ["record_id"]},
    }
    staging_table = {
        "id": "stg_synthetic_typed",
        "source_table_id": "synthetic_typed",
        "expected_source_row_count": 1,
        "expected_staging_row_count": 1,
        "semantic_key": {"columns": ["record_id"]},
    }

    result = extract_staging_rows(
        [{"record_id": "001", "count": "11", "created_at": "2026-09-29"}],
        staging_table,
        source_table,
    )

    assert result[0]["record_id"] == "001"
    assert result[0]["count"] == 11
    assert result[0]["created_at"] == datetime(2026, 9, 29)


def test_extraction_rejects_missing_retained_column() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"unit_id": "A", "amount": "1"},
        {"unit_id": "B", "amount": "2"},
        {"unit_id": "C"},
    ]
    with pytest.raises(StagingExtractionError, match="missing column amount"):
        extract_staging_rows(
            rows,
            stage_by_source(staging_contract, "synthetic_measurements"),
            table_by_id(source_contract, "synthetic_measurements"),
        )


def test_extraction_rejects_forbidden_null() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"unit_id": "A", "amount": "1"},
        {"unit_id": "", "amount": "2"},
        {"unit_id": "C", "amount": "3"},
    ]
    with pytest.raises(StagingExtractionError, match="forbidden null in unit_id"):
        extract_staging_rows(
            rows,
            stage_by_source(staging_contract, "synthetic_measurements"),
            table_by_id(source_contract, "synthetic_measurements"),
        )


def test_extraction_rejects_type_parse_failure() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"unit_id": "A", "amount": "1"},
        {"unit_id": "B", "amount": "not numeric"},
        {"unit_id": "C", "amount": "3"},
    ]
    with pytest.raises(StagingExtractionError, match="cannot parse amount as NUMBER"):
        extract_staging_rows(
            rows,
            stage_by_source(staging_contract, "synthetic_measurements"),
            table_by_id(source_contract, "synthetic_measurements"),
        )


def test_extraction_rejects_row_count_change() -> None:
    source_contract = synthetic_source_tables()
    staging_contract = synthetic_staging()
    rows = [
        {"unit_id": "A", "amount": "1"},
        {"unit_id": "B", "amount": "2"},
    ]
    with pytest.raises(StagingExtractionError, match="row-count mismatch"):
        extract_staging_rows(
            rows,
            stage_by_source(staging_contract, "synthetic_measurements"),
            table_by_id(source_contract, "synthetic_measurements"),
        )


def test_staging_contract_rejects_source_table_hash_drift() -> None:
    contract = deepcopy(synthetic_staging())
    contract["source_table_contract_sha256"] = "f" * 64
    with pytest.raises(ContractError, match="source-table contract hash"):
        validate_staging_contract(
            contract,
            load_json(CONFIG_DIR / "staging_tables.schema.json"),
            synthetic_source_tables(),
            sha256_file(FIXTURE_DIR / "synthetic_source_table_contract.json"),
            enforce_accepted_tables=False,
        )


def test_staging_contract_rejects_row_filtering() -> None:
    contract = deepcopy(synthetic_staging())
    contract["staging_tables"][0]["expected_staging_row_count"] = 2
    with pytest.raises(ContractError, match="preserve every row"):
        validate_staging_contract(
            contract,
            load_json(CONFIG_DIR / "staging_tables.schema.json"),
            synthetic_source_tables(),
            sha256_file(FIXTURE_DIR / "synthetic_source_table_contract.json"),
            enforce_accepted_tables=False,
        )
