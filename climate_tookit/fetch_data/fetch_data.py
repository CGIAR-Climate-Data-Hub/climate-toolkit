"""
Climate Data Fetching Orchestrator
Single entry point for the climate data pipeline:
    Source -> Transform -> Preprocess
Stages:
    raw          - download only (SourceData)
    transformed  - download + standardise column names (transform_data)
    preprocessed - download + standardise + clean/QC (preprocess_data) [default]

Notes:
    - This low-level entry point expects an exact source name.
    - Module-level historical `auto` selection lives in higher-level workflows
      such as climate_statistics, season_analysis, and calculate_hazards.
"""

import argparse
import sys
from datetime import date
from pathlib import Path
from .gee_xee_batch import (
    SUPPORTED_GEE_XEE_BATCH_SOURCES,
    fetch_gee_xee_batch_data,
)
from .multi_site import parse_site_spec
from .nex_gddp_batch import fetch_nex_gddp_batch_data
from .runtime_notes import build_historical_cache_note
from .source_data.source_data import SourceData
from .source_data.sources.xee_common import format_ee_setup_error
from .transform_data.transform_data import (
    transform_data,
    validate_inputs,
    default_variables,
)
from .preprocess_data.preprocess_data import preprocess_data
from .source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    SoilVariable,
    normalize_climate_dataset_name,
    parse_variable_token,
    source_date_coverage_error,
)
from .source_data.sources.utils.settings import Settings

VALID_STAGES = ("raw", "transformed", "preprocessed")


def _default_variables_for_source(source_name: str):
    if source_name in {"ghcn_daily", "gsod"}:
        return [
            ClimateVariable.precipitation,
            ClimateVariable.max_temperature,
            ClimateVariable.min_temperature,
        ]
    return default_variables()

def fetch_data(
    source,
    location_coord=None,
    variables=None,
    date_from=None,
    date_to=None,
    settings=None,
    model=None,
    scenario=None,
    stage="preprocessed",
    verbose=True,
    cache_dir=None,
    refresh_cache=False,
    sites=None,
    sites_csv=None,
    station_id=None,
    workers=1,
):
    """Fetch climate data through the pipeline.
    Parameters
    ----------
    source : str
        Climate dataset name (e.g. 'era_5', 'chirps_v2', 'nex_gddp').
    location_coord : tuple[float, float], optional
        (latitude, longitude) for single-site fetches.
    variables : list, optional
        ClimateVariable / SoilVariable enums. Defaults to a sensible set.
    date_from, date_to : date, optional
        Date range. Defaults to today.
    settings : Settings, optional
        Loaded settings. Auto-loaded if not provided.
    model, scenario : str, optional
        Required only for `nex_gddp`.
    stage : {'raw', 'transformed', 'preprocessed'}
        How far through the pipeline to run. Default 'preprocessed'.
    sites, sites_csv : optional
        Many-site inputs. If present, package-native batch path is used.
    Returns
    -------
    pandas.DataFrame
    """
    if stage not in VALID_STAGES:
        raise ValueError(
            f"Invalid stage '{stage}'. Must be one of: {', '.join(VALID_STAGES)}"
        )
    settings = settings or Settings.load()
    source_name = normalize_climate_dataset_name(source)
    variables = variables or _default_variables_for_source(source_name)
    date_from = date_from or date.today()
    date_to = date_to or date.today()
    coverage_error = source_date_coverage_error(source_name, date_from, date_to)
    if coverage_error:
        raise ValueError(coverage_error)

    batch_requested = bool(sites or sites_csv)
    if batch_requested:
        if source_name == "nex_gddp":
            data_df, _, _ = fetch_nex_gddp_batch_data(
                sites=sites,
                sites_csv=sites_csv,
                variables=variables,
                date_from=date_from,
                date_to=date_to,
                settings=settings,
                model=model,
                scenario=scenario,
                stage=stage,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                verbose=verbose,
            )
            return data_df

        try:
            dataset = ClimateDataset[source_name]
        except KeyError:
            raise ValueError(f"Unknown source '{source_name}'")

        if dataset not in SUPPORTED_GEE_XEE_BATCH_SOURCES:
            supported = ", ".join(sorted(item.name for item in SUPPORTED_GEE_XEE_BATCH_SOURCES))
            raise ValueError(
                f"Many-site fetch is not supported for source '{source}'. "
                f"Supported many-site sources: nex_gddp, {supported}"
            )

        data_df, _, _ = fetch_gee_xee_batch_data(
            source=source_name,
            sites=sites,
            sites_csv=sites_csv,
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            settings=settings,
            stage=stage,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            verbose=verbose,
            workers=workers,
        )
        return data_df

    if location_coord is None:
        raise ValueError("location_coord must be provided for single-site fetches")

    if stage == "raw":
        try:
            dataset = ClimateDataset[source_name]
        except KeyError:
            raise ValueError(f"Unknown source '{source_name}'")

        client = SourceData(
            location_coord=location_coord,
            variables=variables,
            source=dataset,
            date_from_utc=date_from,
            date_to_utc=date_to,
            settings=settings,
            model=model,
            scenario=scenario,
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
            workers=workers,
        )
        return client.download()

    if stage == "transformed":
        return transform_data(
            source=source_name,
            location_coord=location_coord,
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            settings=settings,
            model=model,
            scenario=scenario,
            verbose=verbose,
            cache_dir=cache_dir,
            refresh_cache=refresh_cache,
            station_id=station_id,
            workers=workers,
        )
    # preprocessed (default)
    return preprocess_data(
        source=source_name,
        location_coord=location_coord,
        variables=variables,
        date_from=date_from,
        date_to=date_to,
        settings=settings,
        model=model,
        scenario=scenario,
        verbose=verbose,
        cache_dir=cache_dir,
        refresh_cache=refresh_cache,
        station_id=station_id,
        workers=workers,
    )
def save_output(data, output_path, fmt):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        data.to_csv(output_path, index=False)
    elif fmt == "json":
        data.to_json(output_path, orient="records", date_format="iso", indent=2)
    else:
        raise ValueError(fmt)

def parse_variables(raw):
    """Parse a comma-separated --variables string into enum members."""
    if not raw:
        return None
    variables = []
    for v in raw.split(","):
        variables.append(parse_variable_token(v))
    return variables

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch climate data through the source -> transform -> preprocess "
            "pipeline. Use an exact source key here; higher-level module "
            "auto-selection is not handled by this CLI."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Exact dataset key, e.g. chirps_v3_daily_rnl, chirps_v2, "
            "agera_5, era_5, nex_gddp. Use climate_statistics / "
            "season_analysis / calculate_hazards for module-level auto mode."
        ),
    )
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help='Repeatable site spec: "name,lat,lon"',
    )
    parser.add_argument(
        "--sites-csv",
        default=None,
        help="CSV of many-site specs for the batch path",
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--scenario", default=None)
    parser.add_argument(
        "--station-id",
        default=None,
        help="Optional station identifier for station-backed sources such as ghcn_daily or gsod",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--cache-dir",
        default=None,
        help=(
            "Optional project-local cache root. Reuse a stable path such as "
            "outputs/cache/... for fast repeat runs. If omitted, supported "
            "sources fall back to their default project-local cache layout."
        ),
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help=(
            "Bypass any saved cache files and force a cold fetch. Useful for "
            "refreshing data, but slower than a warm-cache rerun."
        ),
    )
    parser.add_argument(
        "--stage",
        choices=VALID_STAGES,
        default="preprocessed",
        help="Pipeline stage to return (default: preprocessed)",
    )
    parser.add_argument(
        "--variables",
        default=None,
        help=(
            "Comma-separated list; defaults to a standard set. For agera_5 "
            "companion variables, request humidity, wind_speed, and/or "
            "solar_radiation explicitly. For ghcn_daily and gsod, default is "
            "precipitation,max_temperature,min_temperature."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "Bounded worker count for historical GEE/Xee fetch tasks. "
            "Useful mainly for multi-site or long period historical runs."
        ),
    )
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument(
        "--format",
        choices=["csv", "json", "print"],
        default="print",
    )

    args = parser.parse_args()

    date_from = date.fromisoformat(args.start)
    date_to = date.fromisoformat(args.end)

    batch_requested = bool(args.site or args.sites_csv)

    if batch_requested:
        if args.lat is not None or args.lon is not None:
            print("Error: use either --lat/--lon for single-site or --site/--sites-csv for many-site")
            return 1
    else:
        if args.lat is None or args.lon is None:
            print("Error: provide --lat and --lon for single-site fetches, or use --site/--sites-csv")
            return 1

        errors = validate_inputs(
            args.source, args.lat, args.lon, date_from, date_to,
            args.model, args.scenario,
        )
        if errors:
            print("\nInput validation failed:\n")
            for err in errors:
                print(f" - {err}")
            return 1

    try:
        variables = parse_variables(args.variables)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    parsed_sites = None
    if args.site:
        try:
            parsed_sites = [parse_site_spec(raw) for raw in args.site]
        except ValueError as e:
            print(f"Error: {e}")
            return 1

    cache_note = build_historical_cache_note(
        args.source,
        refresh_cache=args.refresh_cache,
        cache_dir=args.cache_dir,
    )
    if cache_note and not args.quiet:
        print(cache_note)

    try:
        df = fetch_data(
            source=args.source,
            location_coord=(args.lat, args.lon) if args.lat is not None and args.lon is not None else None,
            variables=variables,
            date_from=date_from,
            date_to=date_to,
            model=args.model,
            scenario=args.scenario,
            stage=args.stage,
            verbose=not args.quiet,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            sites=parsed_sites,
            sites_csv=args.sites_csv,
            station_id=args.station_id,
            workers=args.workers,
        )
    except Exception as exc:
        print(f"Error: {format_ee_setup_error(exc)}")
        return 1

    if args.format == "print" or not args.output:
        print(df)
    else:
        save_output(df, args.output, args.format)
        print(f"Saved to {args.output}")

    return 0

if __name__ == "__main__":
    sys.exit(main())

# Examples:
# Full pipeline (default, preprocessed):
# python climate_tookit/fetch_data/fetch_data.py --source era_5 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-03-05

# Stop at transformed stage:
# python climate_tookit/fetch_data/fetch_data.py --source chirps_v2 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --stage transformed

# Raw download only:
# python climate_tookit/fetch_data/fetch_data.py --source chirps_v2 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --stage raw

# NEX-GDDP with model/scenario, saved to CSV:
# python climate_tookit/fetch_data/fetch_data.py --source nex_gddp --lat -1.286 --lon 36.817 --start 2050-01-01 --end 2050-01-10 --model GFDL-ESM4 --scenario ssp245 --format csv --output nex_gddp_2050.csv

# With a custom variable list:
# python climate_tookit/fetch_data/fetch_data.py --source era_5 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --variables precipitation,max_temperature,min_temperature
