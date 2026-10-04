"""Fail-closed county geography reconciliation over already-staged rows."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import validate_schema
from .hashing import sha256_json

FIPS_PATTERN = re.compile(r"^[0-9]{5}$")
STATE_PATTERN = re.compile(r"^[0-9]{2}$")
COUNTY_PATTERN = re.compile(r"^[0-9]{3}$")

MAPPING_STATUSES = (
    "DIRECT_REFERENCE",
    "EXACT_REPLACEMENT",
    "UNRESOLVED_LEGACY_GEOGRAPHY",
    "OUTSIDE_REFERENCE_UNIVERSE",
    "MISSING_SOURCE_FIPS",
    "INVALID_SOURCE_FIPS",
    "STATE_SUMMARY_NOT_COUNTY",
)
OUT_OF_SCOPE_FIPS = (
    "02063", "02066", "09110", "09120", "09130", "09140", "09150",
    "09160", "09170", "09180", "09190",
)
REPLACEMENTS = (
    ("02270", "02158", "HHS_WADE_HAMPTON_TO_KUSILVAK"),
    ("46113", "46102", "HHS_SHANNON_TO_OGLALA_LAKOTA"),
)
ALASKA_LEGACY = ("02261",)
CONNECTICUT_LEGACY = (
    "09001", "09003", "09005", "09007", "09009", "09011", "09013", "09015",
)
SOURCE_TABLE_IDS = (
    "stg_census_county_population_2025",
    "stg_hhs_empower_county",
    "stg_hhs_empower_history_county",
    "stg_fema_nri_counties",
    "stg_hrsa_primary_care_hpsa",
    "stg_hrsa_health_center_sites",
)

REFERENCE_COLUMNS = (
    "canonical_fips", "state_fips", "county_code", "state_name", "county_name",
    "population", "decision_scope_status", "scope_reason",
)
MAP_COLUMNS = (
    "source_table_id", "source_row_number", "source_fips_primary",
    "source_fips_secondary", "canonical_fips", "mapping_status",
    "mapping_rule_id", "diagnostic_reason",
)


class GeographyError(ValueError):
    """Raised when geography rules or rows violate the accepted contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeographyError(message)


def validate_geography_contract(
    contract: dict[str, Any],
    schema: dict[str, Any],
    *,
    enforce_accepted_contract: bool = True,
) -> None:
    """Validate schema and semantic invariants for a geography contract."""

    validate_schema(contract, schema, "geography contract")
    reference = contract["reference"]
    _require(
        tuple(contract["mapping_statuses"]) == MAPPING_STATUSES,
        "mapping statuses or their order differ from the accepted set",
    )
    _require(
        reference["expected_county_count"]
        == reference["eligible_count"] + len(reference["out_of_scope_fips"]),
        "reference counts are internally inconsistent",
    )
    _require(
        len(set(reference["out_of_scope_fips"]))
        == len(reference["out_of_scope_fips"]),
        "out-of-scope FIPS are not unique",
    )

    replacements = contract["exact_replacements"]
    replacement_sources = [item["source_fips"] for item in replacements]
    replacement_targets = [item["canonical_fips"] for item in replacements]
    _require(
        len(set(replacement_sources)) == len(replacement_sources)
        and len(set(replacement_targets)) == len(replacement_targets),
        "replacement sources and targets must be one-to-one",
    )
    _require(
        not set(replacement_targets).intersection(reference["out_of_scope_fips"]),
        "replacement target cannot be out of decision scope",
    )

    legacy_codes: list[str] = []
    blocked_codes: list[str] = []
    for group in contract["unresolved_legacy_groups"]:
        legacy_codes.extend(group["source_fips"])
        blocked_codes.extend(group["blocked_reference_fips"])
    _require(len(set(legacy_codes)) == len(legacy_codes), "legacy FIPS overlap")
    _require(
        not set(legacy_codes).intersection(replacement_sources),
        "a legacy FIPS cannot also be a replacement",
    )
    _require(
        set(blocked_codes).issubset(reference["out_of_scope_fips"]),
        "legacy allocation blockers must remain out of scope",
    )

    source_rules = contract["source_rules"]
    source_ids = [item["staging_table_id"] for item in source_rules]
    _require(len(source_ids) == len(set(source_ids)), "source rule ids are not unique")
    _require(
        set(source_ids) == set(SOURCE_TABLE_IDS),
        "geography contract does not cover the exact six staging tables",
    )
    for rule in source_rules:
        statuses: list[str] = []
        declared_total = 0
        for count in rule["expected_mapping_counts"]:
            _require(
                not set(statuses).intersection(count["statuses"]),
                f"{rule['staging_table_id']}: mapping count groups overlap",
            )
            statuses.extend(count["statuses"])
            declared_total += count["expected_count"]
        _require(
            declared_total == rule["expected_total_count"],
            f"{rule['staging_table_id']}: mapping counts do not sum to total",
        )

    if not enforce_accepted_contract:
        return

    _require(
        contract["source_snapshot_id"]
        == "cc1489ab008db4d5d1b2eddf798b51218e2324e97e88ab9c7d3853927bb54dbb",
        "source snapshot identity differs from accepted evidence",
    )
    _require(
        contract["input_staging_build_identity"]
        == "238da712ad4a9d08b602e89ae8eaa2446871de1e6d84f2dc162ac8a69c5f3b0d",
        "input staging build identity differs from accepted evidence",
    )
    _require(
        contract["input_staging_build_manifest_file_sha256"]
        == "88a9f1ccdfed0cc56993afa7e054c7d81fbe49261dc5a49655a1fc74d3c1b6d6",
        "input staging build-manifest identity differs from accepted evidence",
    )
    _require(
        contract["input_staging_checkpoint_manifest_canonical_sha256"]
        == "676727dfa8a91e5ab1225a8a01eb7b2f1df04465fd57ac714dd6ac54efc3b203"
        and contract["input_staging_checkpoint_manifest_file_sha256"]
        == "e2f7818b159120eb0a81cf16f6db66ec574f9a6a7d1f914efcf91688ce89c43f",
        "input staging checkpoint-manifest identity differs from accepted evidence",
    )
    _require(
        contract["staging_table_contract_sha256"]
        == "40c861170f96f1156c58a6ce95ae4262051364097a4c102eb2c97300758eabe1",
        "staging-table contract identity differs from accepted evidence",
    )
    _require(
        contract["specification"]["accepted_review_sha256"]
        == "a9ce98e10ca596dfd7ec4f62cdd706e682bf1d42aa4ecb9c6a75328d514f1adb",
        "geography specification review identity differs from acceptance",
    )
    _require(
        (
            reference["expected_county_count"],
            reference["expected_state_summary_count"],
            reference["eligible_count"],
            tuple(reference["out_of_scope_fips"]),
        ) == (3144, 51, 3133, OUT_OF_SCOPE_FIPS),
        "accepted reference universe or out-of-scope set changed",
    )
    _require(
        {
            key: reference[key]
            for key in (
                "source_table_id", "summary_level_field", "county_summary_level",
                "state_summary_level", "state_field", "county_field",
                "state_name_field", "county_name_field", "population_field",
            )
        }
        == {
            "source_table_id": "stg_census_county_population_2025",
            "summary_level_field": "SUMLEV",
            "county_summary_level": "050",
            "state_summary_level": "040",
            "state_field": "STATE",
            "county_field": "COUNTY",
            "state_name_field": "STNAME",
            "county_name_field": "CTYNAME",
            "population_field": "POPESTIMATE2025",
        },
        "accepted Census reference selectors changed",
    )
    observed_replacements = tuple(
        (item["source_fips"], item["canonical_fips"], item["rule_id"])
        for item in replacements
    )
    _require(observed_replacements == REPLACEMENTS, "accepted replacements changed")
    accepted_hhs_tables = (
        "stg_hhs_empower_county",
        "stg_hhs_empower_history_county",
    )
    _require(
        all(
            tuple(item["allowed_source_table_ids"]) == accepted_hhs_tables
            for item in replacements
        ),
        "accepted replacement source scope changed",
    )
    _require(
        tuple(contract["unresolved_legacy_groups"][0]["source_fips"])
        == ALASKA_LEGACY
        and tuple(contract["unresolved_legacy_groups"][1]["source_fips"])
        == CONNECTICUT_LEGACY,
        "accepted unresolved legacy FIPS changed",
    )
    _require(
        tuple(contract["unresolved_legacy_groups"][0]["blocked_reference_fips"])
        == ("02063", "02066")
        and tuple(contract["unresolved_legacy_groups"][1]["blocked_reference_fips"])
        == OUT_OF_SCOPE_FIPS[2:]
        and all(
            tuple(item["allowed_source_table_ids"]) == accepted_hhs_tables
            for item in contract["unresolved_legacy_groups"]
        ),
        "accepted unresolved legacy scope or allocation blockers changed",
    )
    expected_totals = {
        "stg_census_county_population_2025": 3195,
        "stg_hhs_empower_county": 3233,
        "stg_hhs_empower_history_county": 3228,
        "stg_fema_nri_counties": 3232,
        "stg_hrsa_primary_care_hpsa": 80199,
        "stg_hrsa_health_center_sites": 19283,
    }
    _require(
        {item["staging_table_id"]: item["expected_total_count"] for item in source_rules}
        == expected_totals,
        "accepted source mapping totals changed",
    )
    expected_rules = {
        "stg_census_county_population_2025": (
            "CENSUS_REFERENCE", ("STATE", "COUNTY"),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 3144),
             ("STATE_SUMMARY_NOT_COUNTY", ("STATE_SUMMARY_NOT_COUNTY",), 51)),
            "ALL_REFERENCE_EXACTLY_ONCE",
        ),
        "stg_hhs_empower_county": (
            "HHS_SINGLE_FIPS", ("FIPS_Code",),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 3131),
             ("EXACT_REPLACEMENT", ("EXACT_REPLACEMENT",), 2),
             ("UNRESOLVED_LEGACY_GEOGRAPHY", ("UNRESOLVED_LEGACY_GEOGRAPHY",), 9),
             ("OUTSIDE_REFERENCE_UNIVERSE", ("OUTSIDE_REFERENCE_UNIVERSE",), 86),
             ("MISSING_SOURCE_FIPS", ("MISSING_SOURCE_FIPS",), 5)),
            "ELIGIBLE_REFERENCE_EXACTLY_ONCE",
        ),
        "stg_hhs_empower_history_county": (
            "HHS_SINGLE_FIPS", ("FIPS_Code",),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 3131),
             ("EXACT_REPLACEMENT", ("EXACT_REPLACEMENT",), 2),
             ("UNRESOLVED_LEGACY_GEOGRAPHY", ("UNRESOLVED_LEGACY_GEOGRAPHY",), 9),
             ("OUTSIDE_REFERENCE_UNIVERSE", ("OUTSIDE_REFERENCE_UNIVERSE",), 86)),
            "NONE",
        ),
        "stg_fema_nri_counties": (
            "DIRECT_SINGLE_FIPS", ("STCOFIPS",),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 3144),
             ("OUTSIDE_REFERENCE_UNIVERSE", ("OUTSIDE_REFERENCE_UNIVERSE",), 88)),
            "ALL_REFERENCE_EXACTLY_ONCE",
        ),
        "stg_hrsa_primary_care_hpsa": (
            "DIRECT_DUAL_FIPS",
            ("State and County Federal Information Processing Standard Code",
             "Common State County FIPS Code"),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 78883),
             ("OUTSIDE_REFERENCE_UNIVERSE", ("OUTSIDE_REFERENCE_UNIVERSE",), 393),
             ("WITHOUT_VALID_SOURCE_FIPS", ("MISSING_SOURCE_FIPS", "INVALID_SOURCE_FIPS"), 923)),
            "NONE",
        ),
        "stg_hrsa_health_center_sites": (
            "DIRECT_SINGLE_FIPS",
            ("State and County Federal Information Processing Standard Code",),
            (("DIRECT_REFERENCE", ("DIRECT_REFERENCE",), 18993),
             ("OUTSIDE_REFERENCE_UNIVERSE", ("OUTSIDE_REFERENCE_UNIVERSE",), 213),
             ("WITHOUT_VALID_SOURCE_FIPS", ("MISSING_SOURCE_FIPS", "INVALID_SOURCE_FIPS"), 77)),
            "NONE",
        ),
    }
    observed_rules = {
        item["staging_table_id"]: (
            item["rule_kind"],
            tuple(item["geography_fields"]),
            tuple(
                (count["count_id"], tuple(count["statuses"]), count["expected_count"])
                for count in item["expected_mapping_counts"]
            ),
            item["required_reference_coverage"],
        )
        for item in source_rules
    }
    _require(observed_rules == expected_rules, "accepted source geography rules changed")
    _require(
        all(item["expected_valid_field_conflicts"] == 0 for item in source_rules),
        "accepted valid-field conflict requirement changed",
    )


def _validate_source_rows(table_id: str, rows: Sequence[Mapping[str, Any]]) -> None:
    row_numbers = [row.get("source_row_number") for row in rows]
    _require(
        all(type(value) is int for value in row_numbers),
        f"{table_id}: source row number must be an integer",
    )
    _require(
        len(row_numbers) == len(set(row_numbers)),
        f"{table_id}: source row lineage is duplicated",
    )
    _require(
        sorted(row_numbers) == list(range(1, len(rows) + 1)),
        f"{table_id}: source row lineage is incomplete or changed",
    )


def _source_fips_state(value: Any, *, table_id: str, field: str) -> str:
    if value is None or value == "":
        return "MISSING"
    _require(
        isinstance(value, str),
        f"{table_id}: {field} must remain text or null",
    )
    return "VALID" if FIPS_PATTERN.fullmatch(value) else "INVALID"


def _map_row(
    table_id: str,
    row_number: int,
    primary: str | None,
    secondary: str | None,
    canonical_fips: str | None,
    status: str,
    rule_id: str,
    reason: str | None,
) -> dict[str, Any]:
    return dict(
        zip(
            MAP_COLUMNS,
            (
                table_id, row_number, primary, secondary, canonical_fips,
                status, rule_id, reason,
            ),
        )
    )


def _build_reference(
    census_rows: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reference_rule = contract["reference"]
    table_id = reference_rule["source_table_id"]
    out_of_scope = set(reference_rule["out_of_scope_fips"])
    county_rows: list[dict[str, Any]] = []
    source_map: list[dict[str, Any]] = []
    seen: set[str] = set()
    state_summary_count = 0

    for row in sorted(census_rows, key=lambda item: item["source_row_number"]):
        summary_level = row.get(reference_rule["summary_level_field"])
        state = row.get(reference_rule["state_field"])
        county = row.get(reference_rule["county_field"])
        _require(
            isinstance(state, str) and STATE_PATTERN.fullmatch(state) is not None,
            f"{table_id}: malformed Census state component",
        )
        _require(
            isinstance(county, str) and COUNTY_PATTERN.fullmatch(county) is not None,
            f"{table_id}: malformed Census county component",
        )
        if summary_level == reference_rule["state_summary_level"]:
            state_summary_count += 1
            source_map.append(
                _map_row(
                    table_id, row["source_row_number"], state, county, None,
                    "STATE_SUMMARY_NOT_COUNTY", "CENSUS_STATE_SUMMARY", None,
                )
            )
            continue
        _require(
            summary_level == reference_rule["county_summary_level"],
            f"{table_id}: unexpected Census summary level",
        )
        canonical = f"{state}{county}"
        _require(canonical not in seen, f"{table_id}: duplicate Census county key")
        seen.add(canonical)
        population = row.get(reference_rule["population_field"])
        _require(
            type(population) is int and population > 0,
            f"{table_id}: population must be a positive integer",
        )
        state_name = row.get(reference_rule["state_name_field"])
        county_name = row.get(reference_rule["county_name_field"])
        _require(
            isinstance(state_name, str) and state_name
            and isinstance(county_name, str) and county_name,
            f"{table_id}: Census display names must be nonempty text",
        )
        is_out = canonical in out_of_scope
        county_rows.append(
            dict(
                zip(
                    REFERENCE_COLUMNS,
                    (
                        canonical, state, county, state_name, county_name, population,
                        "OUT_OF_SCOPE" if is_out else "ELIGIBLE",
                        "BOUNDARY_NOT_COMPARABLE_WITH_CURRENT_HHS"
                        if is_out else None,
                    ),
                )
            )
        )
        source_map.append(
            _map_row(
                table_id, row["source_row_number"], state, county, canonical,
                "DIRECT_REFERENCE", "CENSUS_STATE_COUNTY_CONCATENATION", None,
            )
        )

    county_rows.sort(key=lambda item: item["canonical_fips"])
    _require(
        len(county_rows) == reference_rule["expected_county_count"],
        "Census county reference count differs from contract",
    )
    _require(
        state_summary_count == reference_rule["expected_state_summary_count"],
        "Census state-summary count differs from contract",
    )
    observed_out = {
        item["canonical_fips"]
        for item in county_rows
        if item["decision_scope_status"] == "OUT_OF_SCOPE"
    }
    _require(observed_out == out_of_scope, "out-of-scope reference set differs")
    _require(
        sum(item["decision_scope_status"] == "ELIGIBLE" for item in county_rows)
        == reference_rule["eligible_count"],
        "eligible reference count differs",
    )
    return county_rows, source_map


def _map_single_fips(
    table_id: str,
    row: Mapping[str, Any],
    field: str,
    reference_fips: set[str],
    replacements: Mapping[str, Mapping[str, Any]],
    legacy: Mapping[str, str],
    *,
    hhs_rules: bool,
) -> dict[str, Any]:
    value = row.get(field)
    state = _source_fips_state(value, table_id=table_id, field=field)
    if state == "MISSING":
        return _map_row(
            table_id, row["source_row_number"], value, None, None,
            "MISSING_SOURCE_FIPS", "SOURCE_FIPS_MISSING", None,
        )
    if state == "INVALID":
        return _map_row(
            table_id, row["source_row_number"], value, None, None,
            "INVALID_SOURCE_FIPS", "STRICT_FIVE_DIGIT_VALIDATION",
            "SOURCE_FIPS_IS_NOT_EXACTLY_FIVE_DIGITS",
        )
    assert isinstance(value, str)
    if value in replacements:
        _require(hhs_rules, f"{table_id}: HHS replacement source code is prohibited")
        replacement = replacements[value]
        return _map_row(
            table_id, row["source_row_number"], value, None,
            replacement["canonical_fips"], "EXACT_REPLACEMENT",
            replacement["rule_id"], None,
        )
    if hhs_rules and value in legacy:
        return _map_row(
            table_id, row["source_row_number"], value, None, None,
            "UNRESOLVED_LEGACY_GEOGRAPHY", legacy[value],
            "ONE_TO_MANY_ALLOCATION_PROHIBITED",
        )
    if value in reference_fips:
        return _map_row(
            table_id, row["source_row_number"], value, None, value,
            "DIRECT_REFERENCE", "EXACT_SOURCE_FIPS", None,
        )
    return _map_row(
        table_id, row["source_row_number"], value, None, None,
        "OUTSIDE_REFERENCE_UNIVERSE", "VALID_FIPS_OUTSIDE_REFERENCE", None,
    )


def _map_dual_fips(
    table_id: str,
    row: Mapping[str, Any],
    fields: Sequence[str],
    reference_fips: set[str],
    forbidden_replacements: set[str],
) -> dict[str, Any]:
    primary, secondary = (row.get(field) for field in fields)
    primary_state = _source_fips_state(primary, table_id=table_id, field=fields[0])
    secondary_state = _source_fips_state(secondary, table_id=table_id, field=fields[1])
    valid = [
        (primary, "HPSA_PRIMARY_FIPS") if primary_state == "VALID" else None,
        (secondary, "HPSA_FALLBACK_FIPS") if secondary_state == "VALID" else None,
    ]
    valid = [item for item in valid if item is not None]
    _require(
        not any(value in forbidden_replacements for value, _ in valid),
        f"{table_id}: HHS replacement source code is prohibited",
    )
    if len(valid) == 2:
        _require(valid[0][0] == valid[1][0], f"{table_id}: valid HPSA FIPS fields conflict")
    if not valid:
        status = (
            "MISSING_SOURCE_FIPS"
            if primary_state == secondary_state == "MISSING"
            else "INVALID_SOURCE_FIPS"
        )
        return _map_row(
            table_id, row["source_row_number"], primary, secondary, None, status,
            "HPSA_NO_VALID_FIPS", "NEITHER_HPSA_FIPS_FIELD_IS_VALID",
        )
    chosen, rule_id = valid[0]
    assert isinstance(chosen, str)
    if chosen in reference_fips:
        return _map_row(
            table_id, row["source_row_number"], primary, secondary, chosen,
            "DIRECT_REFERENCE", rule_id, None,
        )
    return _map_row(
        table_id, row["source_row_number"], primary, secondary, None,
        "OUTSIDE_REFERENCE_UNIVERSE", rule_id, "VALID_FIPS_OUTSIDE_REFERENCE",
    )


def _validate_expected_counts(
    rule: Mapping[str, Any], mapped_rows: Sequence[Mapping[str, Any]]
) -> None:
    _require(
        len(mapped_rows) == rule["expected_total_count"],
        f"{rule['staging_table_id']}: source mapping total differs",
    )
    status_counts = Counter(row["mapping_status"] for row in mapped_rows)
    for expected in rule["expected_mapping_counts"]:
        observed = sum(status_counts[status] for status in expected["statuses"])
        _require(
            observed == expected["expected_count"],
            f"{rule['staging_table_id']}: mapping count differs for {expected['count_id']}",
        )


def _validate_coverage(
    rule: Mapping[str, Any],
    mapped_rows: Sequence[Mapping[str, Any]],
    reference_rows: Sequence[Mapping[str, Any]],
) -> None:
    coverage = rule["required_reference_coverage"]
    if coverage == "NONE":
        return
    expected = {
        row["canonical_fips"]
        for row in reference_rows
        if coverage == "ALL_REFERENCE_EXACTLY_ONCE"
        or row["decision_scope_status"] == "ELIGIBLE"
    }
    observed = Counter(
        row["canonical_fips"]
        for row in mapped_rows
        if row["canonical_fips"] is not None
    )
    _require(
        set(observed) == expected and all(count == 1 for count in observed.values()),
        f"{rule['staging_table_id']}: required reference coverage is not exactly one-to-one",
    )


def build_geography_outputs(
    rows_by_staging_table: Mapping[str, Sequence[Mapping[str, Any]]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a county reference and six row-preserving maps without aggregation."""

    rules = {item["staging_table_id"]: item for item in contract["source_rules"]}
    _require(
        set(rows_by_staging_table) == set(rules),
        "input rows do not cover the exact geography source-table set",
    )
    for table_id, rows in rows_by_staging_table.items():
        _validate_source_rows(table_id, rows)

    reference_rows, census_map = _build_reference(
        rows_by_staging_table[contract["reference"]["source_table_id"]], contract
    )
    reference_fips = {row["canonical_fips"] for row in reference_rows}
    replacements = {item["source_fips"]: item for item in contract["exact_replacements"]}
    _require(
        {item["canonical_fips"] for item in replacements.values()}.issubset(reference_fips),
        "replacement target is absent from the county reference",
    )
    legacy = {
        fips: group["rule_id"]
        for group in contract["unresolved_legacy_groups"]
        for fips in group["source_fips"]
    }
    source_maps: dict[str, list[dict[str, Any]]] = {
        contract["reference"]["source_table_id"]: census_map
    }

    for rule in contract["source_rules"]:
        table_id = rule["staging_table_id"]
        if rule["rule_kind"] == "CENSUS_REFERENCE":
            mapped = source_maps[table_id]
        elif rule["rule_kind"] == "DIRECT_DUAL_FIPS":
            mapped = [
                _map_dual_fips(
                    table_id, row, rule["geography_fields"], reference_fips,
                    set(replacements),
                )
                for row in rows_by_staging_table[table_id]
            ]
        else:
            mapped = [
                _map_single_fips(
                    table_id, row, rule["geography_fields"][0], reference_fips,
                    replacements, legacy,
                    hhs_rules=rule["rule_kind"] == "HHS_SINGLE_FIPS",
                )
                for row in rows_by_staging_table[table_id]
            ]
        mapped.sort(key=lambda item: item["source_row_number"])
        _require(
            [row["source_row_number"] for row in mapped]
            == list(range(1, len(mapped) + 1)),
            f"{table_id}: output row lineage changed",
        )
        _require(
            all(list(row) == list(MAP_COLUMNS) for row in mapped),
            f"{table_id}: geography map columns changed",
        )
        _validate_expected_counts(rule, mapped)
        _validate_coverage(rule, mapped, reference_rows)
        source_maps[table_id] = mapped

    return {"county_reference": reference_rows, "source_maps": source_maps}


def geography_content_hashes(outputs: Mapping[str, Any]) -> dict[str, str]:
    """Return canonical hashes independent of input row order."""

    return {
        "county_reference": sha256_json(outputs["county_reference"]),
        **{
            table_id: sha256_json(rows)
            for table_id, rows in sorted(outputs["source_maps"].items())
        },
    }
