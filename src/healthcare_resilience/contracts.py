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
EXPECTED_SOURCE_TABLE_IDS = (
    "hhs_empower_county",
    "fema_nri_counties",
    "hrsa_primary_care_hpsa",
    "hrsa_health_center_sites",
    "census_county_population_2025",
    "hhs_empower_history_state",
    "hhs_empower_history_county",
    "hhs_empower_history_zip_code",
)
EXPECTED_STAGING_TABLE_IDS = (
    "stg_hhs_empower_county",
    "stg_fema_nri_counties",
    "stg_hrsa_primary_care_hpsa",
    "stg_hrsa_health_center_sites",
    "stg_census_county_population_2025",
    "stg_hhs_empower_history_county",
)
EXPECTED_VALIDATION_ONLY_TABLE_IDS = (
    "hhs_empower_history_state",
    "hhs_empower_history_zip_code",
)
EXPECTED_TABLE_FAILURE_CONDITIONS = (
    "MISSING_OR_UNEXPECTED_TABLE_OR_SHEET",
    "ENCODING_OR_BOM_MISMATCH",
    "CSV_DIALECT_OR_LINE_ENDING_MISMATCH",
    "ROW_COUNT_MISMATCH",
    "COLUMN_COUNT_OR_ROW_WIDTH_MISMATCH",
    "ORDERED_HEADER_MISMATCH",
    "MISSING_REQUIRED_COLUMN",
    "REQUIRED_COLUMN_TYPE_MISMATCH",
    "KEY_NULLABILITY_OR_CARDINALITY_MISMATCH",
    "EXACT_DUPLICATE_COUNT_MISMATCH",
)
EXPECTED_STAGING_FAILURE_CONDITIONS = (
    "SOURCE_TABLE_CONTRACT_HASH_MISMATCH",
    "MISSING_OR_UNEXPECTED_STAGING_TABLE",
    "MISSING_RETAINED_SOURCE_COLUMN",
    "NULLABILITY_VIOLATION",
    "OUTPUT_TYPE_PARSE_FAILURE",
    "SOURCE_TO_STAGING_ROW_COUNT_MISMATCH",
    "SOURCE_ROW_ORDER_OR_IDENTITY_CHANGE",
    "VALUE_OR_SEMANTIC_TRANSFORMATION_DETECTED",
    "FILTER_DEDUPLICATION_OR_AGGREGATION_DETECTED",
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
        len({item["private_relative_path"] for item in files}) == len(files),
        "source private relative paths are not unique",
    )
    _require(
        all(
            Path(item["private_relative_path"]).parts
            == ("raw", item["filename"])
            for item in files
        ),
        "source private relative paths must be raw/<filename>",
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


def validate_source_table_contract(
    table_contract: dict[str, Any],
    table_schema: dict[str, Any],
    source_contract: dict[str, Any] | None = None,
    *,
    enforce_accepted_tables: bool = True,
) -> None:
    """Validate structural table declarations without opening source data."""

    validate_schema(table_contract, table_schema, "source-table contract")
    tables = table_contract["table_contracts"]
    _require(
        table_contract["expected_table_count"] == len(tables),
        "source-table expected_table_count does not match table_contracts",
    )
    identifiers = [item["id"] for item in tables]
    _require(len(set(identifiers)) == len(identifiers), "source-table ids are not unique")
    _require(
        tuple(table_contract["schema_failure_conditions"])
        == EXPECTED_TABLE_FAILURE_CONDITIONS,
        "source-table failure conditions changed or are incomplete",
    )

    if source_contract is not None:
        _require(
            table_contract["snapshot_id"] == source_contract["snapshot_id"],
            "source-table contract references a different snapshot",
        )
        sources_by_id = {
            item["id"]: item for item in source_contract["source_files"]
        }
    else:
        sources_by_id = None

    source_locations: set[tuple[str, str | None]] = set()
    for item in tables:
        location = (item["source_id"], item["sheet_name"])
        _require(location not in source_locations, f"duplicate table location for {item['id']}")
        source_locations.add(location)

        if sources_by_id is not None:
            _require(
                item["source_id"] in sources_by_id,
                f"unknown source_id for {item['id']}",
            )
            source = sources_by_id[item["source_id"]]
            _require(
                item["filename"] == source["filename"],
                f"filename differs from source manifest for {item['id']}",
            )
            _require(
                item["role"] == source["role"],
                f"role differs from source manifest for {item['id']}",
            )

        if item["container"] == "CSV":
            _require(item["sheet_name"] is None, f"CSV sheet_name must be null for {item['id']}")
            _require(item["csv_dialect"] is not None, f"CSV dialect is missing for {item['id']}")
            _require(
                item["encoding"] != "NOT_APPLICABLE_BINARY",
                f"CSV encoding is not declared for {item['id']}",
            )
            _require(
                item["byte_order_mark"] != "NOT_APPLICABLE",
                f"CSV byte-order-mark state is not declared for {item['id']}",
            )
        else:
            _require(bool(item["sheet_name"]), f"XLSX sheet_name is missing for {item['id']}")
            _require(item["csv_dialect"] is None, f"XLSX cannot declare a CSV dialect for {item['id']}")
            _require(
                item["encoding"] == "NOT_APPLICABLE_BINARY"
                and item["byte_order_mark"] == "NOT_APPLICABLE",
                f"XLSX text encoding must be not applicable for {item['id']}",
            )

        unnamed_positions = item["unnamed_header_positions"]
        _require(
            all(position <= item["header_cell_count"] for position in unnamed_positions),
            f"unnamed header position is outside the header for {item['id']}",
        )
        _require(
            item["header_cell_count"]
            == item["named_column_count"] + len(unnamed_positions),
            f"header counts are inconsistent for {item['id']}",
        )
        _require(
            item["data_row_field_count"] == item["named_column_count"],
            f"data-row width differs from the named-column count for {item['id']}",
        )

        columns = item["required_columns"]
        column_names = [column["name"] for column in columns]
        _require(
            len(set(column_names)) == len(column_names),
            f"required columns are not unique for {item['id']}",
        )
        _require(
            len(columns) <= item["named_column_count"],
            f"required columns exceed named-column count for {item['id']}",
        )
        key = item["record_key"]
        _require(
            set(key["columns"]).issubset(column_names),
            f"record-key columns are not all required for {item['id']}",
        )
        _require(
            key["expected_nonblank_rows"] <= item["data_row_count"],
            f"record-key nonblank count exceeds rows for {item['id']}",
        )
        _require(
            key["expected_distinct_count"] <= key["expected_nonblank_rows"],
            f"record-key distinct count exceeds nonblank rows for {item['id']}",
        )
        _require(
            key["expected_duplicate_rows_beyond_first"]
            == key["expected_nonblank_rows"] - key["expected_distinct_count"],
            f"record-key duplicate count is inconsistent for {item['id']}",
        )
        if key["null_policy"] == "FORBID":
            _require(
                key["expected_nonblank_rows"] == item["data_row_count"],
                f"record-key null policy conflicts with evidence for {item['id']}",
            )
        if key["kind"] == "UNIQUE":
            _require(
                key["expected_duplicate_rows_beyond_first"] == 0,
                f"unique key has duplicates for {item['id']}",
            )
        _require(
            item["exact_duplicate_rows_beyond_first"] <= item["data_row_count"],
            f"exact-duplicate count exceeds rows for {item['id']}",
        )

    if enforce_accepted_tables:
        _require(
            tuple(identifiers) == EXPECTED_SOURCE_TABLE_IDS,
            "source-table set or order differs from the accepted Gate 1 evidence",
        )
        _require(
            table_contract["snapshot_id"] == ACCEPTED_SOURCE_SNAPSHOT_ID,
            "source-table contract is not tied to the accepted frozen snapshot",
        )


def validate_staging_contract(
    staging_contract: dict[str, Any],
    staging_schema: dict[str, Any],
    source_table_contract: dict[str, Any],
    expected_source_table_contract_sha256: str,
    *,
    enforce_accepted_tables: bool = True,
) -> None:
    """Validate source-preserving staging declarations without reading data."""

    validate_schema(staging_contract, staging_schema, "staging-table contract")
    _require(
        staging_contract["source_snapshot_id"]
        == source_table_contract["snapshot_id"],
        "staging contract references a different source snapshot",
    )
    _require(
        staging_contract["source_table_contract_sha256"]
        == expected_source_table_contract_sha256,
        "staging contract references a different source-table contract hash",
    )
    _require(
        tuple(staging_contract["failure_conditions"])
        == EXPECTED_STAGING_FAILURE_CONDITIONS,
        "staging failure conditions changed or are incomplete",
    )

    staging_tables = staging_contract["staging_tables"]
    validation_only = staging_contract["validation_only_tables"]
    _require(
        staging_contract["expected_staging_table_count"] == len(staging_tables),
        "staging expected_staging_table_count does not match staging_tables",
    )

    staging_ids = [item["id"] for item in staging_tables]
    source_ids = [item["source_table_id"] for item in staging_tables]
    output_names = [item["output_table_name"] for item in staging_tables]
    validation_only_ids = [item["source_table_id"] for item in validation_only]
    _require(len(staging_ids) == len(set(staging_ids)), "staging ids are not unique")
    _require(
        len(source_ids) == len(set(source_ids)),
        "staging source-table references are not unique",
    )
    _require(
        len(output_names) == len(set(output_names)),
        "staging output table names are not unique",
    )
    _require(
        len(validation_only_ids) == len(set(validation_only_ids)),
        "validation-only source-table references are not unique",
    )
    _require(
        not set(source_ids).intersection(validation_only_ids),
        "a source table cannot be both staged and validation-only",
    )

    source_tables_by_id = {
        item["id"]: item for item in source_table_contract["table_contracts"]
    }
    _require(
        set(source_ids).union(validation_only_ids) == set(source_tables_by_id),
        "staged and validation-only tables do not partition the source-table contract",
    )

    for item in staging_tables:
        source_id = item["source_table_id"]
        _require(source_id in source_tables_by_id, f"unknown source table {source_id}")
        source = source_tables_by_id[source_id]
        _require(
            item["id"] == f"stg_{source_id}"
            and item["output_table_name"] == item["id"],
            f"staging identity is not content-based for {source_id}",
        )
        _require(
            item["expected_source_row_count"] == source["data_row_count"],
            f"source row count differs for {item['id']}",
        )
        _require(
            item["expected_staging_row_count"] == source["data_row_count"],
            f"staging row count must preserve every row for {item['id']}",
        )
        _require(
            item["semantic_key"]["columns"] == source["record_key"]["columns"]
            and item["semantic_key"]["kind"] == source["record_key"]["kind"],
            f"semantic key differs from the source-table contract for {item['id']}",
        )

    if enforce_accepted_tables:
        _require(
            tuple(staging_ids) == EXPECTED_STAGING_TABLE_IDS,
            "staging table set or order differs from the accepted design",
        )
        _require(
            tuple(validation_only_ids) == EXPECTED_VALIDATION_ONLY_TABLE_IDS,
            "validation-only table set or order differs from the accepted design",
        )
        _require(
            staging_contract["source_snapshot_id"] == ACCEPTED_SOURCE_SNAPSHOT_ID,
            "staging contract is not tied to the accepted frozen snapshot",
        )


def validate_observed_table_profile(
    table_contract: dict[str, Any],
    observed_profile: dict[str, Any],
    *,
    expected_source_contract_sha256: str | None = None,
    expected_source_table_contract_sha256: str | None = None,
) -> None:
    """Compare an invented or future observed profile with declared structure."""

    _require(
        observed_profile.get("schema_version") == "1.0.0",
        "observed table profile version is unsupported",
    )
    _require(
        observed_profile.get("profile_type") == "SOURCE_TABLE_STRUCTURE"
        and observed_profile.get("status") == "VALID",
        "observed table profile type or status is invalid",
    )
    _require(
        observed_profile.get("source_snapshot_id") == table_contract["snapshot_id"],
        "observed table profile references a different snapshot",
    )
    if expected_source_contract_sha256 is not None:
        _require(
            observed_profile.get("source_contract_sha256")
            == expected_source_contract_sha256,
            "observed table profile references a different source contract",
        )
    if expected_source_table_contract_sha256 is not None:
        _require(
            observed_profile.get("source_table_contract_sha256")
            == expected_source_table_contract_sha256,
            "observed table profile references a different source-table contract",
        )
    expected = {item["id"]: item for item in table_contract["table_contracts"]}
    observed_tables = observed_profile.get("tables")
    _require(isinstance(observed_tables, list), "observed table profile has no tables array")
    _require(
        observed_profile.get("table_count") == len(observed_tables),
        "observed table profile table_count does not match tables",
    )
    observed = {item.get("id"): item for item in observed_tables}
    _require(
        None not in observed and len(observed) == len(observed_tables),
        "observed table profile has missing or duplicate ids",
    )
    _require(
        set(observed) == set(expected),
        "observed table profile has a missing or unexpected table or sheet",
    )

    structural_fields = (
        "source_id",
        "filename",
        "container",
        "sheet_name",
        "encoding",
        "byte_order_mark",
        "csv_dialect",
        "header_row",
        "data_row_count",
        "header_cell_count",
        "named_column_count",
        "data_row_field_count",
        "unnamed_header_positions",
        "header_sha256",
        "exact_duplicate_rows_beyond_first",
    )
    for table_id, declared in expected.items():
        actual = observed[table_id]
        for field in structural_fields:
            _require(field in actual, f"observed field {field} is missing for {table_id}")
            _require(
                actual[field] == declared[field],
                f"observed {field} differs for {table_id}",
            )

        expected_types = {
            column["name"]: column["parser_type"]
            for column in declared["required_columns"]
        }
        _require(
            actual.get("required_column_types") == expected_types,
            f"required column names or types differ for {table_id}",
        )
        key = declared["record_key"]
        expected_key_evidence = {
            "columns": key["columns"],
            "nonblank_rows": key["expected_nonblank_rows"],
            "distinct_count": key["expected_distinct_count"],
            "duplicate_rows_beyond_first": key[
                "expected_duplicate_rows_beyond_first"
            ],
        }
        _require(
            actual.get("record_key_evidence") == expected_key_evidence,
            f"record-key evidence differs for {table_id}",
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

    from .geography import validate_geography_contract

    config_dir = root / "configs"
    Draft202012Validator.check_schema(
        load_json(config_dir / "source_verification.schema.json")
    )
    Draft202012Validator.check_schema(
        load_json(config_dir / "source_table_profile.schema.json")
    )
    Draft202012Validator.check_schema(
        load_json(config_dir / "staging_checkpoint.schema.json")
    )
    Draft202012Validator.check_schema(
        load_json(config_dir / "staging_build.schema.json")
    )
    Draft202012Validator.check_schema(
        load_json(config_dir / "geography.schema.json")
    )
    Draft202012Validator.check_schema(
        load_json(config_dir / "geography_checkpoint.schema.json")
    )
    sources = load_json(config_dir / "sources.json")
    source_tables = load_json(config_dir / "source_tables.json")
    staging_tables = load_json(config_dir / "staging_tables.json")
    method = load_json(config_dir / "method.json")
    configurations = load_json(config_dir / "configurations.json")
    geography = load_json(config_dir / "geography.json")
    validate_source_contract(sources, load_json(config_dir / "sources.schema.json"))
    validate_source_table_contract(
        source_tables,
        load_json(config_dir / "source_tables.schema.json"),
        sources,
    )
    source_table_hash = sha256_file(config_dir / "source_tables.json")
    validate_staging_contract(
        staging_tables,
        load_json(config_dir / "staging_tables.schema.json"),
        source_tables,
        source_table_hash,
    )
    validate_method_contract(method, load_json(config_dir / "method.schema.json"))
    method_hash = sha256_file(config_dir / "method.json")
    validate_configuration_manifest(
        configurations,
        load_json(config_dir / "configurations.schema.json"),
        method,
        method_hash,
    )
    validate_geography_contract(
        geography,
        load_json(config_dir / "geography.schema.json"),
    )
    return {
        "source_snapshot_id": sources["snapshot_id"],
        "source_contract_sha256": sha256_file(config_dir / "sources.json"),
        "source_table_contract_sha256": source_table_hash,
        "source_table_count": source_tables["expected_table_count"],
        "staging_table_contract_sha256": sha256_file(
            config_dir / "staging_tables.json"
        ),
        "staging_checkpoint_schema_sha256": sha256_file(
            config_dir / "staging_checkpoint.schema.json"
        ),
        "staging_build_schema_sha256": sha256_file(
            config_dir / "staging_build.schema.json"
        ),
        "staging_table_count": staging_tables["expected_staging_table_count"],
        "method_contract_sha256": method_hash,
        "configuration_manifest_sha256": sha256_file(
            config_dir / "configurations.json"
        ),
        "configuration_count": configurations["configuration_count"],
        "primary_configuration_count": configurations["primary_configuration_count"],
        "geography_contract_sha256": sha256_file(config_dir / "geography.json"),
        "geography_schema_sha256": sha256_file(
            config_dir / "geography.schema.json"
        ),
        "geography_checkpoint_schema_sha256": sha256_file(
            config_dir / "geography_checkpoint.schema.json"
        ),
        "geography_source_table_count": len(geography["source_rules"]),
    }
