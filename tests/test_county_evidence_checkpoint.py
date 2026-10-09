from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from healthcare_resilience.contracts import load_json
from healthcare_resilience.county_evidence import build_county_evidence
from healthcare_resilience.county_evidence_checkpoint import (
    ARTIFACT_FILENAME,
    CountyEvidenceCheckpointError,
    EvidenceInputIdentity,
    verify_county_evidence_checkpoint,
    validate_county_evidence_rows,
    write_county_evidence_checkpoint,
)
from healthcare_resilience.hashing import sha256_file
from healthcare_resilience.staging_build import StagingBuildError
from tests.county_evidence_support import (
    CONFIG_DIR,
    ROOT,
    synthetic_county_evidence_contract,
    synthetic_county_evidence_inputs,
)

COMMIT = "a" * 40
LOCK = "b" * 64
ENVIRONMENT = {"python_version": "invented", "dependencies": {"duckdb": "invented"}}


def _identity(contract: dict) -> EvidenceInputIdentity:
    return EvidenceInputIdentity(
        contract["input_staging_build_identity"],
        contract["input_staging_build_manifest_file_sha256"],
        contract["input_staging_checkpoint_manifest_canonical_sha256"],
        contract["input_staging_checkpoint_manifest_file_sha256"],
        contract["input_geography_checkpoint_identity"],
        contract["input_geography_manifest_canonical_sha256"],
        contract["input_geography_manifest_file_sha256"],
    )


def _case(monkeypatch: pytest.MonkeyPatch) -> tuple[list[dict], dict, dict, str]:
    contract = synthetic_county_evidence_contract()
    staging, geography = synthetic_county_evidence_inputs()
    rows = build_county_evidence(staging, geography, contract)
    schema = load_json(CONFIG_DIR / "county_evidence_checkpoint.schema.json")
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_checkpoint.capture_repository_identity",
        lambda _: COMMIT,
    )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_checkpoint.capture_environment_identity",
        lambda _: (LOCK, ENVIRONMENT),
    )
    return rows, contract, schema, "c" * 64


def _write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "output"):
    rows, contract, schema, contract_hash = _case(monkeypatch)
    output, manifest = write_county_evidence_checkpoint(
        tmp_path / name,
        rows,
        contract,
        contract_hash,
        schema,
        ROOT,
        lambda: _identity(contract),
    )
    return output, manifest, contract, schema, contract_hash


def test_checkpoint_is_two_files_and_independently_verifiable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, manifest, contract, schema, contract_hash = _write(tmp_path, monkeypatch)
    assert {path.name for path in output.iterdir()} == {
        "county_evidence_manifest.json", ARTIFACT_FILENAME
    }
    assert manifest["artifact_count"] == 1
    assert manifest["artifact"]["row_count"] == 4
    verify_county_evidence_checkpoint(output, manifest, schema, contract, contract_hash)


def test_two_fresh_checkpoints_have_identical_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, manifest_a, _, _, _ = _write(tmp_path, monkeypatch, "one")
    second, manifest_b, _, _, _ = _write(tmp_path, monkeypatch, "two")
    assert first.name == second.name
    assert manifest_a == manifest_b
    assert sha256_file(first / ARTIFACT_FILENAME) == sha256_file(second / ARTIFACT_FILENAME)


def test_existing_output_and_dirty_repository_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, monkeypatch)
    rows, contract, schema, contract_hash = _case(monkeypatch)
    with pytest.raises(CountyEvidenceCheckpointError, match="already exists"):
        write_county_evidence_checkpoint(
            tmp_path / "output", rows, contract, contract_hash, schema, ROOT,
            lambda: _identity(contract),
        )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_checkpoint.capture_repository_identity",
        lambda _: (_ for _ in ()).throw(StagingBuildError("repository working tree is not clean")),
    )
    with pytest.raises(CountyEvidenceCheckpointError, match="not clean"):
        write_county_evidence_checkpoint(
            tmp_path / "dirty", rows, contract, contract_hash, schema, ROOT,
            lambda: _identity(contract),
        )


def test_input_mutation_during_write_fails_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows, contract, schema, contract_hash = _case(monkeypatch)
    accepted = _identity(contract)
    changed = accepted._replace(geography_manifest_file_sha256="d" * 64)
    identities = iter([accepted, changed])
    root = tmp_path / "mutated"
    with pytest.raises(CountyEvidenceCheckpointError, match="changed during"):
        write_county_evidence_checkpoint(
            root, rows, contract, contract_hash, schema, ROOT,
            lambda: next(identities),
        )
    assert not list(root.glob("*"))


def test_artifact_manifest_and_extra_file_tampering_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, manifest, contract, schema, contract_hash = _write(tmp_path, monkeypatch)
    (output / "extra.txt").write_text("invented", encoding="utf-8")
    with pytest.raises(CountyEvidenceCheckpointError, match="membership differs"):
        verify_county_evidence_checkpoint(output, manifest, schema, contract, contract_hash)
    (output / "extra.txt").unlink()
    artifact = output / ARTIFACT_FILENAME
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(CountyEvidenceCheckpointError, match="byte count differs"):
        verify_county_evidence_checkpoint(output, manifest, schema, contract, contract_hash)


def test_manifest_identity_mutation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, manifest, contract, schema, contract_hash = _write(tmp_path, monkeypatch)
    changed = deepcopy(manifest)
    changed["checkpoint_identity_inputs"]["method_contract_sha256"] = "e" * 64
    with pytest.raises(CountyEvidenceCheckpointError, match="identity differs"):
        verify_county_evidence_checkpoint(output, changed, schema, contract, contract_hash)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("hhs_dme_ambiguous_11", False, "HHS evidence semantics differ"),
        ("site_status_counts_json", '{"Active": 2}', "encoding is not canonical"),
        ("fema_tsun_risk_score", 0.0, "Not Applicable hazard score must remain null"),
    ],
)
def test_independent_row_semantics_reject_mutation(
    monkeypatch: pytest.MonkeyPatch, field: str, value, message: str
) -> None:
    rows, contract, _, _ = _case(monkeypatch)
    changed = deepcopy(rows)
    target = next(row for row in changed if row["canonical_fips"] == "88001")
    if field == "fema_tsun_risk_score":
        target = next(row for row in changed if row["canonical_fips"] == "88003")
    target[field] = value
    with pytest.raises(CountyEvidenceCheckpointError, match=message):
        validate_county_evidence_rows(changed, contract)
