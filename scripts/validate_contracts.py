"""Generate or verify the public source, method, and configuration contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healthcare_resilience.configurations import (  # noqa: E402
    build_configuration_manifest,
    write_json_document,
)
from healthcare_resilience.contracts import (  # noqa: E402
    load_json,
    validate_configuration_manifest,
    validate_method_contract,
    validate_repository_contracts,
    validate_source_contract,
    validate_source_table_contract,
    validate_staging_contract,
)
from healthcare_resilience.hashing import sha256_file  # noqa: E402
from healthcare_resilience.geography import validate_geography_contract  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate immutable Project 04 engineering contracts and schemas."
    )
    parser.add_argument(
        "--write-configurations",
        action="store_true",
        help="Regenerate configs/configurations.json from the accepted method contract.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_dir = ROOT / "configs"
    sources = load_json(config_dir / "sources.json")
    source_schema = load_json(config_dir / "sources.schema.json")
    source_tables = load_json(config_dir / "source_tables.json")
    source_table_schema = load_json(config_dir / "source_tables.schema.json")
    staging_tables = load_json(config_dir / "staging_tables.json")
    staging_table_schema = load_json(config_dir / "staging_tables.schema.json")
    method = load_json(config_dir / "method.json")
    method_schema = load_json(config_dir / "method.schema.json")
    configuration_schema = load_json(config_dir / "configurations.schema.json")
    geography = load_json(config_dir / "geography.json")
    geography_schema = load_json(config_dir / "geography.schema.json")

    validate_source_contract(sources, source_schema)
    validate_source_table_contract(
        source_tables, source_table_schema, sources
    )
    validate_staging_contract(
        staging_tables,
        staging_table_schema,
        source_tables,
        sha256_file(config_dir / "source_tables.json"),
    )
    validate_method_contract(method, method_schema)
    validate_geography_contract(geography, geography_schema)
    method_hash = sha256_file(config_dir / "method.json")
    generated = build_configuration_manifest(method, method_hash)
    validate_configuration_manifest(
        generated, configuration_schema, method, method_hash
    )

    if args.write_configurations:
        write_json_document(config_dir / "configurations.json", generated)

    summary = validate_repository_contracts(ROOT)
    print(json.dumps({"status": "valid", **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
