"""Verify the private frozen snapshot without parsing source records."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healthcare_resilience.contracts import (  # noqa: E402
    load_json,
    validate_schema,
    validate_source_contract,
)
from healthcare_resilience.hashing import sha256_file  # noqa: E402
from healthcare_resilience.snapshot import (  # noqa: E402
    validate_verification_report,
    verify_frozen_snapshot,
    write_verification_report,
)

DATA_ROOT_ENV = "HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the accepted frozen source files by exact name, size, and SHA-256. "
            "The command does not parse source records."
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
        help="Private report path; defaults under DATA_ROOT/verification/<snapshot-id>/.",
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
    source_contract = load_json(source_path)
    validate_source_contract(
        source_contract, load_json(config_dir / "sources.schema.json")
    )
    source_contract_hash = sha256_file(source_path)
    report = verify_frozen_snapshot(
        args.data_root, source_contract, source_contract_hash
    )
    validate_verification_report(report)
    validate_schema(
        report,
        load_json(config_dir / "source_verification.schema.json"),
        "source verification report",
    )

    report_path = args.report or (
        args.data_root
        / "verification"
        / source_contract["snapshot_id"]
        / "source_verification.json"
    )
    write_verification_report(report_path, report)
    summary = {
        "status": report["status"].lower(),
        "source_snapshot_id": report["source_snapshot_id"],
        "source_contract_sha256": source_contract_hash,
        "report_sha256": sha256_file(report_path),
        "expected_file_count": report["expected_file_count"],
        "observed_file_count": report["observed_file_count"],
        "verified_file_count": report["verified_file_count"],
        "failure_count": report["failure_count"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if report["status"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
