"""Hash-only verification for an immutable private source snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_file


class SnapshotVerificationInvariantError(ValueError):
    """Raised when a verification report contradicts its own evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotVerificationInvariantError(message)


def _failure(code: str, relative_path: str, detail: str) -> dict[str, str]:
    return {
        "code": code,
        "relative_path": relative_path,
        "detail": detail,
    }


def verify_frozen_snapshot(
    data_root: Path,
    source_contract: dict[str, Any],
    source_contract_sha256: str,
) -> dict[str, Any]:
    """Verify names, sizes, and hashes without parsing any source file."""

    snapshot_id = source_contract["snapshot_id"]
    snapshot_root = data_root / "snapshots" / snapshot_id
    raw_root = snapshot_root / "raw"
    expected_by_id = {
        item["id"]: item for item in source_contract["source_files"]
    }
    ordered_expected = [
        expected_by_id[source_id]
        for source_id in source_contract["snapshot_identity_order"]
    ]
    expected_paths = {
        item["private_relative_path"] for item in ordered_expected
    }
    failures: list[dict[str, str]] = []

    if not data_root.is_dir():
        failures.append(
            _failure("DATA_ROOT_MISSING", "", "configured data root is not a directory")
        )
    elif not snapshot_root.is_dir():
        failures.append(
            _failure(
                "SNAPSHOT_DIRECTORY_MISSING",
                f"snapshots/{snapshot_id}",
                "accepted snapshot directory is missing",
            )
        )

    observed_paths: set[str] = set()
    unsafe_paths: set[str] = set()
    if raw_root.is_symlink():
        unsafe_paths.add("raw")
    elif raw_root.is_dir():
        for path in raw_root.rglob("*"):
            relative_path = path.relative_to(snapshot_root).as_posix()
            if path.is_symlink():
                unsafe_paths.add(relative_path)
            elif path.is_file():
                observed_paths.add(relative_path)
    elif snapshot_root.is_dir():
        failures.append(
            _failure("RAW_DIRECTORY_MISSING", "raw", "snapshot raw directory is missing")
        )

    for relative_path in sorted(unsafe_paths):
        failures.append(
            _failure(
                "SYMLINK_NOT_ALLOWED",
                relative_path,
                "snapshot verification does not follow symbolic links",
            )
        )
    for relative_path in sorted(observed_paths - expected_paths):
        failures.append(
            _failure(
                "EXTRA_FILE",
                relative_path,
                "file is not declared in the accepted source contract",
            )
        )

    file_results: list[dict[str, Any]] = []
    verified_count = 0
    for expected in ordered_expected:
        relative_path = expected["private_relative_path"]
        path = snapshot_root / Path(relative_path)
        result: dict[str, Any] = {
            "source_id": expected["id"],
            "relative_path": relative_path,
            "expected_bytes": expected["bytes"],
            "observed_bytes": None,
            "expected_sha256": expected["sha256"],
            "observed_sha256": None,
            "status": "MISSING",
        }
        if relative_path in unsafe_paths:
            result["status"] = "SYMLINK_NOT_ALLOWED"
        elif relative_path not in observed_paths:
            failures.append(
                _failure(
                    "MISSING_FILE",
                    relative_path,
                    "required frozen source file is missing",
                )
            )
        else:
            observed_bytes = path.stat().st_size
            observed_sha256 = sha256_file(path)
            size_matches = observed_bytes == expected["bytes"]
            hash_matches = observed_sha256 == expected["sha256"]
            result["observed_bytes"] = observed_bytes
            result["observed_sha256"] = observed_sha256
            if size_matches and hash_matches:
                result["status"] = "VALID"
                verified_count += 1
            elif not size_matches and not hash_matches:
                result["status"] = "SIZE_AND_HASH_MISMATCH"
            elif not size_matches:
                result["status"] = "SIZE_MISMATCH"
            else:
                result["status"] = "HASH_MISMATCH"
            if not size_matches:
                failures.append(
                    _failure(
                        "SIZE_MISMATCH",
                        relative_path,
                        f"expected {expected['bytes']} bytes; observed {observed_bytes}",
                    )
                )
            if not hash_matches:
                failures.append(
                    _failure(
                        "HASH_MISMATCH",
                        relative_path,
                        "observed SHA-256 differs from the accepted source contract",
                    )
                )
        file_results.append(result)

    status = "VALID" if not failures else "INVALID"
    return {
        "schema_version": "1.0.0",
        "verification_type": "FROZEN_SOURCE_SNAPSHOT",
        "status": status,
        "source_snapshot_id": snapshot_id,
        "source_contract_sha256": source_contract_sha256,
        "expected_file_count": len(expected_paths),
        "observed_file_count": len(observed_paths),
        "verified_file_count": verified_count,
        "failure_count": len(failures),
        "files": file_results,
        "failures": failures,
    }


def validate_verification_report(report: dict[str, Any]) -> None:
    """Reject inconsistent counts or status claims in a generated report."""

    files = report["files"]
    failures = report["failures"]
    verified_count = sum(item["status"] == "VALID" for item in files)
    _require(
        report["expected_file_count"] == len(files),
        "expected_file_count does not match file results",
    )
    _require(
        report["verified_file_count"] == verified_count,
        "verified_file_count does not match VALID file results",
    )
    _require(
        report["failure_count"] == len(failures),
        "failure_count does not match failure records",
    )
    _require(
        len({item["source_id"] for item in files}) == len(files),
        "verification report contains duplicate source ids",
    )
    _require(
        len({item["relative_path"] for item in files}) == len(files),
        "verification report contains duplicate file paths",
    )
    expected_status = "VALID" if not failures else "INVALID"
    _require(
        report["status"] == expected_status,
        "verification status contradicts failure records",
    )


def write_verification_report(path: Path, report: dict[str, Any]) -> None:
    """Atomically write a deterministic report outside the source snapshot."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    text = json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2)
    temporary_path.write_text(f"{text}\n", encoding="utf-8", newline="\n")
    temporary_path.replace(path)
