from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import (
    ContractError,
    load_json,
    validate_observed_table_profile,
    validate_schema,
    validate_source_table_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"


def synthetic_contract() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_source_table_contract.json")


def synthetic_profile() -> dict:
    return load_json(FIXTURE_DIR / "synthetic_source_table_profile.json")


def test_accepted_source_table_contract_is_valid() -> None:
    validate_source_table_contract(
        load_json(CONFIG_DIR / "source_tables.json"),
        load_json(CONFIG_DIR / "source_tables.schema.json"),
        load_json(CONFIG_DIR / "sources.json"),
    )


def test_synthetic_table_profile_matches_contract() -> None:
    contract = synthetic_contract()
    profile = synthetic_profile()
    validate_source_table_contract(
        contract,
        load_json(CONFIG_DIR / "source_tables.schema.json"),
        enforce_accepted_tables=False,
    )
    validate_schema(
        profile,
        load_json(CONFIG_DIR / "source_table_profile.schema.json"),
        "synthetic source-table profile",
    )
    validate_observed_table_profile(
        contract,
        profile,
        expected_source_contract_sha256="2" * 64,
        expected_source_table_contract_sha256="3" * 64,
    )


@pytest.mark.parametrize(
    ("field", "changed_value", "message"),
    [
        ("encoding", "WINDOWS-1252", "encoding differs"),
        ("data_row_count", 4, "data_row_count differs"),
        ("named_column_count", 3, "named_column_count differs"),
        (
            "header_sha256",
            "2" * 64,
            "header_sha256 differs",
        ),
        (
            "exact_duplicate_rows_beyond_first",
            1,
            "exact_duplicate_rows_beyond_first differs",
        ),
    ],
)
def test_profile_rejects_structural_drift(
    field: str, changed_value: object, message: str
) -> None:
    profile = synthetic_profile()
    profile["tables"][0][field] = changed_value
    with pytest.raises(ContractError, match=message):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_profile_rejects_missing_sheet() -> None:
    profile = synthetic_profile()
    profile["tables"].pop()
    profile["table_count"] = 1
    with pytest.raises(ContractError, match="missing or unexpected table"):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_profile_rejects_csv_dialect_drift() -> None:
    profile = synthetic_profile()
    profile["tables"][0]["csv_dialect"]["line_ending"] = "CRLF"
    with pytest.raises(ContractError, match="csv_dialect differs"):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_profile_rejects_missing_required_column() -> None:
    profile = synthetic_profile()
    del profile["tables"][0]["required_column_types"]["amount"]
    with pytest.raises(ContractError, match="column names or types"):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_profile_rejects_required_column_type_drift() -> None:
    profile = synthetic_profile()
    profile["tables"][0]["required_column_types"]["amount"] = "STRING"
    with pytest.raises(ContractError, match="column names or types"):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_profile_rejects_key_cardinality_drift() -> None:
    profile = synthetic_profile()
    profile["tables"][0]["record_key_evidence"]["distinct_count"] = 2
    with pytest.raises(ContractError, match="record-key evidence"):
        validate_observed_table_profile(synthetic_contract(), profile)


def test_contract_rejects_unique_key_with_duplicates() -> None:
    contract = deepcopy(synthetic_contract())
    key = contract["table_contracts"][0]["record_key"]
    key["expected_distinct_count"] = 2
    key["expected_duplicate_rows_beyond_first"] = 1
    with pytest.raises(ContractError, match="unique key has duplicates"):
        validate_source_table_contract(
            contract,
            load_json(CONFIG_DIR / "source_tables.schema.json"),
            enforce_accepted_tables=False,
        )
