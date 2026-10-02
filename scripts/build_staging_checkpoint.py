"""Build one verified frozen source-preserving checkpoint outside Git."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healthcare_resilience.contracts import ContractError  # noqa: E402
from healthcare_resilience.source_adapters import SourceAdapterError  # noqa: E402
from healthcare_resilience.source_profiling import (  # noqa: E402
    SourceTableProfilingError,
)
from healthcare_resilience.snapshot import (  # noqa: E402
    SnapshotVerificationInvariantError,
)
from healthcare_resilience.staging import StagingExtractionError  # noqa: E402
from healthcare_resilience.staging_build import (  # noqa: E402
    StagingBuildError,
    run_frozen_staging_build,
)
from healthcare_resilience.staging_checkpoint import (  # noqa: E402
    StagingCheckpointError,
)

DATA_ROOT_ENV = "HEALTHCARE_ENERGY_RESILIENCE_DATA_ROOT"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the accepted frozen snapshot and all source structures, "
            "then atomically build source-preserving private staging artifacts."
        )
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help=f"Private data root; defaults to ${DATA_ROOT_ENV}.",
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
    try:
        output_directory, manifest = run_frozen_staging_build(
            args.data_root,
            ROOT,
        )
    except (
        ContractError,
        SourceAdapterError,
        SourceTableProfilingError,
        SnapshotVerificationInvariantError,
        StagingBuildError,
        StagingCheckpointError,
        StagingExtractionError,
        duckdb.Error,
        OSError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "stage": "frozen_source_preserving_staging",
                    "error": str(error),
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "complete",
                "build_identity": manifest["build_identity"],
                "source_snapshot_id": manifest["build_identity_inputs"][
                    "source_snapshot_id"
                ],
                "table_count": manifest["checkpoint"]["table_count"],
                "total_row_count": manifest["checkpoint"]["total_row_count"],
                "output_directory": str(output_directory),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
