"""Deterministic county-level source evidence without analytical scoring."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contracts import validate_schema
from .hashing import sha256_file, sha256_json

HAZARD_CODES = (
    "AVLN", "CFLD", "CWAV", "DRGT", "ERQK", "HAIL", "HWAV", "HRCN",
    "ISTM", "LNDS", "LTNG", "IFLD", "SWND", "TRND", "TSUN", "VLCN",
    "WFIR", "WNTW",
)
SOURCE_ROLE_IDS = (
    "stg_hhs_empower_county",
    "stg_fema_nri_counties",
    "stg_hrsa_primary_care_hpsa",
    "stg_hrsa_health_center_sites",
)
EXPECTED_FAILURE_CONDITIONS = (
    "CONTRACT_OR_INPUT_IDENTITY_MISMATCH",
    "MISSING_EXTRA_ALTERED_OR_SYMLINK_ARTIFACT",
    "REFERENCE_GRAIN_OR_SCOPE_MISMATCH",
    "MAP_TO_STAGING_LINEAGE_MISMATCH",
    "HHS_ELIGIBLE_COVERAGE_OR_VALUE_FAILURE",
    "FEMA_REFERENCE_COVERAGE_OR_VALUE_FAILURE",
    "INELIGIBLE_MAPPING_STATUS_ENTERED_EVIDENCE",
    "HPSA_DUPLICATE_OR_SUMMARY_FAILURE",
    "SITE_CATEGORY_OR_COUNT_FAILURE",
    "CONTEXT_ONLY_SOURCE_ENTERED_EVIDENCE",
    "ANALYTICAL_FIELD_EMITTED",
    "OUTPUT_EXISTS_REPOSITORY_DIRTY_OR_INPUT_CHANGED",
)
EXPECTED_INPUT_IDENTITIES = {
    "source_snapshot_id": "cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb",
    "input_staging_build_identity": "238da712ad4a9d08b602e89ae8eaa2446871de1e6d84f2dc162ac8a69c5f3b0d",
    "input_staging_build_manifest_file_sha256": "88a9f1ccdfed0cc56993afa7e054c7d81fbe49261dc5a49655a1fc74d3c1b6d6",
    "input_staging_checkpoint_manifest_canonical_sha256": "676727dfa8a91e5ab1225a8a01eb7b2f1df04465fd57ac714dd6ac54efc3b203",
    "input_staging_checkpoint_manifest_file_sha256": "e2f7818b159120eb0a81cf16f6db66ec574f9a6a7d1f914efcf91688ce89c43f",
    "input_geography_checkpoint_identity": "2ccef71e269fd9ccb8218ac316161076db67cc7de7303085b777de45bb10ad0a",
    "input_geography_manifest_canonical_sha256": "2bdc296c2567ea4f471b2baff0675aa33cf848b387dc4c36ead9a1133847bc10",
    "input_geography_manifest_file_sha256": "8724266f2bbc8010cdabdec3bd8ef7bd6b52721d9c031b20b3e0927da84eabf5",
}


class CountyEvidenceError(ValueError):
    """Raised when county evidence violates its accepted contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CountyEvidenceError(message)


def _expected_output_names() -> list[str]:
    names = [
        "canonical_fips", "state_fips", "county_code", "state_name",
        "county_name", "population", "decision_scope_status", "scope_reason",
        "hhs_source_row_number", "hhs_mapping_status", "hhs_mapping_rule_id",
        "hhs_medicare_benes", "hhs_power_dependent_devices_dme",
        "hhs_dme_ambiguous_11", "fema_source_row_number",
        "fema_mapping_status", "fema_mapping_rule_id", "fema_risk_score",
        "fema_risk_rating",
    ]
    for code in HAZARD_CODES:
        prefix = f"fema_{code.lower()}_risk"
        names.extend((f"{prefix}_score", f"{prefix}_rating"))
    names.extend(
        [
            "hpsa_mapped_source_row_count", "hpsa_exact_duplicate_count",
            "hpsa_distinct_id_count", "hpsa_designated_eligible_row_count",
            "hpsa_designated_max_raw_score",
            "hpsa_designated_with_proposed_eligible_row_count",
            "hpsa_designated_with_proposed_max_raw_score",
            "hpsa_lineage_sha256", "site_mapped_source_row_count",
            "site_status_counts_json", "site_location_type_counts_json",
            "site_lineage_sha256", "hhs_present", "fema_present",
            "hpsa_present", "site_present", "evidence_valid",
        ]
    )
    return names


def validate_county_evidence_contract(
    contract: dict[str, Any],
    schema: dict[str, Any],
    repository_root: Path | None = None,
    *,
    enforce_accepted_contract: bool = True,
) -> None:
    """Validate structure, semantic invariants, and optional public identities."""

    validate_schema(contract, schema, "county evidence contract")
    roles = contract["source_roles"]
    role_ids = [item["staging_table_id"] for item in roles]
    _require(tuple(role_ids) == SOURCE_ROLE_IDS, "county evidence source roles differ")
    _require(
        len({item["role"] for item in roles}) == len(roles),
        "county evidence roles are not unique",
    )
    expected_fields = {
        "HHS_CURRENT": ["Medicare_Benes", "Power_Dependent_Devices_DME"],
        "FEMA_RISK": [
            "RISK_SCORE", "RISK_RATNG",
            *[field for code in HAZARD_CODES for field in (f"{code}_RISKS", f"{code}_RISKR")],
        ],
        "HPSA_COMPONENT": [
            "HPSA ID", "HPSA Score", "HPSA Status", "Designation Type",
            "HPSA Discipline Class", "HPSA Designation Population",
            "HPSA Estimated Underserved Population",
            "State and County Federal Information Processing Standard Code",
            "Common State County FIPS Code", "Data Warehouse Record Create Date",
        ],
        "SITE_CONTEXT": [
            "BPHC Assigned Number", "Site Name", "Health Center Type",
            "Operating Hours per Week", "Site Status Description",
            "Health Center Location Type Description",
            "State and County Federal Information Processing Standard Code",
            "Data Warehouse Record Create Date",
        ],
    }
    expected_statuses = {
        "HHS_CURRENT": ["DIRECT_REFERENCE", "EXACT_REPLACEMENT"],
        "FEMA_RISK": ["DIRECT_REFERENCE"],
        "HPSA_COMPONENT": ["DIRECT_REFERENCE"],
        "SITE_CONTEXT": ["DIRECT_REFERENCE"],
    }
    for role in roles:
        _require(
            role["map_artifact_id"] == f"map_{role['staging_table_id']}"
            and role["required_fields"] == expected_fields[role["role"]]
            and role["allowed_mapping_statuses"] == expected_statuses[role["role"]],
            f"{role['role']}: source role semantics differ",
        )
    _require(
        tuple(contract["hazard_codes"]) == HAZARD_CODES,
        "county evidence hazard codes differ",
    )
    columns = contract["output_columns"]
    names = [item["name"] for item in columns]
    _require(names == _expected_output_names(), "county evidence output columns differ")
    _require(len(names) == len(set(names)), "county evidence output columns repeat")
    _require(
        not any(name.startswith("C_") for name in names),
        "analytical criterion field entered county evidence",
    )
    _require(
        tuple(contract["failure_conditions"]) == EXPECTED_FAILURE_CONDITIONS,
        "county evidence failure conditions differ",
    )
    reference = contract["reference"]
    _require(
        reference["eligible_count"] + reference["out_of_scope_count"]
        == reference["expected_county_count"],
        "county evidence scope counts do not sum to reference count",
    )
    hpsa = contract["hpsa_summary"]
    _require(
        hpsa["primary_statuses"] == ["Designated"]
        and hpsa["sensitivity_statuses"]
        == ["Designated", "Proposed For Withdrawal"],
        "HPSA status families differ",
    )
    if repository_root is not None:
        config = repository_root / "configs"
        identities = {
            "source_contract_sha256": config / "sources.json",
            "source_table_contract_sha256": config / "source_tables.json",
            "staging_table_contract_sha256": config / "staging_tables.json",
            "method_contract_sha256": config / "method.json",
            "geography_contract_sha256": config / "geography.json",
        }
        for field, path in identities.items():
            _require(contract[field] == sha256_file(path), f"{field} differs")
        specification = repository_root / contract["specification"]["document"]
        _require(
            contract["specification"]["accepted_review_sha256"]
            == sha256_file(specification),
            "county evidence specification hash differs",
        )
    if enforce_accepted_contract:
        for field, expected in EXPECTED_INPUT_IDENTITIES.items():
            _require(contract[field] == expected, f"accepted {field} differs")
        _require(
            reference == {
                "artifact_id": "county_reference",
                "expected_county_count": 3144,
                "eligible_count": 3133,
                "out_of_scope_count": 11,
            },
            "county evidence reference invariants differ",
        )
        _require(
            [item["expected_mapped_count"] for item in roles]
            == [3133, 3144, 78883, 18993],
            "county evidence mapped counts differ",
        )


def _canonical_typed(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float):
            _require(math.isfinite(value), "non-finite source value is prohibited")
        return value
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, (datetime, date)):
        return {"type": type(value).__name__, "value": value.isoformat()}
    raise CountyEvidenceError(f"unsupported source value type: {type(value).__name__}")


def _canonical_category_map(counts: Counter[str]) -> str:
    return json.dumps(
        dict(sorted(counts.items())),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _index_staging_rows(
    rows: Sequence[Mapping[str, Any]], role: Mapping[str, Any]
) -> dict[int, Mapping[str, Any]]:
    table_id = role["staging_table_id"]
    fields = ["source_row_number", *role["required_fields"]]
    _require(bool(rows), f"{table_id}: staging rows are empty")
    index: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        _require(list(row) == fields, f"{table_id}: staged fields or order differ")
        number = row["source_row_number"]
        _require(type(number) is int and number > 0, f"{table_id}: invalid source row")
        _require(number not in index, f"{table_id}: staging lineage is duplicated")
        index[number] = row
    _require(
        sorted(index) == list(range(1, len(rows) + 1)),
        f"{table_id}: staging lineage is incomplete or changed",
    )
    return index


def _recover_mapped_rows(
    staging_rows: Sequence[Mapping[str, Any]],
    map_rows: Sequence[Mapping[str, Any]],
    role: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    table_id = role["staging_table_id"]
    index = _index_staging_rows(staging_rows, role)
    _require(len(map_rows) == len(index), f"{table_id}: map-to-staging count differs")
    seen: set[int] = set()
    recovered = []
    allowed = set(role["allowed_mapping_statuses"])
    for mapping in map_rows:
        _require(mapping["source_table_id"] == table_id, f"{table_id}: map source differs")
        number = mapping["source_row_number"]
        _require(number in index and number not in seen, f"{table_id}: map lineage differs")
        seen.add(number)
        canonical = mapping["canonical_fips"]
        status = mapping["mapping_status"]
        if status in allowed:
            _require(canonical is not None, f"{table_id}: allowed mapping lacks FIPS")
            recovered.append((mapping, index[number]))
        else:
            _require(canonical is None, f"{table_id}: ineligible mapping entered evidence")
    _require(seen == set(index), f"{table_id}: map lineage population differs")
    _require(
        len(recovered) == role["expected_mapped_count"],
        f"{table_id}: mapped count differs",
    )
    return recovered


def _one_per_county(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    expected: set[str],
    label: str,
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    result: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for mapping, source in pairs:
        fips = mapping["canonical_fips"]
        _require(fips not in result, f"{label}: duplicate county coverage")
        result[fips] = (mapping, source)
    _require(set(result) == expected, f"{label}: county coverage differs")
    return result


def _hpsa_summaries(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    by_county: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for pair in pairs:
        by_county[pair[0]["canonical_fips"]].append(pair)
    summary: dict[str, dict[str, Any]] = {}
    fields = next(
        role["required_fields"] for role in contract["source_roles"]
        if role["role"] == "HPSA_COMPONENT"
    )
    rules = contract["hpsa_summary"]
    for fips, county_pairs in by_county.items():
        ordered = sorted(county_pairs, key=lambda pair: pair[0]["source_row_number"])
        unique: list[Mapping[str, Any]] = []
        identities: set[str] = set()
        duplicates = 0
        for _, source in ordered:
            identity = sha256_json([
                {"field": field, "value": _canonical_typed(source[field])}
                for field in fields
            ])
            if identity in identities:
                duplicates += 1
            else:
                identities.add(identity)
                unique.append(source)
        eligible_type = set(rules["designation_types"])
        primary = [
            row for row in unique
            if row["HPSA Status"] in rules["primary_statuses"]
            and row["Designation Type"] in eligible_type
        ]
        sensitivity = [
            row for row in unique
            if row["HPSA Status"] in rules["sensitivity_statuses"]
            and row["Designation Type"] in eligible_type
        ]
        lineage = [pair[0]["source_row_number"] for pair in ordered]
        summary[fips] = {
            "hpsa_mapped_source_row_count": len(ordered),
            "hpsa_exact_duplicate_count": duplicates,
            "hpsa_distinct_id_count": len({row["HPSA ID"] for row in unique}),
            "hpsa_designated_eligible_row_count": len(primary),
            "hpsa_designated_max_raw_score": (
                max(row["HPSA Score"] for row in primary) if primary else None
            ),
            "hpsa_designated_with_proposed_eligible_row_count": len(sensitivity),
            "hpsa_designated_with_proposed_max_raw_score": (
                max(row["HPSA Score"] for row in sensitivity) if sensitivity else None
            ),
            "hpsa_lineage_sha256": sha256_json(lineage),
        }
    return summary


def _site_summaries(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    by_county: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = defaultdict(list)
    for pair in pairs:
        by_county[pair[0]["canonical_fips"]].append(pair)
    rules = contract["site_summary"]
    result = {}
    for fips, county_pairs in by_county.items():
        ordered = sorted(county_pairs, key=lambda pair: pair[0]["source_row_number"])
        status = Counter(pair[1][rules["status_field"]] for pair in ordered)
        location = Counter(pair[1][rules["location_type_field"]] for pair in ordered)
        _require(
            all(isinstance(key, str) for key in [*status, *location]),
            "site category is not text",
        )
        lineage = [pair[0]["source_row_number"] for pair in ordered]
        result[fips] = {
            "site_mapped_source_row_count": len(ordered),
            "site_status_counts_json": _canonical_category_map(status),
            "site_location_type_counts_json": _canonical_category_map(location),
            "site_lineage_sha256": sha256_json(lineage),
        }
    return result


def build_county_evidence(
    staging_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    geography_outputs: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build one source-evidence row per reference county, without criteria."""

    roles = {item["role"]: item for item in contract["source_roles"]}
    _require(set(staging_rows) == set(SOURCE_ROLE_IDS), "evidence staging table set differs")
    _require(
        "stg_hhs_empower_history_county" not in staging_rows,
        "context-only historical HHS entered evidence",
    )
    references = list(geography_outputs["county_reference"])
    source_maps = geography_outputs["source_maps"]
    expected_maps = {item["staging_table_id"] for item in contract["source_roles"]}
    _require(expected_maps.issubset(source_maps), "evidence geography maps are missing")
    _require(
        len(references) == contract["reference"]["expected_county_count"],
        "county reference count differs",
    )
    references.sort(key=lambda row: row["canonical_fips"])
    reference_fips = [row["canonical_fips"] for row in references]
    _require(len(reference_fips) == len(set(reference_fips)), "county reference FIPS repeat")
    eligible = {
        row["canonical_fips"] for row in references
        if row["decision_scope_status"] == "ELIGIBLE"
    }
    out_of_scope = {
        row["canonical_fips"] for row in references
        if row["decision_scope_status"] == "OUT_OF_SCOPE"
    }
    _require(
        len(eligible) == contract["reference"]["eligible_count"]
        and len(out_of_scope) == contract["reference"]["out_of_scope_count"],
        "county reference scope counts differ",
    )

    recovered = {}
    for role in contract["source_roles"]:
        table_id = role["staging_table_id"]
        recovered[role["role"]] = _recover_mapped_rows(
            staging_rows[table_id], source_maps[table_id], role
        )
    hhs = _one_per_county(recovered["HHS_CURRENT"], eligible, "HHS")
    fema = _one_per_county(recovered["FEMA_RISK"], set(reference_fips), "FEMA")
    hpsa = _hpsa_summaries(recovered["HPSA_COMPONENT"], contract)
    sites = _site_summaries(recovered["SITE_CONTEXT"], contract)
    empty_hash = sha256_json([])
    rows = []
    for reference in references:
        fips = reference["canonical_fips"]
        hhs_pair = hhs.get(fips)
        fema_map, fema_source = fema[fips]
        risk_score = fema_source["RISK_SCORE"]
        _require(
            type(risk_score) in (int, float)
            and math.isfinite(risk_score)
            and 0 <= risk_score <= 100,
            "FEMA composite score is invalid",
        )
        row = dict(reference)
        if hhs_pair is None:
            _require(fips in out_of_scope, "eligible county lacks HHS evidence")
            row.update({
                "hhs_source_row_number": None,
                "hhs_mapping_status": None,
                "hhs_mapping_rule_id": None,
                "hhs_medicare_benes": None,
                "hhs_power_dependent_devices_dme": None,
                "hhs_dme_ambiguous_11": False,
            })
        else:
            hhs_map, hhs_source = hhs_pair
            medicare = hhs_source["Medicare_Benes"]
            dme = hhs_source["Power_Dependent_Devices_DME"]
            _require(
                type(medicare) is int and type(dme) is int
                and medicare >= 0 and dme >= 0 and dme <= medicare,
                "HHS source values are invalid",
            )
            row.update({
                "hhs_source_row_number": hhs_map["source_row_number"],
                "hhs_mapping_status": hhs_map["mapping_status"],
                "hhs_mapping_rule_id": hhs_map["mapping_rule_id"],
                "hhs_medicare_benes": medicare,
                "hhs_power_dependent_devices_dme": dme,
                "hhs_dme_ambiguous_11": dme == 11,
            })
        row.update({
            "fema_source_row_number": fema_map["source_row_number"],
            "fema_mapping_status": fema_map["mapping_status"],
            "fema_mapping_rule_id": fema_map["mapping_rule_id"],
            "fema_risk_score": risk_score,
            "fema_risk_rating": fema_source["RISK_RATNG"],
        })
        for code in contract["hazard_codes"]:
            prefix = f"fema_{code.lower()}_risk"
            row[f"{prefix}_score"] = fema_source[f"{code}_RISKS"]
            row[f"{prefix}_rating"] = fema_source[f"{code}_RISKR"]
        row.update(hpsa.get(fips, {
            "hpsa_mapped_source_row_count": 0,
            "hpsa_exact_duplicate_count": 0,
            "hpsa_distinct_id_count": 0,
            "hpsa_designated_eligible_row_count": 0,
            "hpsa_designated_max_raw_score": None,
            "hpsa_designated_with_proposed_eligible_row_count": 0,
            "hpsa_designated_with_proposed_max_raw_score": None,
            "hpsa_lineage_sha256": empty_hash,
        }))
        row.update(sites.get(fips, {
            "site_mapped_source_row_count": 0,
            "site_status_counts_json": "{}",
            "site_location_type_counts_json": "{}",
            "site_lineage_sha256": empty_hash,
        }))
        row.update({
            "hhs_present": hhs_pair is not None,
            "fema_present": True,
            "hpsa_present": row["hpsa_mapped_source_row_count"] > 0,
            "site_present": row["site_mapped_source_row_count"] > 0,
            "evidence_valid": True,
        })
        _require(
            list(row) == [item["name"] for item in contract["output_columns"]],
            "county evidence output field order differs",
        )
        rows.append(row)
    return rows
