"""Schema and semantic validation for the accepted project contracts."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .configurations import build_configuration_manifest
from .hashing import sha256_file, sha256_json, source_snapshot_identity

ACCEPTED_SOURCE_SNAPSHOT_ID = (
    "cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb"
)
ACCEPTED_METHOD_SPECIFICATION_SHA256 = (
    "3ab000d429a7d9bda38f0eab08caa38d54a4421fbffe7698213a1afa94d8ae16"
)

EXPECTED_CRITERIA = ("C_COUNT", "C_RATE", "C_HAZARD", "C_HPSA")
EXPECTED_CONTEXT_FIELDS = (
    "HRSA_HEALTH_CENTER_PERMANENT_SITE_PRESENCE",
    "HRSA_HEALTH_CENTER_SEASONAL_SITE_PRESENCE",
    "HRSA_HEALTH_CENTER_MOBILE_SITE_PRESENCE",
    "HRSA_HEALTH_CENTER_MISSING_FIPS_COUNT",
)
EXPECTED_PROFILE_WEIGHTS = {
    "BALANCED": {"C_COUNT": 0.24, "C_RATE": 0.16, "C_HAZARD": 0.40, "C_HPSA": 0.20},
    "BURDEN_MAGNITUDE": {"C_COUNT": 0.40, "C_RATE": 0.10, "C_HAZARD": 0.30, "C_HPSA": 0.20},
    "BURDEN_PREVALENCE": {"C_COUNT": 0.10, "C_RATE": 0.40, "C_HAZARD": 0.30, "C_HPSA": 0.20},
    "HAZARD_EMPHASIS": {"C_COUNT": 0.18, "C_RATE": 0.12, "C_HAZARD": 0.50, "C_HPSA": 0.20},
    "SHORTAGE_EMPHASIS": {"C_COUNT": 0.18, "C_RATE": 0.12, "C_HAZARD": 0.30, "C_HPSA": 0.40},
}
EXPECTED_HAZARD_CODES = (
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN", "ISTM",
    "LNDS", "LTNG", "IFLD", "SWND", "TRND", "TSUN", "VLCN", "WFIR", "WNTW",
)
EXPECTED_OUT_OF_SCOPE = (
    "02063", "02066", "09110", "09120", "09130", "09140", "09150", "09160",
    "09170", "09180", "09190",
)
EXPECTED_FAMILY_COUNTS = {
    "PRIMARY": 20,
    "CAPACITY": 40,
    "MEDICARE_THRESHOLD": 40,
    "HPSA_STATUS": 20,
    "HAZARD_SPECIFIC": 360,
}
EXPECTED_SOURCE_IDENTITY_ORDER = (
    "census_county_population_2025",
    "fema_nri_counties_layer_metadata",
    "fema_nri_counties_service_metadata",
    "fema_nri_counties",
    "fema_nri_item_metadata_json",
    "fema_nri_item_metadata_xml",
    "hhs_empower_2026_historical",
    "hhs_empower_county_layer_metadata",
    "hhs_empower_county_service_metadata",
    "hhs_empower_county",
    "hhs_empower_historical_dictionary",
    "hrsa_health_center_sites_metadata",
    "hrsa_health_center_sites",
    "hrsa_primary_care_hpsa_metadata",
    "hrsa_primary_care_hpsa",
)


class ContractError(ValueError):
    """Raised when a public contract violates a schema or accepted invariant."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate_schema(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: tuple(str(part) for part in error.path),
    )
    if not errors:
        return
    details = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        details.append(f"{location}: {error.message}")
    raise ContractError(f"{label} schema validation failed: " + "; ".join(details))


def validate_source_contract(
    source_contract: dict[str, Any],
    source_schema: dict[str, Any],
    *,
    enforce_accepted_snapshot: bool = True,
) -> None:
    validate_schema(source_contract, source_schema, "source contract")
    files = source_contract["source_files"]
    _require(
        source_contract["expected_file_count"] == len(files),
        "source expected_file_count does not match source_files",
    )
    _require(len({item["id"] for item in files}) == len(files), "source ids are not unique")
    _require(
        len({item["filename"] for item in files}) == len(files),
        "source filenames are not unique",
    )
    _require(
        all(item["required_for_frozen_reproduction"] for item in files),
        "every frozen source entry must be required for reproduction",
    )
    identity_order = source_contract["snapshot_identity_order"]
    _require(
        len(identity_order) == len(set(identity_order)),
        "source snapshot identity order contains duplicate ids",
    )
    _require(
        set(identity_order) == {item["id"] for item in files},
        "source snapshot identity order does not cover the exact file set",
    )
    files_by_id = {item["id"]: item for item in files}
    calculated_identity = source_snapshot_identity(
        [files_by_id[source_id] for source_id in identity_order]
    )
    _require(
        source_contract["snapshot_id"] == calculated_identity,
        "source snapshot_id does not match filename, byte-size, and SHA-256 identities",
    )
    if enforce_accepted_snapshot:
        _require(len(files) == 15, "accepted frozen source contract must contain 15 files")
        _require(
            tuple(identity_order) == EXPECTED_SOURCE_IDENTITY_ORDER,
            "source snapshot identity order differs from preservation evidence",
        )
        _require(
            source_contract["snapshot_id"] == ACCEPTED_SOURCE_SNAPSHOT_ID,
            "source contract is not the accepted frozen snapshot",
        )


def validate_method_contract(
    method: dict[str, Any], method_schema: dict[str, Any]
) -> None:
    validate_schema(method, method_schema, "method contract")
    _require(
        method["method_specification"]["sha256"]
        == ACCEPTED_METHOD_SPECIFICATION_SHA256,
        "method specification identity differs from the accepted precommitment",
    )

    universe = method["universe"]
    _require(universe["reference_count"] == 3144, "reference universe must contain 3,144 units")
    _require(universe["eligible_count"] == 3133, "eligible universe must contain 3,133 units")
    replacements = [
        (item["source_fips"], item["current_fips"])
        for item in universe["exact_fips_replacements"]
    ]
    _require(
        replacements == [("02270", "02158"), ("46113", "46102")],
        "geography replacements differ from the accepted exact mappings",
    )
    _require(
        tuple(universe["out_of_scope_fips"]) == EXPECTED_OUT_OF_SCOPE,
        "out-of-scope geography differs from the accepted 11-unit set",
    )

    criterion_ids = tuple(item["id"] for item in method["criteria"])
    _require(criterion_ids == EXPECTED_CRITERIA, "criteria or criterion order changed")
    _require(
        tuple(method["context_only_fields"]) == EXPECTED_CONTEXT_FIELDS,
        "context-only health-center fields changed",
    )
    _require(
        not set(criterion_ids).intersection(method["context_only_fields"]),
        "context-only fields cannot enter the primary value model",
    )

    profiles = method["preference_profiles"]
    _require(
        [profile["name"] for profile in profiles] == list(EXPECTED_PROFILE_WEIGHTS),
        "preference profiles or their order changed",
    )
    for profile in profiles:
        _require(
            profile["weights"] == EXPECTED_PROFILE_WEIGHTS[profile["name"]],
            f"weights changed for profile {profile['name']}",
        )
        _require(
            math.isclose(sum(profile["weights"].values()), 1.0, abs_tol=1e-12),
            f"weights do not sum to one for profile {profile['name']}",
        )

    axes = method["uncertainty_axes"]
    _require(
        [(item["id"], item["masked_dme_value"]) for item in axes["mask_states"]]
        == [("MASK_LOWER", 1), ("MASK_UPPER", 11)],
        "masked-count uncertainty bounds changed",
    )
    _require(
        [
            (item["id"], item["small_denominator_normalized_value"])
            for item in axes["rate_states"]
        ]
        == [("RATE_LOWER", 0.0), ("RATE_UPPER", 1.0)],
        "small-denominator uncertainty bounds changed",
    )

    hpsa = method["hpsa"]
    _require(
        hpsa["eligible_designation_types"]
        == ["Geographic HPSA", "High Needs Geographic HPSA", "HPSA Population"],
        "eligible HPSA designation types changed",
    )
    _require(
        hpsa["primary_status_set"]
        == {"id": "DESIGNATED", "statuses": ["Designated"]},
        "primary HPSA status set changed",
    )
    _require(
        hpsa["sensitivity_status_set"]
        == {
            "id": "DESIGNATED_PLUS_PROPOSED_FOR_WITHDRAWAL",
            "statuses": ["Designated", "Proposed For Withdrawal"],
        },
        "HPSA sensitivity status set changed",
    )

    primary = method["primary"]
    _require(
        primary
        == {
            "capacity": 25,
            "medicare_threshold": 1000,
            "hazard_context": "ALL_HAZARD",
            "hpsa_status_set": "DESIGNATED",
            "expected_configuration_count": 20,
        },
        "primary configuration settings changed",
    )
    sensitivities = method["sensitivities"]
    _require(sensitivities["capacities"] == [10, 50], "capacity sensitivities changed")
    _require(
        sensitivities["medicare_thresholds"] == [500, 2000],
        "Medicare-threshold sensitivities changed",
    )
    _require(
        sensitivities["hpsa_status_sets"]
        == ["DESIGNATED_PLUS_PROPOSED_FOR_WITHDRAWAL"],
        "HPSA status sensitivity changed",
    )
    _require(
        tuple(sensitivities["hazard_codes"]) == EXPECTED_HAZARD_CODES,
        "hazard-specific sensitivity set or order changed",
    )

    corner_count = len(profiles) * len(axes["mask_states"]) * len(axes["rate_states"])
    derived_counts = {
        "primary": corner_count,
        "capacity": corner_count * len(sensitivities["capacities"]),
        "medicare_threshold": corner_count * len(sensitivities["medicare_thresholds"]),
        "hpsa_status": corner_count * len(sensitivities["hpsa_status_sets"]),
        "hazard_specific": corner_count * len(sensitivities["hazard_codes"]),
    }
    derived_counts["total"] = sum(derived_counts.values())
    _require(
        method["configuration_counts"] == derived_counts,
        "declared configuration counts do not match the accepted Cartesian design",
    )


def validate_configuration_manifest(
    manifest: dict[str, Any],
    configuration_schema: dict[str, Any],
    method: dict[str, Any],
    method_contract_sha256: str,
) -> None:
    validate_schema(manifest, configuration_schema, "configuration manifest")
    _require(
        manifest["method_contract_sha256"] == method_contract_sha256,
        "configuration manifest references a different method contract",
    )
    configurations = manifest["configurations"]
    identifiers = [item["configuration_id"] for item in configurations]
    _require(len(set(identifiers)) == len(identifiers), "configuration ids are not unique")
    for item in configurations:
        payload = {key: value for key, value in item.items() if key != "configuration_sha256"}
        _require(
            item["configuration_sha256"] == sha256_json(payload),
            f"configuration hash mismatch for {item['configuration_id']}",
        )
    _require(
        Counter(item["family"] for item in configurations) == EXPECTED_FAMILY_COUNTS,
        "configuration family counts differ from 20/40/40/20/360",
    )
    expected = build_configuration_manifest(method, method_contract_sha256)
    _require(
        manifest == expected,
        "configuration manifest differs from deterministic expansion of method.json",
    )


def validate_repository_contracts(root: Path) -> dict[str, Any]:
    """Validate all public contracts and return their reproducible identities."""

    config_dir = root / "configs"
    sources = load_json(config_dir / "sources.json")
    method = load_json(config_dir / "method.json")
    configurations = load_json(config_dir / "configurations.json")
    validate_source_contract(sources, load_json(config_dir / "sources.schema.json"))
    validate_method_contract(method, load_json(config_dir / "method.schema.json"))
    method_hash = sha256_file(config_dir / "method.json")
    validate_configuration_manifest(
        configurations,
        load_json(config_dir / "configurations.schema.json"),
        method,
        method_hash,
    )
    return {
        "source_snapshot_id": sources["snapshot_id"],
        "source_contract_sha256": sha256_file(config_dir / "sources.json"),
        "method_contract_sha256": method_hash,
        "configuration_manifest_sha256": sha256_file(
            config_dir / "configurations.json"
        ),
        "configuration_count": configurations["configuration_count"],
        "primary_configuration_count": configurations["primary_configuration_count"],
    }
