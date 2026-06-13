"""
Module for applying the DownloadData / SourceData class to download from
different climate databases.
"""

import argparse
import sys
from datetime import datetime, date
from .sources.gee import DownloadData as DownloadGEE
from .sources.gee_xee import DownloadData as DownloadGEEXee
from .sources.agera_5 import DownloadData as DownloadAgera5
from .sources.era_5 import DownloadData as DownloadERA5
from .sources.tamsat import DownloadTAMSAT
from .sources.nasa_power import DownloadData as DownloadNASA
from .sources.nex_gddp import DownloadData as DownloadNEXGDDP
from .sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    SoilVariable,
    Location,
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


class SourceData:
    """The main class for retrieving data via a standardised interface."""

    def __init__(self, location_coord, variables, source, date_from_utc,
                 date_to_utc, settings, model=None, scenario=None,
                 nex_backend=None, verbose=True, cache_dir=None,
                 refresh_cache=False):
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
            )
        elif source in STATIC_GEE_SOURCES:
            client = DownloadGEE(
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
                date_to_utc=date_to_utc
            )
        elif source == ClimateDataset.nasa_power:
            client = DownloadNASA(
                variables=variables,
                location_coord=location_coord,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
                settings=settings,
                source=source
            )

        if client is None:
            raise ValueError(f"No download client defined for source: {source}")

        self.client = client

    def download(self):
        """Download climate data from the remote location."""
        return self.client.download_variables()


def save_output(data, output_path, fmt):
    if fmt == "csv":
        data.to_csv(output_path, index=False)
    elif fmt == "json":
        data.to_json(output_path, orient="records", date_format="iso", indent=2)
    else:
        raise ValueError(fmt)


def main():
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
        v = v.strip()
        if hasattr(ClimateVariable, v):
            variables.append(getattr(ClimateVariable, v))
        elif hasattr(SoilVariable, v):
            variables.append(getattr(SoilVariable, v))
        else:
            print(f"Error: Unknown variable '{v}'")
            return 1

    source = getattr(ClimateDataset, args.source, None)
    if not source:
        print(f"Error: Unknown source '{args.source}'")
        return 1

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()

    settings = Settings.load()

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
    )

    climate_data = source_data.download()

    if args.format == "print" or not args.output:
        print(climate_data.to_string())
    else:
        save_output(climate_data, args.output, args.format)
        print(f"Saved to {args.output}")

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
