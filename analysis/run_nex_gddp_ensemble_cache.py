"""
Operator wrapper for cached NEX-GDDP ensemble extraction.

Loops model/scenario combinations, reuses parquet batch cache from
`run_nex_gddp_many_points_ee.py`, and writes combined summary outputs.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climate_tookit.fetch_data.nex_gddp_batch import (
    load_sites,
    parse_site_spec,
    run_batch_extraction,
    save_frame,
)
from climate_tookit.fetch_data.source_data.sources.nex_gddp_xee import (
    _infer_ee_project_id,
    _normalize_scenario,
    _validate_period_against_scenario,
)
from climate_tookit.fetch_data.source_data.sources.nex_gddp import AVAILABLE_MODELS
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run cached many-point NEX-GDDP extraction across model/scenario ensembles."
    )
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help='Repeatable site spec: "name,lat,lon"',
    )
    parser.add_argument(
        "--sites-csv",
        default=None,
        help="Optional CSV with columns: name,lat,lon",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Repeatable model name. Defaults to all AVAILABLE_MODELS.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Repeatable scenario. Defaults to historical for pre-2015 windows, or ssp245+ssp585 for 2015+ windows.",
    )
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--chunk-days", type=int, default=None)
    parser.add_argument("--point-batch-size", type=int, default=25)
    parser.add_argument("--target-elements-per-batch", type=int, default=4500)
    parser.add_argument("--tile-scale", type=float, default=1.0)
    parser.add_argument(
        "--cache-dir",
        default="analysis/cache/nex_gddp_many_points",
        help="Directory for parquet batch cache.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore existing cache and re-fetch from Earth Engine.",
    )
    parser.add_argument(
        "--summary-output",
        default="analysis/nex_ensemble_summary.csv",
        help="Combined per-model per-scenario summary output.",
    )
    parser.add_argument(
        "--manifest-output",
        default="analysis/nex_ensemble_manifest.csv",
        help="Batch/chunk execution manifest output.",
    )
    return parser.parse_args()


def default_scenarios(start: date, end: date) -> list[str]:
    if end <= date(2014, 12, 31):
        return ["historical"]
    if start >= date(2015, 1, 1):
        return ["ssp245", "ssp585"]
    raise ValueError(
        "Mixed historical/future windows require explicit --scenario choices with separate runs."
    )


def main() -> int:
    args = parse_args()
    sites = load_sites(
        sites=[parse_site_spec(raw) for raw in args.site],
        sites_csv=args.sites_csv,
    )
    models = args.model or list(AVAILABLE_MODELS)
    scenarios = [_normalize_scenario(item) for item in (args.scenario or default_scenarios(args.start, args.end))]

    for scenario in scenarios:
        _validate_period_against_scenario(scenario, args.start, args.end)

    project_id = _infer_ee_project_id(args.project_id)
    settings = Settings.load()

    combined_summary: list[pd.DataFrame] = []
    combined_manifest: list[pd.DataFrame] = []

    print("Running cached ensemble NEX-GDDP extraction")
    print(f"Project:          {project_id}")
    print(f"Sites:            {len(sites)}")
    print(f"Models:           {len(models)}")
    print(f"Scenarios:        {', '.join(scenarios)}")
    print(f"Date range:       {args.start} to {args.end}")

    for scenario in scenarios:
        for model in models:
            print()
            print(f"=== model={model} scenario={scenario} ===")
            result, summary, manifest = run_batch_extraction(
                sites=sites,
                date_from=args.start,
                date_to=args.end,
                settings=settings,
                model=model,
                scenario=scenario,
                point_batch_size=args.point_batch_size,
                chunk_days=args.chunk_days,
                target_elements_per_batch=args.target_elements_per_batch,
                tile_scale=args.tile_scale,
                cache_dir=args.cache_dir,
                refresh_cache=args.refresh_cache,
                ee_project_id=project_id,
                verbose=True,
            )
            if not summary.empty:
                combined_summary.append(summary)
            if not manifest.empty:
                manifest = manifest.copy()
                manifest["model"] = model
                manifest["scenario"] = scenario
                combined_manifest.append(manifest)

    summary_df = (
        pd.concat(combined_summary, ignore_index=True)
        if combined_summary else pd.DataFrame()
    )
    manifest_df = (
        pd.concat(combined_manifest, ignore_index=True)
        if combined_manifest else pd.DataFrame()
    )

    save_frame(summary_df, args.summary_output)
    print()
    print(f"Saved ensemble summary to {args.summary_output}")

    save_frame(manifest_df, args.manifest_output)
    print(f"Saved ensemble manifest to {args.manifest_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
