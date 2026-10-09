from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook

from healthcare_resilience.contracts import load_json
from healthcare_resilience.hashing import (
    sha256_file,
    source_snapshot_identity,
)
from healthcare_resilience import staging_build
from healthcare_resilience.staging_build import (
    StagingBuildError,
    _run_staging_build,
    capture_environment_identity,
    capture_repository_identity,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
SYNTHETIC_COMMIT = "a" * 40


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        f"{json.dumps(value, indent=2)}\n",
        encoding="utf-8",
        newline="\n",
    )


@pytest.fixture
def synthetic_build_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    material = tmp_path / "invented_source_material"
    material.mkdir()
    csv_path = material / "synthetic_measurements.csv"
    csv_path.write_bytes(
        b"unit_id,amount\n01001,11\n02020,\n03030,4.50\n"
    )
    workbook_path = material / "synthetic_regions.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Regions"
    sheet.append(["region_id", "label"])
    sheet.append(["R-01", "Not Applicable"])
    sheet.append(["R-01", "Different Context"])
    workbook.save(workbook_path)
    workbook.close()

    source_contract = load_json(FIXTURE_DIR / "synthetic_source_contract.json")
    source_files = deepcopy(source_contract["source_files"])
    source_files[0].update(
        {
            "id": "synthetic_csv_source",
            "filename": csv_path.name,
            "private_relative_path": f"raw/{csv_path.name}",
            "bytes": csv_path.stat().st_size,
            "sha256": sha256_file(csv_path),
            "media_type": "text/csv",
        }
    )
    source_files[1].update(
        {
            "id": "synthetic_workbook_source",
            "filename": workbook_path.name,
            "private_relative_path": f"raw/{workbook_path.name}",
            "bytes": workbook_path.stat().st_size,
            "sha256": sha256_file(workbook_path),
            "media_type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "role": "CONTEXT_INPUT",
        }
    )
    source_contract["source_files"] = source_files
    source_contract["snapshot_identity_order"] = [
        "synthetic_csv_source",
        "synthetic_workbook_source",
    ]
    source_contract["snapshot_id"] = source_snapshot_identity(source_files)

    data_root = tmp_path / "private_data"
    raw_root = (
        data_root / "snapshots" / source_contract["snapshot_id"] / "raw"
    )
    raw_root.mkdir(parents=True)
    shutil.copy2(csv_path, raw_root / csv_path.name)
    shutil.copy2(workbook_path, raw_root / workbook_path.name)

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    for name in (
        "sources.schema.json",
        "source_tables.schema.json",
        "staging_tables.schema.json",
        "source_table_profile.schema.json",
        "staging_checkpoint.schema.json",
        "staging_build.schema.json",
    ):
        shutil.copy2(CONFIG_DIR / name, config_dir / name)
    _write_json(config_dir / "sources.json", source_contract)

    source_table_contract = load_json(
        FIXTURE_DIR / "synthetic_source_table_contract.json"
    )
    source_table_contract["snapshot_id"] = source_contract["snapshot_id"]
    _write_json(config_dir / "source_tables.json", source_table_contract)
    source_table_hash = sha256_file(config_dir / "source_tables.json")

    staging_contract = load_json(FIXTURE_DIR / "synthetic_staging_contract.json")
    staging_contract["source_snapshot_id"] = source_contract["snapshot_id"]
    staging_contract["source_table_contract_sha256"] = source_table_hash
    _write_json(config_dir / "staging_tables.json", staging_contract)

    monkeypatch.setattr(
        staging_build,
        "capture_repository_identity",
        lambda repository_root: SYNTHETIC_COMMIT,
    )
    return data_root, config_dir


def _run_synthetic_build(
    data_root: Path, config_dir: Path
) -> tuple[Path, dict]:
    return _run_staging_build(
        data_root,
        ROOT,
        config_dir=config_dir,
        enforce_accepted_contracts=False,
    )


def test_frozen_build_is_content_addressed_complete_and_path_neutral(
    synthetic_build_inputs: tuple[Path, Path],
) -> None:
    data_root, config_dir = synthetic_build_inputs

    output, manifest = _run_synthetic_build(data_root, config_dir)

    assert output == (
        data_root
        / "checkpoints"
        / manifest["build_identity_inputs"]["source_snapshot_id"]
        / "source_preserving_staging"
        / manifest["build_identity"]
    )
    assert manifest["status"] == "COMPLETE"
    assert manifest["build_identity_inputs"]["code_commit"] == SYNTHETIC_COMMIT
    assert manifest["snapshot_verification"]["reports_identical"] is True
    assert manifest["checkpoint"]["table_count"] == 2
    assert manifest["checkpoint"]["total_row_count"] == 5
    assert manifest["independent_verification"] is True
    assert load_json(output / "staging_build_manifest.json") == manifest
    assert str(data_root) not in json.dumps(manifest)


def test_frozen_build_refuses_existing_content_addressed_output(
    synthetic_build_inputs: tuple[Path, Path],
) -> None:
    data_root, config_dir = synthetic_build_inputs
    output, _ = _run_synthetic_build(data_root, config_dir)

    with pytest.raises(StagingBuildError, match="already exists"):
        _run_synthetic_build(data_root, config_dir)

    assert output.is_dir()


def test_frozen_build_detects_source_change_between_verifications(
    synthetic_build_inputs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root, config_dir = synthetic_build_inputs
    original = staging_build.extract_staging_tables_from_files

    def extract_then_change(*args: object, **kwargs: object) -> dict:
        rows = original(*args, **kwargs)
        raw_root = args[0]
        assert isinstance(raw_root, Path)
        path = raw_root / "synthetic_measurements.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        return rows

    monkeypatch.setattr(
        staging_build,
        "extract_staging_tables_from_files",
        extract_then_change,
    )

    with pytest.raises(StagingBuildError, match="post-build source snapshot"):
        _run_synthetic_build(data_root, config_dir)

    checkpoint_root = data_root / "checkpoints"
    assert not list(checkpoint_root.rglob("staging_build_manifest.json"))
    assert not list(checkpoint_root.rglob(".*.tmp-*"))


def test_frozen_build_detects_repository_commit_change_and_cleans_output(
    synthetic_build_inputs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root, config_dir = synthetic_build_inputs
    commits = iter((SYNTHETIC_COMMIT, "b" * 40))
    monkeypatch.setattr(
        staging_build,
        "capture_repository_identity",
        lambda repository_root: next(commits),
    )

    with pytest.raises(StagingBuildError, match="commit changed"):
        _run_synthetic_build(data_root, config_dir)

    checkpoint_root = data_root / "checkpoints"
    assert not list(checkpoint_root.rglob("staging_build_manifest.json"))
    assert not list(checkpoint_root.rglob(".*.tmp-*"))


def test_repository_identity_rejects_dirty_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = {
        ("rev-parse", "--is-inside-work-tree"): "true",
        ("status", "--porcelain=v1", "--untracked-files=all"): " M tracked.py",
    }
    monkeypatch.setattr(
        staging_build,
        "_run_git",
        lambda repository_root, *arguments: responses[arguments],
    )

    with pytest.raises(StagingBuildError, match="not clean"):
        capture_repository_identity(tmp_path)


def test_git_identity_uses_command_scoped_safe_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["cwd"] = kwargs["cwd"]
        return type("Result", (), {"stdout": "true\n"})()

    monkeypatch.setattr(staging_build.subprocess, "run", fake_run)
    assert staging_build._run_git(tmp_path, "rev-parse", "--is-inside-work-tree") == "true"
    assert observed["command"] == [
        "git",
        "-c",
        f"safe.directory={tmp_path.resolve().as_posix()}",
        "rev-parse",
        "--is-inside-work-tree",
    ]
    assert observed["cwd"] == tmp_path


def test_environment_identity_rejects_direct_dependency_lock_drift(
    tmp_path: Path,
) -> None:
    lock_text = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    (tmp_path / "requirements-lock.txt").write_text(
        lock_text.replace("duckdb==1.5.5", "duckdb==0.0.1"),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(StagingBuildError, match="duckdb version differs"):
        capture_environment_identity(tmp_path)
