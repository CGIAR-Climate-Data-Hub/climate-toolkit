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
    },
}


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


def _coerce_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def source_date_coverage_error(
    source: str | ClimateDataset | None,
    date_from: date | datetime | None,
    date_to: date | datetime | None,
) -> str | None:
    source_name = normalize_climate_dataset_name(source)
    if source_name is None:
        return None

    limits = SOURCE_DATE_LIMITS.get(source_name)
    if limits is None:
        return None

    start = _coerce_date(date_from)
    end = _coerce_date(date_to)
    coverage_start = limits["start"]
    coverage_end = limits["end"]
    dataset_label = limits["label"]

    violations = []
    if start is not None and start < coverage_start:
        violations.append(
            f"start={start.isoformat()} is before {coverage_start.isoformat()}"
        )
    if end is not None and end > coverage_end:
        violations.append(
            f"end={end.isoformat()} is after {coverage_end.isoformat()}"
        )

    if not violations:
        return None

    return (
        f"Requested range for source '{source_name}' is outside current coverage "
        f"for {dataset_label} ({coverage_start.isoformat()}..{coverage_end.isoformat()}): "
        f"{'; '.join(violations)}. Use 'agera_5' or 'auto' for later periods."
    )
