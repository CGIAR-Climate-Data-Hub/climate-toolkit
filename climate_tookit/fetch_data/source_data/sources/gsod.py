"""Download daily weather-station observations from NOAA GSOD."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from climate_tookit.weather_station.gsod import fetch_gsod_records

from .utils import models
from .utils.settings import Settings


logger = logging.getLogger(__name__)


class DownloadData(models.DataDownloadBase):
    def __init__(
        self,
        location_coord: tuple[float],
        date_from_utc: date,
        date_to_utc: date,
        variables: list[models.ClimateVariable] | None = None,
        settings: Settings | None = None,
        source: models.ClimateDataset | None = None,
        verbose: bool = True,
        cache_dir=None,
        refresh_cache: bool = False,
        station_id: str | None = None,
    ):
        super().__init__(
            variables=variables or [],
            location_coord=location_coord,
            date_from_utc=date_from_utc,
            date_to_utc=date_to_utc,
        )
        self.location_coord = location_coord
        self.date_from_utc = date_from_utc
        self.date_to_utc = date_to_utc
        self.variables = variables or []
        self.settings = settings or Settings.load()
        self.source = source
        self.verbose = verbose
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache
        self.station_id = station_id

    def download_variables(self) -> pd.DataFrame:
        if not self.variables:
            return pd.DataFrame()

        df = fetch_gsod_records(
            location_coord=self.location_coord,
            date_from=self.date_from_utc,
            date_to=self.date_to_utc,
            variables=self.variables,
            cache_dir=self.cache_dir,
            refresh_cache=self.refresh_cache,
            station_id=self.station_id,
            verbose=self.verbose,
        )
        if df.empty and self.verbose:
            logger.warning("No GSOD rows returned for requested station window.")
        return df

    def download_precipitation(self):
        raise NotImplementedError

    def download_temperature(self):
        raise NotImplementedError

    def download_windspeed(self):
        raise NotImplementedError

    def download_solar_radiation(self):
        raise NotImplementedError

    def download_humidity(self):
        raise NotImplementedError

    def download_rainfall(self):
        raise NotImplementedError

    def download_soil_moisture(self):
        raise NotImplementedError
