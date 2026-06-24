"""Module for defining base classes and enums"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from enum import Enum, auto
from typing import NamedTuple

import pandas as pd


class VariableType(Enum):
    max = auto()
    min = auto()
    mean = auto()


class ClimateVariable(Enum):
    """The enum for climate variables"""

    rainfall = auto()
    max_temperature = auto()
    min_temperature = auto()
    mean_temperature = auto()
    precipitation = auto()
    wind_speed = auto()
    solar_radiation = auto()
    humidity = auto()
    soil_moisture = auto()

class SoilVariable(Enum):
    """Soil-specific variables from ISRIC SoilGrids250m v2.0"""
    root_depth = auto()
    available_water_capacity = auto()
    drainage = auto()
    bulk_density = auto()
    coarse_fragments = auto()
    field_capacity = auto()
    wilting_point = auto()
    ph = auto()
    sand_content = auto()
    clay_content = auto()
    organic_carbon = auto()
    organic_carbon_stock = auto()
    soil_moisture = auto()
    silt_content = auto()
    cation_exchange_capacity = auto()

class ClimateDataset(Enum):
    """The enum to represent climate datasets"""

    agera_5 = auto()
    era_5 = auto()
    terraclimate = auto()
    imerg = auto()
    chirps_v2 = auto()
    chirps = chirps_v2
    chirps_v3_daily_rnl = auto()
    cmip_6 = auto()
    nex_gddp = auto()
    nasa_power = auto()
    tamsat = auto()
    chirts = auto()
    soil_grid = auto()
    hwsd = auto()
    ghcn_daily = auto()
    gsod = auto()


class Cadence(Enum):
    """The enum for cadence levels"""

    hourly = auto()
    daily = auto()
    monthly = auto()


class Location(NamedTuple):
    lat: float
    lon: float


class DataDownloadBase(ABC):
    """An abstract class for creating astandardised interface for downloading data"""

    def __init__(
        self,
        variables: list[ClimateVariable],
        location_coord: tuple[float],
        date_from_utc: date,
        date_to_utc: date,
    ):
        pass

    @abstractmethod
    def download_rainfall():
        """Retrieves rainfall data from the climate database"""
        # The parameters here can be flexible while reusing the ones initialised
        pass

    @abstractmethod
    def download_temperature():
        """Retrieves temperature data from the climate database"""
        # The parameters here can be flexible while reusing the ones initialised
        pass

    @abstractmethod
    def download_precipitation():
        """Retrieves precipitation data from the climate database"""
        pass

    @abstractmethod
    def download_windspeed():
        """Retrieves wind speed data from the climate database"""
        pass

    @abstractmethod
    def download_solar_radiation():
        """Retrieves solar radiation data from the climate database"""
        pass

    @abstractmethod
    def download_humidity():
        """Retrieves humidity data from the climate database"""
        pass

    @abstractmethod
    def download_soil_moisture():
        """Retrieves soil moisture data from the climate database"""
        pass

    @abstractmethod
    def download_variables() -> pd.DataFrame:
        """Retrieves all variables available in the climate database"""
        pass


LEGACY_SOURCE_ALIASES = {
    "chirps": "chirps_v2",
    "agera5": "agera_5",
    "era5": "era_5",
    "nasapower": "nasa_power",
    "power": "nasa_power",
    "nexgddp": "nex_gddp",
    "soilgrids": "soil_grid",
    "ghcn": "ghcn_daily",
    "ghcnd": "ghcn_daily",
    "ghcn_daily": "ghcn_daily",
    "gsod": "gsod",
}

SOURCE_DATE_LIMITS = {
    "era_5": {
        "start": date(1979, 1, 2),
        "end": date(2020, 7, 9),
        "label": "ECMWF/ERA5/DAILY",
        "fallback_hint": "Use 'agera_5' or 'auto' for later periods.",
    },
}
LIVE_SOURCE_DATE_LIMITS_CACHE: dict[tuple[str, str, str | None, str], dict[str, object]] = {}


def normalize_climate_dataset_name(source: str | ClimateDataset | None) -> str | None:
    if source is None:
        return None
    if isinstance(source, ClimateDataset):
        return source.name
    return LEGACY_SOURCE_ALIASES.get(str(source).lower(), str(source).lower())


def accepted_climate_dataset_names() -> list[str]:
    names = {dataset.name for dataset in ClimateDataset}
    names.update(LEGACY_SOURCE_ALIASES.keys())
    return sorted(names)


CLIMATE_VARIABLE_ALIASES = {
    "rain": "precipitation",
    "rainfall": "precipitation",
    "precip": "precipitation",
    "prcp": "precipitation",
    "tmax": "max_temperature",
    "maximum_temperature": "max_temperature",
    "tmin": "min_temperature",
    "minimum_temperature": "min_temperature",
    "tavg": "mean_temperature",
    "tmean": "mean_temperature",
    "average_temperature": "mean_temperature",
    "avg_temperature": "mean_temperature",
    "relative_humidity": "humidity",
    "rh": "humidity",
    "windspeed": "wind_speed",
    "wind": "wind_speed",
    "solar": "solar_radiation",
    "radiation": "solar_radiation",
}


def canonical_climate_variable_name(name: str) -> str:
    token = str(name).strip().lower()
    return CLIMATE_VARIABLE_ALIASES.get(token, token)


def parse_variable_token(name: str):
    climate_name = canonical_climate_variable_name(name)
    if hasattr(ClimateVariable, climate_name):
        return getattr(ClimateVariable, climate_name)

    soil_name = str(name).strip().lower()
    if hasattr(SoilVariable, soil_name):
        return getattr(SoilVariable, soil_name)

    raise ValueError(f"Unknown variable '{name}'")


def _coerce_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _format_date_range(start: date | None, end: date | None) -> str:
    if start is None and end is None:
        return "open-ended"
    if start is None:
        return f"..{end.isoformat()}"
    if end is None:
        return f"{start.isoformat()}.."
    return f"{start.isoformat()}..{end.isoformat()}"


def _resolve_source_limits(
    source_name: str | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> dict[str, object] | None:
    static_limits = SOURCE_DATE_LIMITS.get(source_name)
    if static_limits is None or not prefer_live_gee:
        return static_limits

    live_limits = _fetch_live_source_date_limits(
        source_name,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
    )
    return live_limits or static_limits


def _fetch_live_source_date_limits(
    source_name: str,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
) -> dict[str, object] | None:
    static_limits = SOURCE_DATE_LIMITS.get(source_name)
    if static_limits is None:
        return None

    from .settings import Settings
    from ..xee_common import DEFAULT_EE_OPT_URL, initialize_earth_engine
    import importlib

    resolved_settings = settings or Settings.load()
    data_settings = getattr(resolved_settings, source_name, None)
    gee_image = getattr(data_settings, "gee_image", None)
    if not gee_image:
        return None

    resolved_opt_url = ee_opt_url or DEFAULT_EE_OPT_URL
    cache_key = (source_name, gee_image, ee_project_id, resolved_opt_url)
    cached = LIVE_SOURCE_DATE_LIMITS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        ee_module = importlib.import_module("ee")
        initialize_earth_engine(
            ee_module,
            project_id=ee_project_id,
            ee_opt_url=resolved_opt_url,
        )
        collection = ee_module.ImageCollection(gee_image)
        min_millis = collection.aggregate_min("system:time_start").getInfo()
        max_millis = collection.aggregate_max("system:time_start").getInfo()
        if min_millis is None or max_millis is None:
            return None
        live_limits = {
            "start": datetime.utcfromtimestamp(min_millis / 1000.0).date(),
            "end": datetime.utcfromtimestamp(max_millis / 1000.0).date(),
            "label": static_limits["label"],
            "fallback_hint": static_limits.get("fallback_hint"),
            "coverage_source": "gee_live",
            "gee_image": gee_image,
        }
        LIVE_SOURCE_DATE_LIMITS_CACHE[cache_key] = live_limits
        return live_limits
    except Exception:
        return None


def resolve_source_date_coverage(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> dict[str, object]:
    source_name = normalize_climate_dataset_name(source)
    requested_start = _coerce_date(date_from)
    requested_end = _coerce_date(date_to)
    limits = _resolve_source_limits(
        source_name,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )

    if source_name is None or limits is None:
        return {
            "source_name": source_name,
            "dataset_label": None,
            "requested_start": requested_start,
            "requested_end": requested_end,
            "adjusted_start": requested_start,
            "adjusted_end": requested_end,
            "coverage_start": None,
            "coverage_end": None,
            "fallback_hint": None,
            "clipped": False,
            "has_overlap": True,
            "coverage_source": None,
        }

    coverage_start = limits["start"]
    coverage_end = limits["end"]
    adjusted_start = (
        max(requested_start, coverage_start)
        if requested_start is not None
        else coverage_start
    )
    adjusted_end = (
        min(requested_end, coverage_end)
        if requested_end is not None
        else coverage_end
    )
    has_overlap = adjusted_start <= adjusted_end
    clipped = has_overlap and (
        requested_start != adjusted_start or requested_end != adjusted_end
    )
    return {
        "source_name": source_name,
        "dataset_label": limits["label"],
        "requested_start": requested_start,
        "requested_end": requested_end,
        "adjusted_start": adjusted_start,
        "adjusted_end": adjusted_end,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "fallback_hint": limits.get("fallback_hint"),
        "clipped": clipped,
        "has_overlap": has_overlap,
        "coverage_source": limits.get("coverage_source", "static"),
    }


def source_date_coverage_warning(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> str | None:
    coverage = resolve_source_date_coverage(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    if not coverage["dataset_label"] or not coverage["clipped"]:
        return None

    message = (
        f"Requested range for source '{coverage['source_name']}' is outside current coverage "
        f"for {coverage['dataset_label']} ({coverage['coverage_start'].isoformat()}.."
        f"{coverage['coverage_end'].isoformat()}). Requested: "
        f"{_format_date_range(coverage['requested_start'], coverage['requested_end'])}. "
        f"Adjusted: {_format_date_range(coverage['adjusted_start'], coverage['adjusted_end'])}. "
        "Proceeding with the overlapping window."
    )
    fallback_hint = coverage["fallback_hint"]
    if fallback_hint:
        message = f"{message} {fallback_hint}"
    return message


def source_date_no_overlap_error(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> str | None:
    coverage = resolve_source_date_coverage(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    if not coverage["dataset_label"] or coverage["has_overlap"]:
        return None

    message = (
        f"Requested range for source '{coverage['source_name']}' is outside current coverage "
        f"for {coverage['dataset_label']} ({coverage['coverage_start'].isoformat()}.."
        f"{coverage['coverage_end'].isoformat()}). Requested: "
        f"{_format_date_range(coverage['requested_start'], coverage['requested_end'])}. "
        "No overlapping dates remain after clipping."
    )
    fallback_hint = coverage["fallback_hint"]
    if fallback_hint:
        message = f"{message} {fallback_hint}"
    return message


def clip_source_date_range(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> tuple[date | None, date | None, str | None]:
    coverage = resolve_source_date_coverage(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    no_overlap_error = source_date_no_overlap_error(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    if no_overlap_error:
        raise ValueError(no_overlap_error)
    return (
        coverage["adjusted_start"],
        coverage["adjusted_end"],
        source_date_coverage_warning(
            source,
            date_from,
            date_to,
            settings=settings,
            ee_project_id=ee_project_id,
            ee_opt_url=ee_opt_url,
            prefer_live_gee=prefer_live_gee,
        ),
    )


def source_date_coverage_error(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
    *,
    settings=None,
    ee_project_id: str | None = None,
    ee_opt_url: str | None = None,
    prefer_live_gee: bool = True,
) -> str | None:
    coverage = resolve_source_date_coverage(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    if not coverage["dataset_label"]:
        return None

    no_overlap_error = source_date_no_overlap_error(
        source,
        date_from,
        date_to,
        settings=settings,
        ee_project_id=ee_project_id,
        ee_opt_url=ee_opt_url,
        prefer_live_gee=prefer_live_gee,
    )
    if no_overlap_error:
        return no_overlap_error

    if not coverage["clipped"]:
        return None

    message = (
        f"Requested range for source '{coverage['source_name']}' is outside current coverage "
        f"for {coverage['dataset_label']} ({coverage['coverage_start'].isoformat()}.."
        f"{coverage['coverage_end'].isoformat()}). Requested: "
        f"{_format_date_range(coverage['requested_start'], coverage['requested_end'])}. "
        f"Overlapping window: {_format_date_range(coverage['adjusted_start'], coverage['adjusted_end'])}."
    )
    fallback_hint = coverage["fallback_hint"]
    if fallback_hint:
        message = f"{message} {fallback_hint}"
    return message
