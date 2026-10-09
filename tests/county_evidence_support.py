from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from healthcare_resilience.contracts import load_json
from healthcare_resilience.county_evidence import HAZARD_CODES

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_county_evidence.json"


def synthetic_county_evidence_contract() -> dict:
    contract = deepcopy(load_json(CONFIG_DIR / "county_evidence.json"))
    contract["reference"].update(
        {"expected_county_count": 4, "eligible_count": 3, "out_of_scope_count": 1}
    )
    counts = {
        "HHS_CURRENT": 3,
        "FEMA_RISK": 4,
        "HPSA_COMPONENT": 5,
        "SITE_CONTEXT": 3,
    }
    for role in contract["source_roles"]:
        role["expected_mapped_count"] = counts[role["role"]]
    return contract


def synthetic_county_evidence_inputs() -> tuple[dict, dict]:
    fixture = deepcopy(load_json(FIXTURE))
    fema_rows = fixture["staging_rows"]["stg_fema_nri_counties"]
    expanded = []
    for row in fema_rows:
        seed = row.pop("hazard_seed")
        not_applicable = row.pop("not_applicable_hazard", None)
        output = dict(row)
        for position, code in enumerate(HAZARD_CODES, start=1):
            if code == not_applicable:
                output[f"{code}_RISKS"] = None
                output[f"{code}_RISKR"] = "Not Applicable"
            else:
                output[f"{code}_RISKS"] = seed + position / 100
                output[f"{code}_RISKR"] = "Invented Rating"
        expanded.append(output)
    fixture["staging_rows"]["stg_fema_nri_counties"] = expanded
    geography = {
        "county_reference": fixture["county_reference"],
        "source_maps": fixture["source_maps"],
    }
    return fixture["staging_rows"], geography
