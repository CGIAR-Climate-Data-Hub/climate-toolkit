"""Single-site Xee-backed adapter for non-static GEE datasets.

This keeps single-site historical and non-NEX projection downloads on same
Xee extraction stack used by many-site fetches, while preserving existing
`SourceData.download_variables()` raw-column contract.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Union

import pandas as pd

from ...multi_site import Site
from .utils import models
from .utils.settings import Settings


class DownloadData(models.DataDownloadBase):
    """Single-site wrapper over package-native Xee batch extraction."""

    def __init__(
        self,
        variables: list[Union[models.ClimateVariable, models.SoilVariable]],
        location_coord: tuple[float, float],
        date_from_utc: date,
        date_to_utc: date,
        settings: Settings,
        source: models.ClimateDataset,
        verbose: bool = True,
        cache_dir: str | Path | None = None,
        refresh_cache: bool = False,
    ):
        super().__init__(
            location_coord=location_coord,
            date_from_utc=date_from_utc,
            date_to_utc=date_to_utc,
            variables=variables,
        )
        self.variables = variables
        self.location_coord = location_coord
        self.date_from_utc = date_from_utc
        self.date_to_utc = date_to_utc
        self.settings = settings
        self.source = source
        self.verbose = verbose
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache

    def _site(self) -> Site:
        lat, lon = self.location_coord
        return Site(name="site", lat=float(lat), lon=float(lon))

    @staticmethod
    def _strip_site_columns(frame: pd.DataFrame) -> pd.DataFrame:
        drop_columns = [column for column in ("site", "lat", "lon") if column in frame.columns]
        if not drop_columns:
            return frame
        return frame.drop(columns=drop_columns)

    def download_variables(self) -> pd.DataFrame:
        from ...gee_xee_batch import run_gee_xee_batch_extraction

        raw_df, _, _ = run_gee_xee_batch_extraction(
            source=self.source,
            sites=[self._site()],
            variables=self.variables,
            date_from=self.date_from_utc,
            date_to=self.date_to_utc,
            settings=self.settings,
            cache_dir=self.cache_dir,
            refresh_cache=self.refresh_cache,
            verbose=self.verbose,
        )
        return self._strip_site_columns(raw_df)

    def download_rainfall(self):
        raise NotImplementedError("Use download_variables()")

    def download_temperature(self):
        raise NotImplementedError("Use download_variables()")

    def download_precipitation(self):
        raise NotImplementedError("Use download_variables()")

    def download_windspeed(self):
        raise NotImplementedError("Use download_variables()")

    def download_solar_radiation(self):
        raise NotImplementedError("Use download_variables()")

    def download_humidity(self):
        raise NotImplementedError("Use download_variables()")

    def download_soil_moisture(self):
        raise NotImplementedError("Use download_variables()")


__all__ = ["DownloadData"]
