"""Profile and validate frozen source-table structure without transforming rows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healthcare_resilience.contracts import (  # noqa: E402
    ContractError,
    load_json,
    validate_observed_table_profile,
    validate_schema,
    validate_source_contract,
    validate_source_table_contract,
)
from healthcare_resilience.hashing import sha256_file  # noqa: E402
from healthcare_resilience.snapshot import (  # noqa: E402
    validate_verification_report,
    verify_frozen_snapshot,
)
from healthcare_resilience.source_profiling import (  # noqa: E402
    SourceTableProfilingError,
    profile_source_tables,
    write_source_table_profile,
)

DATA_ROOT_ENV = "HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the frozen snapshot, then profile only contracted CSV and "
            "XLSX structure. No normalized or analytical records are written."
        )
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help=f"Private data root; defaults to ${DATA_ROOT_ENV}.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Private profile path; defaults under DATA_ROOT/verification/<snapshot-id>/.",
    )
    args = parser.parse_args()
    if args.data_root is None:
        value = os.environ.get(DATA_ROOT_ENV)
        if not value:
            parser.error(f"--data-root or {DATA_ROOT_ENV} is required")
        args.data_root = Path(value)
    return args


def main() -> int:
    args = parse_args()
    config_dir = ROOT / "configs"
    source_path = config_dir / "sources.json"
    table_path = config_dir / "source_tables.json"
    source_contract = load_json(source_path)
    table_contract = load_json(table_path)
    validate_source_contract(
        source_contract, load_json(config_dir / "sources.schema.json")
    )
    validate_source_table_contract(
        table_contract,
        load_json(config_dir / "source_tables.schema.json"),
        source_contract,
    )
    source_hash = sha256_file(source_path)
    table_hash = sha256_file(table_path)

    verification = verify_frozen_snapshot(args.data_root, source_contract, source_hash)
    validate_verification_report(verification)
    if verification["status"] != "VALID":
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "stage": "snapshot_verification",
                    "source_snapshot_id": source_contract["snapshot_id"],
                    "failure_count": verification["failure_count"],
                },
                indent=2,
            )
        )
        return 1

    snapshot_root = args.data_root / "snapshots" / source_contract["snapshot_id"]
    raw_root = snapshot_root / "raw"
    try:
        profile = profile_source_tables(
            raw_root,
            table_contract,
            source_hash,
            table_hash,
        )
        validate_schema(
            profile,
            load_json(config_dir / "source_table_profile.schema.json"),
            "source-table profile",
        )
        validate_observed_table_profile(
            table_contract,
            profile,
            expected_source_contract_sha256=source_hash,
            expected_source_table_contract_sha256=table_hash,
        )
    except (ContractError, SourceTableProfilingError) as error:
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "stage": "source_table_profile",
                    "source_snapshot_id": source_contract["snapshot_id"],
                    "error": str(error),
                },
                indent=2,
            )
        )
        return 1

    report_path = args.report or (
        args.data_root
        / "verification"
        / source_contract["snapshot_id"]
        / "source_table_profile.json"
    )
    if report_path.resolve().is_relative_to(snapshot_root.resolve()):
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "stage": "report_path",
                    "source_snapshot_id": source_contract["snapshot_id"],
                    "error": "profile report cannot be written inside the immutable snapshot",
                },
                indent=2,
            )
        )
        return 1
    write_source_table_profile(report_path, profile)
    print(
        json.dumps(
            {
                "status": "valid",
                "source_snapshot_id": source_contract["snapshot_id"],
                "source_contract_sha256": source_hash,
                "source_table_contract_sha256": table_hash,
                "profile_sha256": sha256_file(report_path),
                "table_count": profile["table_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
