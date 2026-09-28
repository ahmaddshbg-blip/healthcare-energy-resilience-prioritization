from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import (
    ContractError,
    load_json,
    validate_method_contract,
    validate_repository_contracts,
    validate_source_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"


def test_repository_contracts_are_valid() -> None:
    summary = validate_repository_contracts(ROOT)
    assert summary["configuration_count"] == 480
    assert summary["primary_configuration_count"] == 20


def test_synthetic_source_contract_has_no_private_dependency() -> None:
    source_contract = load_json(
        ROOT / "tests" / "fixtures" / "synthetic_source_contract.json"
    )
    source_schema = load_json(CONFIG_DIR / "sources.schema.json")
    validate_source_contract(
        source_contract, source_schema, enforce_accepted_snapshot=False
    )


def test_source_snapshot_identity_rejects_a_changed_file_size() -> None:
    source_contract = load_json(
        ROOT / "tests" / "fixtures" / "synthetic_source_contract.json"
    )
    source_schema = load_json(CONFIG_DIR / "sources.schema.json")
    source_contract["source_files"][0]["bytes"] += 1
    with pytest.raises(ContractError, match="snapshot_id"):
        validate_source_contract(
            source_contract, source_schema, enforce_accepted_snapshot=False
        )


def test_method_contract_rejects_weight_drift() -> None:
    method = deepcopy(load_json(CONFIG_DIR / "method.json"))
    method_schema = load_json(CONFIG_DIR / "method.schema.json")
    method["preference_profiles"][0]["weights"]["C_COUNT"] = 0.25
    with pytest.raises(ContractError, match="weights changed"):
        validate_method_contract(method, method_schema)
