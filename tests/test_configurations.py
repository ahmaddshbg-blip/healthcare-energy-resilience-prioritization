from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.configurations import build_configuration_manifest
from healthcare_resilience.contracts import (
    ContractError,
    load_json,
    validate_configuration_manifest,
)
from healthcare_resilience.hashing import sha256_file

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"


def _generated_manifest() -> tuple[dict, dict, str]:
    method = load_json(CONFIG_DIR / "method.json")
    method_hash = sha256_file(CONFIG_DIR / "method.json")
    return build_configuration_manifest(method, method_hash), method, method_hash


def test_configuration_generation_is_deterministic() -> None:
    first, _, _ = _generated_manifest()
    second, _, _ = _generated_manifest()
    assert first == second


def test_configuration_families_have_accepted_counts() -> None:
    manifest, _, _ = _generated_manifest()
    counts = Counter(item["family"] for item in manifest["configurations"])
    assert counts == {
        "PRIMARY": 20,
        "CAPACITY": 40,
        "MEDICARE_THRESHOLD": 40,
        "HPSA_STATUS": 20,
        "HAZARD_SPECIFIC": 360,
    }
    assert len({item["configuration_id"] for item in manifest["configurations"]}) == 480


def test_primary_identifier_is_content_based() -> None:
    manifest, _, _ = _generated_manifest()
    assert manifest["configurations"][0]["configuration_id"] == (
        "BALANCED__MASK_LOWER__RATE_LOWER__K25__T1000__ALL_HAZARD__DESIGNATED"
    )


def test_configuration_hash_rejects_parameter_tampering() -> None:
    manifest, method, method_hash = _generated_manifest()
    changed = deepcopy(manifest)
    changed["configurations"][0]["capacity"] = 24
    schema = load_json(CONFIG_DIR / "configurations.schema.json")
    with pytest.raises(ContractError, match="configuration hash mismatch"):
        validate_configuration_manifest(changed, schema, method, method_hash)
