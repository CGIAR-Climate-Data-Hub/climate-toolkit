"""
This module provides functionality to download DAILY climate data
from the NASA POWER API.

Coordinate convention: `location_coord` is `(lat, lon)`, matching every other
source module and every caller in the toolkit (compare_datasets, climatology,
calculate_hazards, season_analysis, etc.).
"""

import json
import logging
import os
import pandas as pd
import requests
from datetime import date
from pathlib import Path
from typing import Optional
from .utils import models
from .utils.settings import Settings
from collections import defaultdict
from ...multi_site import normalize_cache_coord, safe_coord_fragment

logger = logging.getLogger(__name__)
NASA_POWER_CACHE_SCHEMA_VERSION = "v1"
DEFAULT_CACHE_PARENT = Path("outputs/cache")

class DownloadData(models.DataDownloadBase):
    def __init__(
        self,
        location_coord: tuple[float],
        date_from_utc: date,
        date_to_utc: date,
        variables: list[models.ClimateVariable] = None,
        aggregation: Optional[str] = None,
        settings: Settings = None,
        source: models.ClimateDataset = None,
        verbose: bool = True,
        cache_dir=None,
        refresh_cache: bool = False,
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
        self.aggregation = aggregation
        self.settings = settings or Settings.load()
        self.source = source
        self.verbose = verbose
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache

    def _cache_base_dir(self) -> Path:
        lat, lon = self.location_coord
        cache_root = self._cache_root()
        return (
            cache_root
            / NASA_POWER_CACHE_SCHEMA_VERSION
            / f"lat_{safe_coord_fragment(lat)}_lon_{safe_coord_fragment(lon)}"
        )

    def _cache_root(self) -> Path:
        parent = Path(self.cache_dir) if self.cache_dir else DEFAULT_CACHE_PARENT
        return parent / "nasa_power"

    def _legacy_cache_root(self) -> Path | None:
        if self.cache_dir is None:
            return None
        return Path(self.cache_dir)

    def _requested_variable_names(self) -> list[str]:
        return sorted(v.name for v in self.variables)

    def _cache_paths(self) -> tuple[Path, Path]:
        variable_fragment = "-".join(self._requested_variable_names()) or "no_variables"
        filename = (
            f"{self.date_from_utc.isoformat()}_{self.date_to_utc.isoformat()}_"
            f"{variable_fragment}.json"
        )
        data_path = self._cache_base_dir() / filename
        manifest_path = self._cache_base_dir() / f"{filename}.manifest.json"
        return data_path, manifest_path

    def _legacy_cache_paths(self) -> tuple[Path, Path] | None:
        legacy_root = self._legacy_cache_root()
        if legacy_root is None:
            return None
        lat, lon = self.location_coord
        variable_fragment = "-".join(self._requested_variable_names()) or "no_variables"
        filename = (
            f"{self.date_from_utc.isoformat()}_{self.date_to_utc.isoformat()}_"
            f"{variable_fragment}.json"
        )
        base = (
            legacy_root
            / NASA_POWER_CACHE_SCHEMA_VERSION
            / f"lat_{safe_coord_fragment(lat)}_lon_{safe_coord_fragment(lon)}"
        )
        return base / filename, base / f"{filename}.manifest.json"

    def _read_cached_frame(self, data_path: Path) -> pd.DataFrame:
        frame = pd.read_json(data_path)
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
        return frame

    def _expected_dates(self) -> pd.DatetimeIndex:
        return pd.date_range(self.date_from_utc, self.date_to_utc, freq="D")

    def _integrity_summary(self, frame: pd.DataFrame) -> dict[str, object]:
        expected_dates = self._expected_dates()
        if frame.empty or "date" not in frame.columns:
            return {
                "complete": False,
                "row_count": len(frame),
                "expected_rows": len(expected_dates),
            }
        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"]).dt.tz_localize(None)
        actual_dates = pd.DatetimeIndex(working["date"].sort_values().unique())
        complete = len(actual_dates) == len(expected_dates) and actual_dates.equals(expected_dates)
        return {
            "complete": complete,
            "row_count": len(frame),
            "expected_rows": len(expected_dates),
        }

    def _build_manifest(self, frame: pd.DataFrame) -> dict[str, object]:
        lat, lon = self.location_coord
        return {
            "cache_schema_version": NASA_POWER_CACHE_SCHEMA_VERSION,
            "dataset": "nasa_power",
            "start_date": self.date_from_utc.isoformat(),
            "end_date": self.date_to_utc.isoformat(),
            "lat": normalize_cache_coord(lat),
            "lon": normalize_cache_coord(lon),
            "requested_variables": self._requested_variable_names(),
            "parameter_codes": self._get_parameter_codes(),
            "columns": list(frame.columns),
            "integrity": self._integrity_summary(frame),
        }

    def _write_cache(
        self,
        data_path: Path,
        manifest_path: Path,
        frame: pd.DataFrame,
        manifest: dict[str, object],
    ) -> None:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        temp_data = data_path.with_suffix(data_path.suffix + ".part")
        temp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".part")
        with temp_data.open("w", encoding="utf-8") as handle:
            handle.write(frame.to_json(orient="records", date_format="iso", indent=2))
        with temp_manifest.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        os.replace(temp_data, data_path)
        os.replace(temp_manifest, manifest_path)

    def _load_valid_cache_from_paths(self, data_path: Path, manifest_path: Path) -> pd.DataFrame | None:
        partial_paths = [
            data_path.with_suffix(data_path.suffix + ".part"),
            manifest_path.with_suffix(manifest_path.suffix + ".part"),
        ]
        if any(path.exists() for path in partial_paths):
            logger.info("Ignoring stale partial NASA POWER cache; refetching.")
        if self.refresh_cache or not data_path.exists() or not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.info("NASA POWER manifest unreadable; refetching.")
            return None
        if not manifest.get("integrity", {}).get("complete", False):
            logger.info("NASA POWER manifest incomplete; refetching.")
            return None
        if manifest.get("requested_variables") != self._requested_variable_names():
            logger.info("NASA POWER cache variable mismatch; refetching.")
            return None
        frame = self._read_cached_frame(data_path)
        if not self._integrity_summary(frame).get("complete", False):
            logger.info("NASA POWER cached data incomplete; refetching.")
            return None
        if self.verbose:
            logger.info(
                "NASA POWER cache hit for lat=%s lon=%s %s..%s.",
                *self.location_coord,
                self.date_from_utc,
                self.date_to_utc,
            )
        return frame

    def _load_valid_cache(self) -> pd.DataFrame | None:
        data_path, manifest_path = self._cache_paths()
        frame = self._load_valid_cache_from_paths(data_path, manifest_path)
        if frame is not None:
            return frame
        legacy_paths = self._legacy_cache_paths()
        if legacy_paths is None:
            return None
        legacy_data_path, legacy_manifest_path = legacy_paths
        legacy_frame = self._load_valid_cache_from_paths(legacy_data_path, legacy_manifest_path)
        if legacy_frame is not None:
            logger.info(
                "NASA POWER using legacy cache layout at %s; consider rerunning to rewrite under %s.",
                legacy_data_path,
                self._cache_root(),
            )
            return legacy_frame
        return None

    def _get_parameter_codes(self) -> list[str]:
        """Map requested variables to NASA POWER parameter codes."""
        params = []

        var_names = [v.name for v in self.variables]

        # NASA POWER has limited precipitation data (only PRECTOTCORR)
        if 'precipitation' in var_names:
            params.append("PRECTOTCORR")

        # T2M covers temperature (we'll use specific max/min if available)
        if 'max_temperature' in var_names or 'min_temperature' in var_names or 'temperature' in var_names:
            params.append("T2M")
            params.append("T2M_MAX") 
            params.append("T2M_MIN") 

        if 'humidity' in var_names:
            params.append("RH2M")

        if 'solar_radiation' in var_names:
            params.append("ALLSKY_SFC_SW_DWN")

        if 'wind_speed' in var_names:
            params.append("WS2M")

        return params

    def _fetch_daily_data(self) -> dict:
        """Fetch DAILY data from NASA POWER API."""
        params = self._get_parameter_codes()
        if not params:
            raise ValueError("No valid parameters to request from NASA POWER.")

        # Toolkit-wide convention: location_coord is (lat, lon).
        lat, lon = self.location_coord

        # Format dates as YYYYMMDD for daily data
        start_date = self.date_from_utc.strftime("%Y%m%d")
        end_date = self.date_to_utc.strftime("%Y%m%d")

        # CRITICAL: Use temporal-api=daily for daily data
        url = (
            f"{self.settings.nasa_power.endpoint}/point"
            f"?start={start_date}"
            f"&end={end_date}"
            f"&latitude={lat}&longitude={lon}" 
            f"&community=AG"
            f"&parameters={','.join(params)}"
            f"&format=JSON"
            f"&temporal-api=daily"
        )

        logger.info(
            "Fetching NASA POWER for lat=%s lon=%s %s..%s vars=%s",
            lat,
            lon,
            self.date_from_utc,
            self.date_to_utc,
            ",".join(self._requested_variable_names()),
        )
        logger.debug("NASA POWER URL: %s", url)
        logger.debug("NASA POWER Coordinates: lat=%s, lon=%s", lat, lon)

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("properties", {}).get("parameter", {})
        except Exception as e:
            logger.error(f"Error fetching NASA POWER data: {e}")
            return {}

    def download_variables(self) -> pd.DataFrame:
        if not self.variables:
            return pd.DataFrame()

        cached = self._load_valid_cache()
        if cached is not None:
            return cached

        try:
            raw_data = self._fetch_daily_data()
        except ValueError as e:
            logger.error(str(e))
            return pd.DataFrame()

        if not raw_data:
            logger.warning("No data returned from NASA POWER")
            return pd.DataFrame()

        data_by_date = defaultdict(dict)
        available_vars = set()

        for var_code, values in raw_data.items():
            for dt_str, val in values.items():
                if len(dt_str) == 8 and dt_str.isdigit():
                    try:
                        dt = pd.to_datetime(dt_str, format="%Y%m%d")

                        if var_code == "PRECTOTCORR":
                            data_by_date[dt]["precipitation"] = val
                            available_vars.add("precipitation")
                        elif var_code == "T2M_MAX":
                            data_by_date[dt]["max_temperature"] = val
                            available_vars.add("max_temperature")
                        elif var_code == "T2M_MIN":
                            data_by_date[dt]["min_temperature"] = val
                            available_vars.add("min_temperature")
                        elif var_code == "T2M":
                            # Only use T2M if we don't have T2M_MAX/MIN
                            if "max_temperature" not in data_by_date[dt]:
                                data_by_date[dt]["max_temperature"] = val
                            if "min_temperature" not in data_by_date[dt]:
                                data_by_date[dt]["min_temperature"] = val
                            available_vars.update(["max_temperature", "min_temperature"])
                        elif var_code == "RH2M":
                            data_by_date[dt]["humidity"] = val
                            available_vars.add("humidity")
                        elif var_code == "ALLSKY_SFC_SW_DWN":
                            data_by_date[dt]["solar_radiation"] = val
                            available_vars.add("solar_radiation")
                        elif var_code == "WS2M":
                            data_by_date[dt]["wind_speed"] = val
                            available_vars.add("wind_speed")
                    except Exception as e:
                        logger.warning(f"Error parsing date {dt_str}: {e}")
                        continue

        df = pd.DataFrame([
            {"date": dt, **vals} for dt, vals in sorted(data_by_date.items())
        ])

        requested_vars = [v.name for v in self.variables]

        for var in requested_vars:
            if var not in available_vars:
                logger.warning(f"NASA POWER does not have {var} data")

        logger.info("NASA POWER returned %s daily records", len(df))
        logger.debug("NASA POWER date range: %s to %s", df["date"].min(), df["date"].max())
        logger.debug("NASA POWER available columns: %s", df.columns.tolist())
        logger.debug("NASA POWER requested variables: %s", requested_vars)

        final_columns = ["date"] + [col for col in requested_vars if col in df.columns]
        result = df[final_columns] if final_columns else pd.DataFrame()
        if not result.empty:
            data_path, manifest_path = self._cache_paths()
            manifest = self._build_manifest(result)
            self._write_cache(data_path, manifest_path, result, manifest)
            logger.info("Saved NASA POWER cache to %s", data_path)
        return result

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