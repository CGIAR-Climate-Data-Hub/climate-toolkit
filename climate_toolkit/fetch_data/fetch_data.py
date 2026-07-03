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
from .source_data.sources.nex_gddp import AVAILABLE_MODELS as NEX_GDDP_MODELS
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
    clip_source_date_range,
    normalize_climate_dataset_name,
    parse_variable_token,
)
from .source_data.sources.utils.settings import Settings

VALID_STAGES = ("raw", "transformed", "preprocessed")


def _emit_coverage_warning(message: str | None) -> None:
    if message:
        print(f"Warning: {message}", flush=True)


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
    """Fetch climate data through the pipeline (source -> transform -> preprocess).

    Also exported as ``climate_toolkit.fetch_climate_data``.

    Parameters
    ----------
    source : str or ClimateDataset
        Climate dataset name. Valid values (``ClimateDataset`` enum names):

        - ``'agera_5'`` : ERA5-Land daily aggregates (GEE asset
          ``ECMWF/ERA5_LAND/DAILY_AGGR``), 0.1 deg (~11 km), 1979-present.
          Broadest daily variable set: precipitation, max/min/mean
          temperature, humidity, wind_speed, solar_radiation (request
          companions explicitly). Recommended default. Earth Engine.
        - ``'era_5'`` : ERA5 daily reanalysis, 0.25 deg (~28 km), from 1979.
          The static coverage window ends 2020-07-09 (the ECMWF/ERA5/DAILY
          GEE asset); live GEE coverage is checked at runtime and requests
          are clipped to it, with a hint to use 'agera_5' for later periods.
          Precipitation, max/min temperature, wind. Earth Engine.
        - ``'terraclimate'`` : TerraClimate monthly climate/water balance,
          ~4 km, 1958-present. Monthly cadence. Earth Engine.
        - ``'imerg'`` : GPM IMERG v07 satellite precipitation, 0.1 deg,
          2000-present. Precipitation only. Earth Engine.
        - ``'chirps_v2'`` (alias ``'chirps'``) : CHIRPS v2 daily blended
          satellite-gauge precipitation, 0.05 deg (~5.5 km), 1981-present.
          Precipitation only. Earth Engine.
        - ``'chirps_v3_daily_rnl'`` : CHIRPS v3 daily precipitation,
          0.05 deg, 1981-present. Precipitation only. Earth Engine.
        - ``'chirts'`` : CHIRTS daily satellite-station temperature,
          0.05 deg, 1983-2016. Max/min temperature. Earth Engine.
        - ``'cmip_6'`` : NASA GDDP-CMIP6 downscaled projections, 0.25 deg.
          Precipitation, max/min temperature. Earth Engine.
        - ``'nex_gddp'`` : NEX-GDDP-CMIP6 downscaled projections, 0.25 deg;
          historical runs end 2014-12-31, scenario runs start 2015-01-01.
          Requires `model` and `scenario`. Precipitation, max/min
          temperature, humidity. Earth Engine.
        - ``'nasa_power'`` : NASA POWER daily point data, ~0.5 deg,
          1984-present. Precipitation, max/min/mean temperature, humidity.
          Plain HTTPS API; no Earth Engine setup needed.
        - ``'tamsat'`` : TAMSAT v3.1 African rainfall + soil moisture,
          0.05 deg (~4 km), Africa only, 1983-present. Direct download; no
          Earth Engine setup needed.
        - ``'ghcn_daily'``, ``'gsod'`` : point station observations (see
          `station_id`). No Earth Engine setup needed.
        - ``'soil_grid'`` (ISRIC SoilGrids, 250 m), ``'hwsd'`` (FAO HWSD v2,
          ~1 km) : static soil properties (use SoilVariable members).
          Earth Engine.

        Full dataset descriptions: see docs/datasets.md (or the "Datasets"
        page of the documentation site).

        Legacy aliases such as ``'era5'``, ``'agera5'``, ``'nasapower'``,
        ``'nexgddp'``, and ``'ghcn'`` are normalised automatically.

        Earth Engine sources require prior ``earthengine authenticate`` and a
        project ID in the ``GCP_PROJECT_ID`` (or ``GOOGLE_CLOUD_PROJECT`` /
        ``EE_PROJECT_ID``) environment variable.
    location_coord : tuple[float, float], optional
        ``(latitude, longitude)`` in decimal degrees for single-site fetches.
        Required unless `sites` or `sites_csv` is given.
    variables : list, optional
        ``ClimateVariable`` and/or ``SoilVariable`` enum members. Import with
        ``from climate_toolkit.fetch_data.source_data.sources.utils.models
        import ClimateVariable``. Valid ``ClimateVariable`` names: ``rainfall``,
        ``max_temperature``, ``min_temperature``, ``mean_temperature``,
        ``precipitation``, ``wind_speed``, ``solar_radiation``, ``humidity``,
        ``soil_moisture``. Defaults to a standard climate + soil set
        (precipitation, max/min temperature, solar radiation, soil moisture,
        wind speed, humidity, plus SoilGrids properties); for ``ghcn_daily``
        and ``gsod`` the default is precipitation, max_temperature,
        min_temperature.
    date_from, date_to : datetime.date, optional
        Inclusive date range. Both default to today. The range is clipped to
        the source's known coverage window (a warning is printed when
        clipping occurs; a ``ValueError`` is raised if no overlap remains).
    settings : Settings, optional
        Loaded package settings. Auto-loaded via ``Settings.load()`` if not
        provided.
    model, scenario : str, optional
        Required only for ``'nex_gddp'``: a GCM name (e.g. ``'GFDL-ESM4'``,
        ``'ACCESS-CM2'``) and an SSP scenario (e.g. ``'ssp245'``,
        ``'ssp585'``).
    stage : {'raw', 'transformed', 'preprocessed'}
        How far through the pipeline to run: ``'raw'`` downloads only,
        ``'transformed'`` also standardises column names/units, and
        ``'preprocessed'`` (default) additionally applies cleaning/QC.
    verbose : bool, default True
        Print progress and diagnostic messages while fetching.
    cache_dir : str or pathlib.Path, optional
        Project-local cache root for downloaded data (reuse a stable path for
        fast repeat runs). If omitted, supported sources fall back to their
        default project-local cache layout.
    refresh_cache : bool, default False
        Bypass any saved cache files and force a cold fetch.
    sites : list, optional
        Many-site input; when given (or `sites_csv`), the package-native
        batch path is used instead of `location_coord`. Each item may be a
        ``Site``, a ``dict`` with ``name``/``lat``/``lon`` keys, or a
        ``(name, lat, lon)`` tuple. Batch fetching is supported for
        ``nex_gddp`` and the GEE/Xee sources (``agera_5``, ``era_5``,
        ``terraclimate``, ``imerg``, ``chirps_v2``, ``chirps_v3_daily_rnl``,
        ``chirts``, ``cmip_6``).
    sites_csv : str or pathlib.Path, optional
        Path to a CSV of sites with required columns ``name``, ``lat``,
        ``lon``. May be combined with `sites`; duplicates are removed.
    station_id : str, optional
        Station identifier for station-backed sources (``ghcn_daily``,
        ``gsod``). If omitted, the nearest station to `location_coord` is
        used.
    workers : int, default 1
        Bounded worker count for historical GEE/Xee fetch tasks. Mainly
        useful for multi-site or long-period historical runs.

    Returns
    -------
    pandas.DataFrame
        For single-site fetches at the default stage: one row per date with a
        ``date`` column plus one column per requested variable (canonical
        names such as ``precipitation``, ``max_temperature``). Many-site
        fetches additionally include ``site``, ``lat``, and ``lon`` columns
        (and ``model``/``scenario`` for ``nex_gddp``). ``stage='raw'``
        returns source-native column names.

    Examples
    --------
    Daily weather for Nairobi from NASA POWER (no Earth Engine needed):

    >>> from datetime import date
    >>> import climate_toolkit as ct
    >>> from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ...     ClimateVariable,
    ... )
    >>> df = ct.fetch_climate_data(
    ...     source="nasa_power",
    ...     location_coord=(-1.286, 36.817),
    ...     variables=[
    ...         ClimateVariable.precipitation,
    ...         ClimateVariable.max_temperature,
    ...         ClimateVariable.min_temperature,
    ...     ],
    ...     date_from=date(2020, 1, 1),
    ...     date_to=date(2020, 12, 31),
    ... )

    NEX-GDDP projections (requires Earth Engine auth and GCP_PROJECT_ID):

    >>> df = ct.fetch_climate_data(
    ...     source="nex_gddp",
    ...     location_coord=(-1.286, 36.817),
    ...     variables=[ClimateVariable.precipitation,
    ...                ClimateVariable.max_temperature],
    ...     date_from=date(2050, 1, 1),
    ...     date_to=date(2050, 12, 31),
    ...     model="GFDL-ESM4",
    ...     scenario="ssp245",
    ... )
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
    date_from, date_to, coverage_warning = clip_source_date_range(
        source_name,
        date_from,
        date_to,
        settings=settings,
    )
    _emit_coverage_warning(coverage_warning)

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

def resolve_models(model, models):
    """Resolve --model/--models into a list of NEX-GDDP model names.

    - A comma-separated list, or the literal 'all', is accepted on *either*
      flag and expands to several models; 'all' = every model in
      AVAILABLE_MODELS. `--models` takes precedence over `--model`.
    - a single-name `--model` returns [model] unchanged (which may be [None]
      for non-NEX-GDDP sources), leaving validation to the caller.
    Unknown model names raise ValueError listing the valid options.
    """
    spec = models if models else model
    if spec:
        spec = spec.strip()
        if spec.lower() == "all":
            return list(NEX_GDDP_MODELS)
        # Expand when the value is an explicit list (comma) or came from the
        # dedicated --models flag; a bare single --model keeps its old path.
        if models or "," in spec:
            names = [m.strip() for m in spec.split(",") if m.strip()]
            unknown = [m for m in names if m not in NEX_GDDP_MODELS]
            if unknown:
                raise ValueError(
                    f"Invalid model(s): {', '.join(unknown)}. "
                    f"Valid models: {', '.join(NEX_GDDP_MODELS)}"
                )
            return names
    return [model]

def suffix_output_path(path, suffix):
    """Insert '_<suffix>' before the file extension (out.csv -> out_GFDL.csv)."""
    p = Path(path)
    return str(p.with_name(f"{p.stem}_{suffix}{p.suffix}"))

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
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "NEX-GDDP model. A single name, or a comma-separated list / 'all' "
            "(equivalent to --models) to fetch several models, writing one "
            "file per model (output stem + _<model>)."
        ),
    )
    parser.add_argument(
        "--models",
        default=None,
        help=(
            "NEX-GDDP only. Comma-separated list of models, or 'all' for every "
            "available model. Runs the fetch for each model and writes one file "
            "per model (output stem + _<model>). Overrides --model."
        ),
    )
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
    settings = Settings.load()

    batch_requested = bool(args.site or args.sites_csv)

    # Resolve the requested model list (--models overrides --model). 'all' =>
    # every NEX-GDDP model; otherwise a single-item list (possibly [None]).
    try:
        model_list = resolve_models(args.model, args.models)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    multi_model = len(model_list) > 1

    if batch_requested:
        if args.lat is not None or args.lon is not None:
            print("Error: use either --lat/--lon for single-site or --site/--sites-csv for many-site")
            return 1
    else:
        if args.lat is None or args.lon is None:
            print("Error: provide --lat and --lon for single-site fetches, or use --site/--sites-csv")
            return 1

        for model in model_list:
            errors = validate_inputs(
                args.source, args.lat, args.lon, date_from, date_to,
                model, args.scenario,
                allow_coverage_clip=True,
                settings=settings,
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

    for model in model_list:
        if multi_model and not args.quiet:
            print(f"\n=== NEX-GDDP model: {model} ===")
        try:
            df = fetch_data(
                source=args.source,
                location_coord=(args.lat, args.lon) if args.lat is not None and args.lon is not None else None,
                variables=variables,
                date_from=date_from,
                date_to=date_to,
                model=model,
                scenario=args.scenario,
                stage=args.stage,
                verbose=not args.quiet,
                cache_dir=args.cache_dir,
                refresh_cache=args.refresh_cache,
                sites=parsed_sites,
                sites_csv=args.sites_csv,
                station_id=args.station_id,
                workers=args.workers,
                settings=settings,
            )
        except Exception as exc:
            print(f"Error: {format_ee_setup_error(exc)}")
            return 1

        if args.format == "print" or not args.output:
            print(df)
        else:
            # One file per model when several are requested.
            out_path = suffix_output_path(args.output, model) if multi_model else args.output
            save_output(df, out_path, args.format)
            print(f"Saved to {out_path}")

    return 0

if __name__ == "__main__":
    sys.exit(main())

# Examples:
# Full pipeline (default, preprocessed):
# python climate_toolkit/fetch_data/fetch_data.py --source era_5 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-03-05

# Stop at transformed stage:
# python climate_toolkit/fetch_data/fetch_data.py --source chirps_v2 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --stage transformed

# Raw download only:
# python climate_toolkit/fetch_data/fetch_data.py --source chirps_v2 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --stage raw

# NEX-GDDP with model/scenario, saved to CSV:
# python climate_toolkit/fetch_data/fetch_data.py --source nex_gddp --lat -1.286 --lon 36.817 --start 2050-01-01 --end 2050-01-10 --model GFDL-ESM4 --scenario ssp245 --format csv --output nex_gddp_2050.csv

# With a custom variable list:
# python climate_toolkit/fetch_data/fetch_data.py --source era_5 --lat -1.286 --lon 36.817 --start 2020-01-01 --end 2020-01-10 --variables precipitation,max_temperature,min_temperature
