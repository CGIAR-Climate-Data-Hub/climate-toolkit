"""Internal source-dispatch helper for fetch pipeline.

This module remains importable for package internals and legacy analysis
scripts, but it is not stable public CLI surface. End users should prefer
`climate-toolkit-fetch` or `climate_tookit.fetch_data.fetch_data`.
"""

import argparse
import sys
from datetime import datetime, date
from pathlib import Path
import pandas as pd
from .sources.gee_xee import DownloadData as DownloadGEEXee
from .sources.agera_5 import DownloadData as DownloadAgera5
from .sources.era_5 import DownloadData as DownloadERA5
from .sources.tamsat import DownloadTAMSAT
from .sources.nasa_power import DownloadData as DownloadNASA
from .sources.nex_gddp import DownloadData as DownloadNEXGDDP
from .sources.ghcn_daily import DownloadData as DownloadGHCNDaily
from .sources.gsod import DownloadData as DownloadGSOD
from .sources.xee_common import format_ee_setup_error
from .sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    SoilVariable,
    Location,
    clip_source_date_range,
    normalize_climate_dataset_name,
    parse_variable_token,
)
from .sources.utils.settings import Settings

XEE_SINGLE_SITE_SOURCES = (
    ClimateDataset.era_5,
    ClimateDataset.agera_5,
    ClimateDataset.terraclimate,
    ClimateDataset.imerg,
    ClimateDataset.chirps_v2,
    ClimateDataset.chirps_v3_daily_rnl,
    ClimateDataset.cmip_6,
    ClimateDataset.chirts,
)

STATIC_GEE_SOURCES = (
    ClimateDataset.soil_grid,
    ClimateDataset.hwsd,
)

FULL_PRINT_MAX_ROWS = 60
PREVIEW_ROWS = 5


def _download_gee_cls():
    from .sources.gee import DownloadData

    return DownloadData


class SourceData:
    """The main class for retrieving data via a standardised interface."""

    def __init__(self, location_coord, variables, source, date_from_utc,
                 date_to_utc, settings, model=None, scenario=None,
                 nex_backend=None, verbose=True, cache_dir=None,
                 refresh_cache=False, station_id=None, ee_project_id=None):
        self.location_coord = location_coord
        self.variables = variables
        self.source = source
        self.date_from_utc = date_from_utc
        self.date_to_utc = date_to_utc
        self.settings = settings
        self.model = model
        self.scenario = scenario
        self.nex_backend = nex_backend
        self.verbose = verbose
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache
        self.station_id = station_id
        self.ee_project_id = ee_project_id

        client = None

        if source == ClimateDataset.nex_gddp:
            client = DownloadNEXGDDP(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                model=model,
                scenario=scenario,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                ee_project_id=ee_project_id,
            )
        elif source == ClimateDataset.era_5:
            client = DownloadERA5(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                ee_project_id=ee_project_id,
            )
        elif source == ClimateDataset.agera_5:
            client = DownloadAgera5(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                ee_project_id=ee_project_id,
            )
        elif source in XEE_SINGLE_SITE_SOURCES:
            client = DownloadGEEXee(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                ee_project_id=ee_project_id,
            )
        elif source in STATIC_GEE_SOURCES:
            client = _download_gee_cls()(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            )
        elif source == ClimateDataset.tamsat:
            client = DownloadTAMSAT(
                variables=variables,
                location_coord=location_coord,
                aggregation=None,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            )
        elif source == ClimateDataset.nasa_power:
            client = DownloadNASA(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
            )
        elif source == ClimateDataset.ghcn_daily:
            client = DownloadGHCNDaily(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
            )
        elif source == ClimateDataset.gsod:
            client = DownloadGSOD(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source,
                verbose=verbose,
                cache_dir=cache_dir,
                refresh_cache=refresh_cache,
                station_id=station_id,
            )

        if client is None:
            raise ValueError(f"No download client defined for source: {source}")

        self.client = client

    def download(self):
        """Download climate data from the remote location."""
        return self.client.download_variables()


def save_output(data, output_path, fmt):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        data.to_csv(output_path, index=False)
    elif fmt == "json":
        data.to_json(output_path, orient="records", date_format="iso", indent=2)
    else:
        raise ValueError(fmt)


def _source_label(source) -> str:
    if hasattr(source, "name"):
        return source.name
    return str(source)


def _requested_variable_names(variables) -> list[str]:
    return [getattr(variable, "name", str(variable)) for variable in variables]


def _format_date_value(value) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _date_range_line(data: pd.DataFrame) -> str | None:
    if data.empty or "date" not in data.columns:
        return None
    date_values = pd.to_datetime(data["date"], errors="coerce").dropna()
    if date_values.empty:
        return None
    return (
        f"Date range: {_format_date_value(date_values.min())} .. "
        f"{_format_date_value(date_values.max())}"
    )


def render_cli_output(data: pd.DataFrame, variables, source) -> str:
    lines: list[str] = []
    requested_variables = _requested_variable_names(variables)
    available_variables = {str(column) for column in data.columns if str(column) != "date"}
    missing_variables = [
        variable for variable in requested_variables if variable not in available_variables
    ]
    if missing_variables:
        lines.append(
            "Warning: Source "
            f"'{_source_label(source)}' did not return requested variables: "
            f"{', '.join(missing_variables)}"
        )

    if len(data) <= FULL_PRINT_MAX_ROWS:
        lines.append(data.to_string(index=False))
        return "\n".join(lines)

    lines.append(f"Retrieved {len(data)} row(s) across {len(data.columns)} column(s).")
    date_range = _date_range_line(data)
    if date_range:
        lines.append(date_range)
    lines.append(f"Columns: {', '.join(str(column) for column in data.columns)}")
    lines.append(f"Preview (first {PREVIEW_ROWS} rows):")
    lines.append(data.head(PREVIEW_ROWS).to_string(index=False))
    lines.append(f"Preview (last {PREVIEW_ROWS} rows):")
    lines.append(data.tail(PREVIEW_ROWS).to_string(index=False))
    lines.append("Use --format csv --output <path> or --format json --output <path> to save the full dataset.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Download climate data')
    parser.add_argument('--lon', type=float, required=True)
    parser.add_argument('--lat', type=float, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--variables', required=True)
    parser.add_argument('--from', dest='date_from', required=True)
    parser.add_argument('--to', dest='date_to', required=True)
    parser.add_argument('--model', default=None)
    parser.add_argument('--scenario', default=None)
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--cache-dir', default=None)
    parser.add_argument('--refresh-cache', action='store_true')
    parser.add_argument('--station-id', default=None)
    parser.add_argument('--project-id', default=None,
                        help='Optional Earth Engine / GCP project ID for Xee-backed sources')
    parser.add_argument('--output', '-o', default=None)
    parser.add_argument(
        '--format',
        choices=['csv', 'json', 'print'],
        default='print'
    )

    args = parser.parse_args()
    
    if not (-180 <= args.lon <= 180):
        print(f"Error: Longitude must be between -180 and 180, got {args.lon}")
        return 1

    if not (-90 <= args.lat <= 90):
        print(f"Error: Latitude must be between -90 and 90, got {args.lat}")
        return 1

    variables = []
    for v in args.variables.split(','):
        try:
            variables.append(parse_variable_token(v))
        except ValueError:
            print(f"Error: Unknown variable '{v.strip()}'")
            return 1

    source = getattr(ClimateDataset, normalize_climate_dataset_name(args.source), None)
    if not source:
        print(f"Error: Unknown source '{args.source}'")
        return 1

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    settings = Settings.load()
    try:
        date_from, date_to, coverage_warning = clip_source_date_range(
            source,
            date_from,
            date_to,
            settings=settings,
            ee_project_id=args.project_id,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    if coverage_warning:
        print(f"Warning: {coverage_warning}", flush=True)

    try:
        source_data = SourceData(
            location_coord=(args.lat, args.lon),
            variables=variables,
            source=source,
            date_from_utc=date_from,
            date_to_utc=date_to,
            settings=settings,
            model=args.model,
            scenario=args.scenario,
            verbose=not args.quiet,
            cache_dir=args.cache_dir,
            refresh_cache=args.refresh_cache,
            station_id=args.station_id,
            ee_project_id=args.project_id,
        )

        climate_data = source_data.download()

        if args.format == "print" or not args.output:
            print(render_cli_output(climate_data, variables=variables, source=source))
        else:
            save_output(climate_data, args.output, args.format)
            print(f"Saved to {args.output}")
    except Exception as exc:
        print(f"Error: {format_ee_setup_error(exc)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

 
# For nex_gddp with different models and scenarios    
# python .\climate_tookit\fetch_data\source_data\source_data.py --source nex_gddp --variables precipitation,max_temperature,min_temperature --from 2050-01-01 --to 2050-01-10 --lon 36.817 --lat -1.286 --model GFDL-ESM4 --scenario ssp245

# For other sources
# python .\climate_tookit\fetch_data\source_data\source_data.py --source chirps_v2 --variables precipitation,max_temperature,min_temperature,soil_moisture,bulk_density,wind_speed,solar_radiation,humidity,ph,silt_content,clay_content --from 2020-01-01 --to 2020-01-10 --lon 36.817 --lat -1.286

# Download data in csv
# For nex_gddp with different models and scenarios
# python .\climate_tookit\fetch_data\source_data\source_data.py --source nex_gddp --variables precipitation,max_temperature,min_temperature --from 2050-01-01 --to 2050-01-10 --lon 36.817 --lat -1.286 --model GFDL-ESM4 --scenario ssp245 --format csv --output nexgddp_2050.csv

# For other sources
# python .\climate_tookit\fetch_data\source_data\source_data.py --source chirts --variables precipitation,max_temperature,min_temperature --from 2016-01-01 --to 2016-01-10 --lon 36.817 --lat -1.286 --format csv --output chirts_2016.csv
