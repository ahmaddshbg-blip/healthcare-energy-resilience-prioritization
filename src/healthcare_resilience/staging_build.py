"""Fail-closed orchestration for a frozen source-preserving staging build."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import (
    load_json,
    validate_observed_table_profile,
    validate_schema,
    validate_source_contract,
    validate_source_table_contract,
    validate_staging_contract,
)
from .hashing import sha256_file, sha256_json
from .snapshot import validate_verification_report, verify_frozen_snapshot
from .source_adapters import extract_staging_tables_from_files
from .source_profiling import profile_source_tables
from .staging_checkpoint import (
    MANIFEST_FILENAME as CHECKPOINT_MANIFEST_FILENAME,
    verify_staging_checkpoint_artifacts,
    write_staging_checkpoint,
)

BUILD_MANIFEST_FILENAME = "staging_build_manifest.json"
EXECUTION_MODE = "FROZEN_SOURCE_PRESERVING_STAGING"
DIRECT_DEPENDENCIES = ("duckdb", "jsonschema", "numpy", "openpyxl", "pandas")


class StagingBuildError(ValueError):
    """Raised when a frozen staging build cannot satisfy every control."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StagingBuildError(message)


def _run_git(repository_root: Path, *arguments: str) -> str:
    safe_directory = repository_root.resolve().as_posix()
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={safe_directory}", *arguments],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise StagingBuildError(
            f"git {' '.join(arguments)} failed for repository identity"
        ) from error
    return result.stdout.strip()


def capture_repository_identity(repository_root: Path) -> str:
    """Return HEAD only when the repository is committed and completely clean."""

    _require(repository_root.is_dir(), "repository root is missing")
    _require(
        _run_git(repository_root, "rev-parse", "--is-inside-work-tree") == "true",
        "build path is not a Git working tree",
    )
    _require(
        not _run_git(
            repository_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        "repository working tree is not clean",
    )
    commit = _run_git(repository_root, "rev-parse", "HEAD")
    _require(
        len(commit) == 40
        and all(character in "0123456789abcdef" for character in commit),
        "repository HEAD is not a full lowercase commit identity",
    )
    return commit


def capture_environment_identity(repository_root: Path) -> tuple[str, dict[str, Any]]:
    """Return the dependency-lock hash and path-neutral runtime identity."""

    lock_path = repository_root / "requirements-lock.txt"
    _require(lock_path.is_file(), "requirements lock is missing")
    _require(
        (3, 11) <= sys.version_info[:2] < (3, 14),
        "Python version is outside the supported 3.11-3.13 range",
    )
    locked_versions: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        _require("==" in line, "requirements lock contains an unpinned entry")
        package, locked_version = line.split("==", maxsplit=1)
        locked_versions[package.lower()] = locked_version
    dependencies: dict[str, str] = {}
    for package in DIRECT_DEPENDENCIES:
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError as error:
            raise StagingBuildError(
                f"required package {package} is not installed"
            ) from error
        _require(
            locked_versions.get(package) == dependencies[package],
            f"installed {package} version differs from requirements lock",
        )
    environment = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "dependencies": dependencies,
    }
    return sha256_file(lock_path), environment


def _write_json(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2)
    path.write_text(f"{text}\n", encoding="utf-8", newline="\n")


def _checkpoint_summary(
    checkpoint_directory: Path, checkpoint_manifest: dict[str, Any]
) -> dict[str, Any]:
    manifest_path = checkpoint_directory / CHECKPOINT_MANIFEST_FILENAME
    return {
        "relative_path": "checkpoint",
        "manifest_canonical_sha256": sha256_json(checkpoint_manifest),
        "manifest_file_sha256": sha256_file(manifest_path),
        "table_count": checkpoint_manifest["table_count"],
        "total_row_count": checkpoint_manifest["total_row_count"],
        "tables": [
            {
                "staging_table_id": table["staging_table_id"],
                "canonical_content_sha256": table["canonical_content_sha256"],
                "schema_sha256": table["schema_sha256"],
                "artifact_sha256": table["artifact_sha256"],
            }
            for table in checkpoint_manifest["tables"]
        ],
    }


def validate_staging_build_manifest(
    manifest: dict[str, Any],
    manifest_schema: dict[str, Any],
    pre_verification: dict[str, Any],
    post_verification: dict[str, Any],
    source_table_profile: dict[str, Any],
    checkpoint_manifest: dict[str, Any],
    checkpoint_directory: Path,
) -> None:
    """Validate build identity and every evidence reference semantically."""

    validate_schema(manifest, manifest_schema, "staging build manifest")
    identity_inputs = manifest["build_identity_inputs"]
    _require(
        manifest["build_identity"] == sha256_json(identity_inputs),
        "staging build identity differs from its canonical inputs",
    )
    _require(
        identity_inputs["repository_clean"] is True,
        "staging build does not claim a clean repository",
    )
    _require(
        pre_verification["status"] == post_verification["status"] == "VALID"
        and pre_verification["failure_count"] == post_verification["failure_count"] == 0,
        "staging build references an invalid snapshot verification",
    )
    _require(
        pre_verification == post_verification,
        "source snapshot changed between pre- and post-build verification",
    )
    _require(
        identity_inputs["source_snapshot_id"]
        == pre_verification["source_snapshot_id"]
        == source_table_profile["source_snapshot_id"]
        == checkpoint_manifest["source_snapshot_id"],
        "staging build snapshot identities are inconsistent",
    )
    _require(
        identity_inputs["source_contract_sha256"]
        == pre_verification["source_contract_sha256"]
        == source_table_profile["source_contract_sha256"]
        == checkpoint_manifest["source_contract_sha256"],
        "staging build source-contract identities are inconsistent",
    )
    _require(
        identity_inputs["source_table_contract_sha256"]
        == source_table_profile["source_table_contract_sha256"]
        == checkpoint_manifest["source_table_contract_sha256"],
        "staging build source-table-contract identities are inconsistent",
    )
    _require(
        identity_inputs["staging_table_contract_sha256"]
        == checkpoint_manifest["staging_table_contract_sha256"],
        "staging build staging-contract identities are inconsistent",
    )
    verification = manifest["snapshot_verification"]
    expected_verification_hash = sha256_json(pre_verification)
    _require(
        verification["pre_build_report_sha256"] == expected_verification_hash
        and verification["post_build_report_sha256"] == expected_verification_hash,
        "snapshot verification hashes differ from generated reports",
    )
    _require(
        verification["expected_file_count"]
        == pre_verification["expected_file_count"]
        and verification["verified_file_count"]
        == pre_verification["verified_file_count"],
        "snapshot verification counts differ from generated reports",
    )
    _require(
        manifest["source_table_profile"]
        == {
            "canonical_sha256": sha256_json(source_table_profile),
            "table_count": source_table_profile["table_count"],
        },
        "source-table profile evidence differs from generated profile",
    )
    _require(
        manifest["checkpoint"]
        == _checkpoint_summary(checkpoint_directory, checkpoint_manifest),
        "checkpoint evidence differs from generated checkpoint",
    )


def verify_staging_build_artifacts(
    build_directory: Path,
    build_manifest: dict[str, Any],
    build_manifest_schema: dict[str, Any],
    checkpoint_manifest: dict[str, Any],
    checkpoint_manifest_schema: dict[str, Any],
    source_profile_schema: dict[str, Any],
    staging_contract: dict[str, Any],
    source_table_contract: dict[str, Any],
    source_contract_sha256: str,
    staging_contract_sha256: str,
    pre_verification: dict[str, Any],
    post_verification: dict[str, Any],
    source_table_profile: dict[str, Any],
) -> None:
    """Verify one complete private build without trusting producer assertions."""

    _require(build_directory.is_dir(), "staging build directory is missing")
    build_manifest_path = build_directory / BUILD_MANIFEST_FILENAME
    try:
        stored_manifest = load_json(build_manifest_path)
    except (OSError, json.JSONDecodeError) as error:
        raise StagingBuildError("staging build manifest cannot be read") from error
    _require(
        stored_manifest == build_manifest,
        "stored staging build manifest differs from validated manifest",
    )
    validate_verification_report(pre_verification)
    validate_verification_report(post_verification)
    validate_schema(
        source_table_profile,
        source_profile_schema,
        "source-table profile",
    )
    validate_observed_table_profile(
        source_table_contract,
        source_table_profile,
        expected_source_contract_sha256=source_contract_sha256,
        expected_source_table_contract_sha256=checkpoint_manifest[
            "source_table_contract_sha256"
        ],
    )
    checkpoint_directory = build_directory / "checkpoint"
    validate_staging_build_manifest(
        build_manifest,
        build_manifest_schema,
        pre_verification,
        post_verification,
        source_table_profile,
        checkpoint_manifest,
        checkpoint_directory,
    )
    expected_files = {BUILD_MANIFEST_FILENAME}
    expected_files.add(f"checkpoint/{CHECKPOINT_MANIFEST_FILENAME}")
    expected_files.update(
        f"checkpoint/{table['relative_path']}"
        for table in checkpoint_manifest["tables"]
    )
    observed_files = {
        path.relative_to(build_directory).as_posix()
        for path in build_directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    _require(
        observed_files == expected_files,
        "staging build contains missing or unexpected files",
    )
    _require(
        not any(path.is_symlink() for path in build_directory.rglob("*")),
        "staging build contains a symbolic link",
    )
    verify_staging_checkpoint_artifacts(
        checkpoint_directory,
        checkpoint_manifest,
        checkpoint_manifest_schema,
        staging_contract,
        source_table_contract,
        source_contract_sha256,
        staging_contract_sha256,
    )


def _run_staging_build(
    data_root: Path,
    repository_root: Path,
    *,
    config_dir: Path,
    enforce_accepted_contracts: bool,
) -> tuple[Path, dict[str, Any]]:
    """Internal implementation shared with contract-safe synthetic tests."""

    repository_root = repository_root.resolve()
    data_root = data_root.resolve()
    _require(
        not data_root.is_relative_to(repository_root),
        "private data root must remain outside the public repository",
    )
    code_commit = capture_repository_identity(repository_root)
    requirements_lock_sha256, environment = capture_environment_identity(
        repository_root
    )
    config_dir = config_dir.resolve()

    source_path = config_dir / "sources.json"
    source_table_path = config_dir / "source_tables.json"
    staging_path = config_dir / "staging_tables.json"
    source_contract = load_json(source_path)
    source_table_contract = load_json(source_table_path)
    staging_contract = load_json(staging_path)
    source_contract_sha256 = sha256_file(source_path)
    source_table_contract_sha256 = sha256_file(source_table_path)
    staging_contract_sha256 = sha256_file(staging_path)
    validate_source_contract(
        source_contract,
        load_json(config_dir / "sources.schema.json"),
        enforce_accepted_snapshot=enforce_accepted_contracts,
    )
    validate_source_table_contract(
        source_table_contract,
        load_json(config_dir / "source_tables.schema.json"),
        source_contract,
        enforce_accepted_tables=enforce_accepted_contracts,
    )
    validate_staging_contract(
        staging_contract,
        load_json(config_dir / "staging_tables.schema.json"),
        source_table_contract,
        source_table_contract_sha256,
        enforce_accepted_tables=enforce_accepted_contracts,
    )
    checkpoint_manifest_schema = load_json(
        config_dir / "staging_checkpoint.schema.json"
    )
    build_manifest_schema = load_json(config_dir / "staging_build.schema.json")
    source_profile_schema = load_json(config_dir / "source_table_profile.schema.json")

    identity_inputs = {
        "execution_mode": EXECUTION_MODE,
        "source_snapshot_id": source_contract["snapshot_id"],
        "source_contract_sha256": source_contract_sha256,
        "source_table_contract_sha256": source_table_contract_sha256,
        "staging_table_contract_sha256": staging_contract_sha256,
        "code_commit": code_commit,
        "repository_clean": True,
        "requirements_lock_sha256": requirements_lock_sha256,
        "environment": environment,
    }
    build_identity = sha256_json(identity_inputs)
    output_directory = (
        data_root
        / "checkpoints"
        / source_contract["snapshot_id"]
        / "source_preserving_staging"
        / build_identity
    )
    _require(not output_directory.exists(), "staging build output already exists")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = output_directory.parent / (
        f".{build_identity}.tmp-{uuid4().hex}"
    )
    temporary_directory.mkdir()

    try:
        pre_verification = verify_frozen_snapshot(
            data_root, source_contract, source_contract_sha256
        )
        validate_verification_report(pre_verification)
        _require(
            pre_verification["status"] == "VALID",
            "pre-build source snapshot verification failed",
        )

        snapshot_root = data_root / "snapshots" / source_contract["snapshot_id"]
        raw_root = snapshot_root / "raw"
        source_table_profile = profile_source_tables(
            raw_root,
            source_table_contract,
            source_contract_sha256,
            source_table_contract_sha256,
        )
        validate_schema(
            source_table_profile,
            source_profile_schema,
            "source-table profile",
        )
        validate_observed_table_profile(
            source_table_contract,
            source_table_profile,
            expected_source_contract_sha256=source_contract_sha256,
            expected_source_table_contract_sha256=source_table_contract_sha256,
        )

        rows_by_staging_table = extract_staging_tables_from_files(
            raw_root, staging_contract, source_table_contract
        )

        checkpoint_directory = temporary_directory / "checkpoint"
        checkpoint_manifest = write_staging_checkpoint(
            checkpoint_directory,
            rows_by_staging_table,
            staging_contract,
            source_table_contract,
            source_contract_sha256,
            staging_contract_sha256,
            checkpoint_manifest_schema,
        )
        verify_staging_checkpoint_artifacts(
            checkpoint_directory,
            checkpoint_manifest,
            checkpoint_manifest_schema,
            staging_contract,
            source_table_contract,
            source_contract_sha256,
            staging_contract_sha256,
        )

        post_verification = verify_frozen_snapshot(
            data_root, source_contract, source_contract_sha256
        )
        validate_verification_report(post_verification)
        _require(
            post_verification["status"] == "VALID",
            "post-build source snapshot verification failed",
        )
        _require(
            pre_verification == post_verification,
            "source snapshot changed between pre- and post-build verification",
        )

        _require(
            capture_repository_identity(repository_root) == code_commit,
            "repository commit changed during staging build",
        )
        verification_hash = sha256_json(pre_verification)
        build_manifest = {
            "schema_version": "1.0.0",
            "manifest_type": "FROZEN_SOURCE_PRESERVING_STAGING_BUILD",
            "status": "COMPLETE",
            "build_identity_algorithm": "SHA256_CANONICAL_BUILD_INPUTS_V1",
            "build_identity": build_identity,
            "build_identity_inputs": identity_inputs,
            "snapshot_verification": {
                "pre_build_report_sha256": verification_hash,
                "post_build_report_sha256": verification_hash,
                "reports_identical": True,
                "expected_file_count": pre_verification["expected_file_count"],
                "verified_file_count": pre_verification["verified_file_count"],
            },
            "source_table_profile": {
                "canonical_sha256": sha256_json(source_table_profile),
                "table_count": source_table_profile["table_count"],
            },
            "checkpoint": _checkpoint_summary(
                checkpoint_directory, checkpoint_manifest
            ),
            "independent_verification": True,
        }
        validate_staging_build_manifest(
            build_manifest,
            build_manifest_schema,
            pre_verification,
            post_verification,
            source_table_profile,
            checkpoint_manifest,
            checkpoint_directory,
        )
        _write_json(temporary_directory / BUILD_MANIFEST_FILENAME, build_manifest)
        verify_staging_build_artifacts(
            temporary_directory,
            build_manifest,
            build_manifest_schema,
            checkpoint_manifest,
            checkpoint_manifest_schema,
            source_profile_schema,
            staging_contract,
            source_table_contract,
            source_contract_sha256,
            staging_contract_sha256,
            pre_verification,
            post_verification,
            source_table_profile,
        )
        os.replace(temporary_directory, output_directory)
        return output_directory, build_manifest
    except Exception:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
        raise


def run_frozen_staging_build(
    data_root: Path,
    repository_root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Build from the repository's accepted contracts with no bypass option."""

    return _run_staging_build(
        data_root,
        repository_root,
        config_dir=repository_root / "configs",
        enforce_accepted_contracts=True,
    )
