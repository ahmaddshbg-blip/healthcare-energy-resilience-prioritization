from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import load_json, validate_schema
from healthcare_resilience.hashing import sha256_file, source_snapshot_identity
from healthcare_resilience.snapshot import (
    SnapshotVerificationInvariantError,
    validate_verification_report,
    verify_frozen_snapshot,
    write_verification_report,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SHA256 = "c" * 64


@pytest.fixture
def frozen_snapshot(tmp_path: Path) -> tuple[Path, dict, dict[str, bytes]]:
    contents = {
        "alpha.csv": b"alpha\n",
        "beta.json": b'{"beta":1}\n',
    }
    source_files = []
    for source_id, filename in (("alpha", "alpha.csv"), ("beta", "beta.json")):
        content = contents[filename]
        source_files.append(
            {
                "id": source_id,
                "filename": filename,
                "private_relative_path": f"raw/{filename}",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    snapshot_id = source_snapshot_identity(source_files)
    contract = {
        "snapshot_id": snapshot_id,
        "snapshot_identity_order": ["alpha", "beta"],
        "source_files": source_files,
    }
    data_root = tmp_path / "private"
    raw_root = data_root / "snapshots" / snapshot_id / "raw"
    raw_root.mkdir(parents=True)
    for filename, content in contents.items():
        (raw_root / filename).write_bytes(content)
    return data_root, contract, contents


def _codes(report: dict) -> set[str]:
    return {failure["code"] for failure in report["failures"]}


def _validate_report(report: dict) -> None:
    schema = load_json(ROOT / "configs" / "source_verification.schema.json")
    validate_schema(report, schema, "synthetic source verification report")
    validate_verification_report(report)


def test_valid_snapshot_matches_exact_contract(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert report["status"] == "VALID"
    assert report["verified_file_count"] == 2
    assert report["failure_count"] == 0
    assert str(data_root) not in json.dumps(report)


def test_missing_file_stops_verification(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    raw_root = data_root / "snapshots" / contract["snapshot_id"] / "raw"
    (raw_root / "alpha.csv").unlink()
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert report["status"] == "INVALID"
    assert "MISSING_FILE" in _codes(report)


def test_extra_file_stops_verification(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    raw_root = data_root / "snapshots" / contract["snapshot_id"] / "raw"
    (raw_root / "undeclared.txt").write_text("extra", encoding="utf-8")
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert report["status"] == "INVALID"
    assert "EXTRA_FILE" in _codes(report)


def test_renamed_file_is_missing_and_extra(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    raw_root = data_root / "snapshots" / contract["snapshot_id"] / "raw"
    (raw_root / "alpha.csv").rename(raw_root / "renamed.csv")
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert {"MISSING_FILE", "EXTRA_FILE"}.issubset(_codes(report))


def test_size_and_hash_mismatch_are_both_reported(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    raw_root = data_root / "snapshots" / contract["snapshot_id"] / "raw"
    (raw_root / "alpha.csv").write_bytes(b"alpha changed\n")
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert {"SIZE_MISMATCH", "HASH_MISMATCH"}.issubset(_codes(report))
    assert report["files"][0]["status"] == "SIZE_AND_HASH_MISMATCH"


def test_same_size_hash_mismatch_is_detected(frozen_snapshot: tuple) -> None:
    data_root, contract, contents = frozen_snapshot
    raw_root = data_root / "snapshots" / contract["snapshot_id"] / "raw"
    replacement = b"ALPHA\n"
    assert len(replacement) == len(contents["alpha.csv"])
    (raw_root / "alpha.csv").write_bytes(replacement)
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    _validate_report(report)
    assert _codes(report) == {"HASH_MISMATCH"}
    assert report["files"][0]["status"] == "HASH_MISMATCH"


def test_report_is_deterministic_and_written_atomically(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    first = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    second = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    assert first == second

    report_path = data_root / "verification" / "source_verification.json"
    write_verification_report(report_path, first)
    first_hash = sha256_file(report_path)
    write_verification_report(report_path, second)
    assert sha256_file(report_path) == first_hash
    assert not report_path.with_name(".source_verification.json.tmp").exists()


def test_inconsistent_report_count_is_rejected(frozen_snapshot: tuple) -> None:
    data_root, contract, _ = frozen_snapshot
    report = verify_frozen_snapshot(data_root, contract, CONTRACT_SHA256)
    changed = deepcopy(report)
    changed["verified_file_count"] = 1
    with pytest.raises(
        SnapshotVerificationInvariantError, match="verified_file_count"
    ):
        validate_verification_report(changed)
