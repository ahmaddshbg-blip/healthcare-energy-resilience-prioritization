from __future__ import annotations

import json
from copy import deepcopy
from inspect import signature
from pathlib import Path

import duckdb
import pytest

from healthcare_resilience.contracts import load_json
from healthcare_resilience.county_evidence import build_county_evidence
from healthcare_resilience.county_evidence_checkpoint import EvidenceInputIdentity
from healthcare_resilience.county_evidence_input import (
    _build_county_evidence_from_verified_inputs,
    CountyEvidenceInputError,
    load_verified_county_evidence_inputs,
    run_frozen_county_evidence_build,
    verify_county_evidence_inputs,
)
from healthcare_resilience.hashing import sha256_file, sha256_json
from healthcare_resilience.geography_checkpoint import StagingInputIdentity
from tests.county_evidence_support import (
    CONFIG_DIR,
    ROOT,
    synthetic_county_evidence_contract,
    synthetic_county_evidence_inputs,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_parquet(path: Path, rows: list[dict]) -> None:
    names = list(rows[0])
    definitions = []
    for name in names:
        values = [row[name] for row in rows if row[name] is not None]
        if not values:
            data_type = "VARCHAR"
        else:
            sample = values[0]
            data_type = (
                "BOOLEAN" if type(sample) is bool else
                "BIGINT" if type(sample) is int else
                "DOUBLE" if type(sample) is float else
                "VARCHAR"
            )
        definitions.append(f'"{name}" {data_type}')
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE TABLE invented ({', '.join(definitions)})")
        connection.executemany(
            f"INSERT INTO invented VALUES ({', '.join('?' for _ in names)})",
            [[row[name] for name in names] for row in rows],
        )
        connection.table("invented").write_parquet(str(path))
    finally:
        connection.close()


def _staging_identity(contract: dict) -> EvidenceInputIdentity:
    return EvidenceInputIdentity(
        contract["input_staging_build_identity"],
        contract["input_staging_build_manifest_file_sha256"],
        contract["input_staging_checkpoint_manifest_canonical_sha256"],
        contract["input_staging_checkpoint_manifest_file_sha256"],
        contract["input_geography_checkpoint_identity"],
        contract["input_geography_manifest_canonical_sha256"],
        contract["input_geography_manifest_file_sha256"],
    )


def _invented_geography_manifest(contract: dict) -> dict:
    return {
        "checkpoint_identity": contract["input_geography_checkpoint_identity"],
        "checkpoint_identity_inputs": {
            "input_staging_build_identity": contract["input_staging_build_identity"],
            "input_staging_build_manifest_file_sha256": contract["input_staging_build_manifest_file_sha256"],
            "input_staging_checkpoint_manifest_canonical_sha256": contract["input_staging_checkpoint_manifest_canonical_sha256"],
            "input_staging_checkpoint_manifest_file_sha256": contract["input_staging_checkpoint_manifest_file_sha256"],
        },
        "tables": [],
    }


def _verification_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    contract = synthetic_county_evidence_contract()
    manifest = _invented_geography_manifest(contract)
    geography = tmp_path / contract["input_geography_checkpoint_identity"]
    geography.mkdir()
    manifest_path = geography / "geography_checkpoint_manifest.json"
    _write_json(manifest_path, manifest)
    contract["input_geography_manifest_canonical_sha256"] = sha256_json(manifest)
    contract["input_geography_manifest_file_sha256"] = sha256_file(manifest_path)
    staging_identity = _staging_identity(contract)
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.verify_staging_geography_input",
        lambda *args: StagingInputIdentity(*staging_identity[:4]),
    )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.verify_geography_checkpoint_artifacts",
        lambda *args: None,
    )
    return contract, geography, manifest_path


def _verification_arguments(contract: dict, geography: Path) -> tuple:
    return (
        geography.parent / "staging",
        geography,
        ROOT,
        contract,
        {}, {}, {}, {}, {}, {},
        contract["source_contract_sha256"],
        contract["source_table_contract_sha256"],
        contract["staging_table_contract_sha256"],
        contract["geography_contract_sha256"],
    )


def test_combined_input_identity_is_bound_to_both_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, geography, _ = _verification_case(tmp_path, monkeypatch)
    observed = verify_county_evidence_inputs(*_verification_arguments(contract, geography))
    assert observed == _staging_identity(contract)


def test_geography_manifest_mutation_and_path_drift_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract, geography, manifest_path = _verification_case(tmp_path, monkeypatch)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["invented_mutation"] = True
    _write_json(manifest_path, manifest)
    with pytest.raises(CountyEvidenceInputError, match="identities differ"):
        verify_county_evidence_inputs(*_verification_arguments(contract, geography))
    manifest.pop("invented_mutation")
    _write_json(manifest_path, manifest)
    wrong = geography.parent / "wrong-path"
    geography.rename(wrong)
    with pytest.raises(CountyEvidenceInputError, match="not content-addressed"):
        verify_county_evidence_inputs(*_verification_arguments(contract, wrong))


def _loader_files(tmp_path: Path, contract: dict) -> tuple[Path, Path]:
    staging_rows, geography_outputs = synthetic_county_evidence_inputs()
    staging_build = tmp_path / "staging"
    staging_checkpoint = staging_build / "checkpoint"
    staging_tables = staging_checkpoint / "tables"
    staging_tables.mkdir(parents=True)
    staging_entries = []
    for table_id, rows in staging_rows.items():
        relative = f"tables/{table_id}.parquet"
        _write_parquet(staging_checkpoint / relative, rows)
        staging_entries.append({"staging_table_id": table_id, "relative_path": relative})
    _write_json(staging_checkpoint / "staging_checkpoint_manifest.json", {"tables": staging_entries})

    geography = tmp_path / contract["input_geography_checkpoint_identity"]
    geography.mkdir()
    geography_entries = []
    _write_parquet(geography / "county_reference.parquet", geography_outputs["county_reference"])
    geography_entries.append({"artifact_id": "county_reference", "relative_path": "county_reference.parquet"})
    for table_id, rows in geography_outputs["source_maps"].items():
        artifact_id = f"map_{table_id}"
        relative = f"{artifact_id}.parquet"
        _write_parquet(geography / relative, rows)
        geography_entries.append({"artifact_id": artifact_id, "relative_path": relative})
    manifest = _invented_geography_manifest(contract)
    manifest["tables"] = geography_entries
    _write_json(geography / "geography_checkpoint_manifest.json", manifest)
    return staging_build, geography


def test_loader_reads_only_contracted_fields_and_builds_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = synthetic_county_evidence_contract()
    staging, geography = _loader_files(tmp_path, contract)
    identity = _staging_identity(contract)
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.verify_county_evidence_inputs",
        lambda *args: identity,
    )
    loaded_staging, loaded_geography, observed = load_verified_county_evidence_inputs(
        staging, geography, ROOT, contract, {}, {}, {}, {}, {}, {},
        contract["source_contract_sha256"], contract["source_table_contract_sha256"],
        contract["staging_table_contract_sha256"], contract["geography_contract_sha256"],
    )
    assert observed == identity
    assert set(loaded_staging) == {
        "stg_hhs_empower_county", "stg_fema_nri_counties",
        "stg_hrsa_primary_care_hpsa", "stg_hrsa_health_center_sites",
    }
    assert "stg_hhs_empower_history_county" not in loaded_staging
    assert len(build_county_evidence(loaded_staging, loaded_geography, contract)) == 4


def test_loader_reverification_detects_input_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = synthetic_county_evidence_contract()
    staging, geography = _loader_files(tmp_path, contract)
    accepted = _staging_identity(contract)
    changed = accepted._replace(geography_manifest_file_sha256="f" * 64)
    identities = iter([accepted, changed])
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.verify_county_evidence_inputs",
        lambda *args: next(identities),
    )
    with pytest.raises(CountyEvidenceInputError, match="changed while being read"):
        load_verified_county_evidence_inputs(
            staging, geography, ROOT, contract, {}, {}, {}, {}, {}, {},
            contract["source_contract_sha256"], contract["source_table_contract_sha256"],
            contract["staging_table_contract_sha256"], contract["geography_contract_sha256"],
        )


def test_production_entrypoint_exposes_no_override() -> None:
    assert list(signature(run_frozen_county_evidence_build).parameters) == [
        "data_root", "repository_root"
    ]


def test_invented_end_to_end_orchestration_writes_verified_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = synthetic_county_evidence_contract()
    staging, geography = _loader_files(tmp_path, contract)
    identity = _staging_identity(contract)
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.verify_county_evidence_inputs",
        lambda *args: identity,
    )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_input.capture_repository_identity",
        lambda _: "a" * 40,
    )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_checkpoint.capture_repository_identity",
        lambda _: "a" * 40,
    )
    monkeypatch.setattr(
        "healthcare_resilience.county_evidence_checkpoint.capture_environment_identity",
        lambda _: ("b" * 64, {"runtime": "invented"}),
    )
    output, manifest = _build_county_evidence_from_verified_inputs(
        staging,
        geography,
        tmp_path / "county_evidence_output",
        ROOT,
        contract,
        {}, {}, {}, {}, {}, {},
        load_json(CONFIG_DIR / "county_evidence_checkpoint.schema.json"),
        contract["source_contract_sha256"],
        contract["source_table_contract_sha256"],
        contract["staging_table_contract_sha256"],
        contract["geography_contract_sha256"],
        "c" * 64,
    )
    assert output.name == manifest["checkpoint_identity"]
    assert manifest["artifact"]["row_count"] == 4
    assert manifest["artifact_count"] == 1
