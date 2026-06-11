"""
Operator smoke test for Xee-backed NEX-GDDP retrieval.

This script is for backend/service operators, not ordinary end users.
It assumes Earth Engine credentials and project access are already configured.

Example:

    export GCP_PROJECT_ID="your-ee-project"
    .venv/bin/python analysis/run_nex_gddp_xee_smoke.py \
        --lat -1.286 --lon 36.817 \
        --start 2050-01-01 --end 2050-01-07 \
        --model MRI-ESM2-0 --scenario ssp245
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climate_tookit.fetch_data.source_data.sources.nex_gddp_xee import DownloadData
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


DEFAULT_VARIABLES = [
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test real Xee-backed NEX-GDDP fetch for operators."
    )
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--model", default="MRI-ESM2-0")
    parser.add_argument("--scenario", default="ssp245")
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--head", type=int, default=5)
    return parser.parse_args()


def infer_project_id(cli_value: str | None) -> str | None:
    return (
        cli_value
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("EE_PROJECT_ID")
    )


def main() -> int:
    args = parse_args()
    project_id = infer_project_id(args.project_id)

    if project_id is None:
        print("Missing Earth Engine project ID.")
        print("Set --project-id or one of: GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, EE_PROJECT_ID.")
        return 2

    settings = Settings.load()
    downloader = DownloadData(
        variables=DEFAULT_VARIABLES,
        location_coord=(args.lat, args.lon),
        date_from_utc=args.start,
        date_to_utc=args.end,
        settings=settings,
        source=ClimateDataset.nex_gddp,
        model=args.model,
        scenario=args.scenario,
        ee_project_id=project_id,
    )

    print("Running Xee NEX-GDDP smoke test")
    print(f"Project:  {project_id}")
    print(f"Location: lat={args.lat}, lon={args.lon}")
    print(f"Period:   {args.start} to {args.end}")
    print(f"Model:    {args.model}")
    print(f"Scenario: {args.scenario}")

    start_time = time.perf_counter()
    try:
        df = downloader.download_variables()
    except Exception as exc:
        elapsed = time.perf_counter() - start_time
        print(f"Fetch failed after {elapsed:.2f}s")
        print(f"{type(exc).__name__}: {exc}")
        print("Check: earthengine authenticate, project registration, and EE access for this project.")
        return 1

    elapsed = time.perf_counter() - start_time
    print(f"Fetch succeeded in {elapsed:.2f}s")
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print()
    print(df.head(args.head).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
