"""Deterministic expansion of the accepted configuration contract."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any, Iterable

from .hashing import sha256_json


def _configuration(
    *,
    profile: dict[str, Any],
    mask_state: str,
    rate_state: str,
    capacity: int,
    medicare_threshold: int,
    hazard_context: str,
    hpsa_status_set: str,
    family: str,
    variant: str,
    tie_rule: str,
) -> dict[str, Any]:
    configuration_id = "__".join(
        [
            profile["name"],
            mask_state,
            rate_state,
            f"K{capacity}",
            f"T{medicare_threshold}",
            hazard_context,
            hpsa_status_set,
        ]
    )
    record = {
        "configuration_id": configuration_id,
        "family": family,
        "variant": variant,
        "is_primary": family == "PRIMARY",
        "profile": profile["name"],
        "weights": dict(profile["weights"]),
        "mask_state": mask_state,
        "rate_state": rate_state,
        "capacity": capacity,
        "medicare_threshold": medicare_threshold,
        "hazard_context": hazard_context,
        "hpsa_status_set": hpsa_status_set,
        "tie_rule": tie_rule,
    }
    return {
        "configuration_id": configuration_id,
        "configuration_sha256": sha256_json(record),
        **{key: value for key, value in record.items() if key != "configuration_id"},
    }


def _corner_records(
    method: dict[str, Any],
    *,
    capacity: int,
    medicare_threshold: int,
    hazard_context: str,
    hpsa_status_set: str,
    family: str,
    variant: str,
) -> Iterable[dict[str, Any]]:
    mask_states = method["uncertainty_axes"]["mask_states"]
    rate_states = method["uncertainty_axes"]["rate_states"]
    tie_rule = method["selection"]["boundary_tie_rule"]
    for profile, mask, rate in product(
        method["preference_profiles"], mask_states, rate_states
    ):
        yield _configuration(
            profile=profile,
            mask_state=mask["id"],
            rate_state=rate["id"],
            capacity=capacity,
            medicare_threshold=medicare_threshold,
            hazard_context=hazard_context,
            hpsa_status_set=hpsa_status_set,
            family=family,
            variant=variant,
            tie_rule=tie_rule,
        )


def build_configuration_manifest(
    method: dict[str, Any], method_contract_sha256: str
) -> dict[str, Any]:
    """Expand the five accepted one-factor families in their declared order."""

    primary = method["primary"]
    sensitivities = method["sensitivities"]
    configurations: list[dict[str, Any]] = []

    configurations.extend(
        _corner_records(
            method,
            capacity=primary["capacity"],
            medicare_threshold=primary["medicare_threshold"],
            hazard_context=primary["hazard_context"],
            hpsa_status_set=primary["hpsa_status_set"],
            family="PRIMARY",
            variant="PRIMARY",
        )
    )
    for capacity in sensitivities["capacities"]:
        configurations.extend(
            _corner_records(
                method,
                capacity=capacity,
                medicare_threshold=primary["medicare_threshold"],
                hazard_context=primary["hazard_context"],
                hpsa_status_set=primary["hpsa_status_set"],
                family="CAPACITY",
                variant=f"K{capacity}",
            )
        )
    for threshold in sensitivities["medicare_thresholds"]:
        configurations.extend(
            _corner_records(
                method,
                capacity=primary["capacity"],
                medicare_threshold=threshold,
                hazard_context=primary["hazard_context"],
                hpsa_status_set=primary["hpsa_status_set"],
                family="MEDICARE_THRESHOLD",
                variant=f"T{threshold}",
            )
        )
    for status_set in sensitivities["hpsa_status_sets"]:
        configurations.extend(
            _corner_records(
                method,
                capacity=primary["capacity"],
                medicare_threshold=primary["medicare_threshold"],
                hazard_context=primary["hazard_context"],
                hpsa_status_set=status_set,
                family="HPSA_STATUS",
                variant=status_set,
            )
        )
    for hazard_code in sensitivities["hazard_codes"]:
        configurations.extend(
            _corner_records(
                method,
                capacity=primary["capacity"],
                medicare_threshold=primary["medicare_threshold"],
                hazard_context=hazard_code,
                hpsa_status_set=primary["hpsa_status_set"],
                family="HAZARD_SPECIFIC",
                variant=hazard_code,
            )
        )

    return {
        "schema_version": "1.0.0",
        "method_contract_sha256": method_contract_sha256,
        "method_specification_sha256": method["method_specification"]["sha256"],
        "configuration_count": len(configurations),
        "primary_configuration_count": sum(
            item["is_primary"] for item in configurations
        ),
        "configurations": configurations,
    }


def write_json_document(path: Path, value: dict[str, Any]) -> None:
    """Write stable, human-readable JSON with a final newline."""

    text = json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2)
    path.write_text(f"{text}\n", encoding="utf-8", newline="\n")
