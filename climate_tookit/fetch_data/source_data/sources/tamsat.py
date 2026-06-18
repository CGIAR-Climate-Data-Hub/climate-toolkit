"""
TAMSAT Data Downloader
Downloads daily rainfall (RFE) and soil moisture (SMCL) from the TAMSAT JASMINpublic tree (`gws-access.jasmin.ac.uk/public/tamsat`). TAMSAT publishes one
NetCDF file per day at this endpoint; this module fetches one file perrequested day, selects the gridcell nearest the requested (lat, lon), and
returns the single-time-step value. Missing/failed days return NaN — never 0.

Note: an earlier revision read from the `/monthly/` tree, but those filescontain a single per-month total rather than per-day samples, which produced
all-NaN (or, before that, all-0) daily output. We now read the `/daily/` tree.

Coordinate convention: `location_coord` is `(lat, lon)`, matching the rest of the toolkit.
"""

import logging
import os
import tempfile
import time
import json
import re
import zipfile
import numpy as np
import pandas as pd
import xarray as xr
import requests
from datetime import date, timedelta
from typing import Optional
from pathlib import Path
from urllib.parse import urljoin
from .utils.models import DataDownloadBase, ClimateVariable
from .utils.settings import Settings
from ...multi_site import normalize_cache_coord, safe_coord_fragment

logger = logging.getLogger(__name__)
TAMSAT_CACHE_SCHEMA_VERSION = "v1"
DEFAULT_CACHE_PARENT = Path("outputs/cache")

class DownloadTAMSAT(DataDownloadBase):
    _FAILURE_PREVIEW_LIMIT = 3

    def __init__(
        self,
        location_coord: tuple[float, float],
        date_from_utc: date,
        date_to_utc: date,
        variables: list[ClimateVariable] = None,
        settings: Optional[Settings] = None,
        source=None,
        aggregation: str = "daily",
        verbose: bool = True,
        cache_dir=None,
        refresh_cache: bool = False,
    ):
        super().__init__(variables=variables or [], location_coord=location_coord,
                         date_from_utc=date_from_utc, date_to_utc=date_to_utc)
        self.location_coord = location_coord
        self.date_from_utc = date_from_utc
        self.date_to_utc = date_to_utc
        self.variables = variables or []
        self.settings = settings or Settings.load()
        self.source = source
        self.aggregation = aggregation
        self.verbose = verbose
        self.cache_dir = cache_dir
        self.refresh_cache = refresh_cache
        self.dates = [
            date_from_utc + timedelta(days=i)
            for i in range((date_to_utc - date_from_utc).days + 1)
        ]

    _NETCDF_ENGINES = ("h5netcdf", "netcdf4", "scipy")

    def _cache_root(self) -> Path:
        parent = Path(self.cache_dir) if self.cache_dir else DEFAULT_CACHE_PARENT
        return parent / "tamsat"

    def _cache_coord_base(self, variable_label: str) -> Path:
        lat, lon = self.location_coord
        return (
            self._cache_root()
            / TAMSAT_CACHE_SCHEMA_VERSION
            / variable_label
            / f"lat_{safe_coord_fragment(lat)}_lon_{safe_coord_fragment(lon)}"
        )

    def _archive_cache_path(self, variable_label: str, year: int, extension: str = "zip") -> Path:
        return (
            self._cache_root()
            / TAMSAT_CACHE_SCHEMA_VERSION
            / "archives"
            / variable_label
            / f"{year}.{extension}"
        )

    def _monthly_cache_paths(self, variable_label: str, year: int, month: int) -> tuple[Path, Path]:
        base = self._cache_coord_base(variable_label) / f"{year}" / f"{month:02d}"
        return base / "values.json", base / "manifest.json"

    def _load_month_cache(self, variable_label: str, year: int, month: int) -> dict[str, object]:
        values_path, manifest_path = self._monthly_cache_paths(variable_label, year, month)
        if self.refresh_cache or not values_path.exists() or not manifest_path.exists():
            return {}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = json.loads(values_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if manifest.get("cache_schema_version") != TAMSAT_CACHE_SCHEMA_VERSION:
            return {}
        if manifest.get("variable") != variable_label:
            return {}
        lat, lon = self.location_coord
        if manifest.get("lat") != normalize_cache_coord(lat):
            return {}
        if manifest.get("lon") != normalize_cache_coord(lon):
            return {}
        values = payload.get("values")
        if not isinstance(values, dict):
            return {}
        return {
            key: value
            for key, value in values.items()
            if value is not None
        }

    def _write_month_cache(
        self,
        variable_label: str,
        year: int,
        month: int,
        values: dict[str, float | None],
    ) -> None:
        values_path, manifest_path = self._monthly_cache_paths(variable_label, year, month)
        values_path.parent.mkdir(parents=True, exist_ok=True)
        lat, lon = self.location_coord
        manifest = {
            "cache_schema_version": TAMSAT_CACHE_SCHEMA_VERSION,
            "dataset": "tamsat",
            "variable": variable_label,
            "year": year,
            "month": month,
            "lat": normalize_cache_coord(lat),
            "lon": normalize_cache_coord(lon),
            "day_count": len(values),
        }
        payload = {"values": values}
        temp_values = values_path.with_suffix(values_path.suffix + ".part")
        temp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".part")
        with temp_values.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=True)
        with temp_manifest.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        os.replace(temp_values, values_path)
        os.replace(temp_manifest, manifest_path)

    def _fetch_single_day_value(
        self,
        *,
        session: requests.Session,
        url: str,
        expected_var: str,
        lat0: float,
        lon0: float,
    ) -> float:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        ds, tmp_path = self._open_netcdf_bytes(resp.content)
        if ds is None:
            raise RuntimeError(
                "no working xarray engine could read the TAMSAT file"
            )
        try:
            da = ds[expected_var]
            sel_kwargs = {}
            if "lat" in da.dims:
                sel_kwargs["lat"] = lat0
            if "lon" in da.dims:
                sel_kwargs["lon"] = lon0
            if sel_kwargs:
                da = da.sel(method="nearest", **sel_kwargs)
            arr = np.asarray(da.values, dtype=float).ravel()
            return float(arr[0]) if arr.size else np.nan
        finally:
            ds.close()
            try:
                if tmp_path:
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _extract_value_from_raw_bytes(
        self,
        *,
        raw: bytes,
        expected_var: str,
        lat0: float,
        lon0: float,
    ) -> float:
        ds, tmp_path = self._open_netcdf_bytes(raw)
        if ds is None:
            raise RuntimeError(
                "no working xarray engine could read the TAMSAT file"
            )
        try:
            da = ds[expected_var]
            sel_kwargs = {}
            if "lat" in da.dims:
                sel_kwargs["lat"] = lat0
            if "lon" in da.dims:
                sel_kwargs["lon"] = lon0
            if sel_kwargs:
                da = da.sel(method="nearest", **sel_kwargs)
            arr = np.asarray(da.values, dtype=float).ravel()
            return float(arr[0]) if arr.size else np.nan
        finally:
            ds.close()
            try:
                if tmp_path:
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _discover_rainfall_zip_url(self, session: requests.Session, year: int) -> str | None:
        root = getattr(self.settings.tamsat, "rainfall_zip_url", None)
        if not root:
            return None
        try:
            response = session.get(root, timeout=30)
            response.raise_for_status()
            hrefs = re.findall(r'href=[\"\']([^\"\']+\\.zip)[\"\']', response.text, flags=re.IGNORECASE)
            candidates = []
            for href in hrefs:
                name = href.rsplit("/", 1)[-1]
                if str(year) not in name:
                    continue
                score = 0
                lower_name = name.lower()
                if "daily" in lower_name:
                    score += 2
                if "rfe" in lower_name:
                    score += 2
                if "tamsat" in lower_name:
                    score += 1
                candidates.append((score, urljoin(root.rstrip("/") + "/", href)))
            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                return candidates[0][1]
        except Exception as exc:
            logger.info(
                "TAMSAT yearly-zip listing unavailable for %s: %s",
                year,
                exc,
            )

        guessed_names = [
            f"TAMSATv3.1_rfe_daily_{year}.zip",
            f"TAMSATv3p1_rfe_daily_{year}.zip",
            f"rfe_daily_{year}.zip",
            f"rfe_{year}.zip",
        ]
        for name in guessed_names:
            return urljoin(root.rstrip("/") + "/", name)
        return None

    @staticmethod
    def _extract_date_from_member_name(name: str) -> date | None:
        base = Path(name).name
        match = re.search(r"(\d{4})[_-](\d{2})[_-](\d{2})", base)
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    def _download_rainfall_year_archive(self, session: requests.Session, year: int) -> Path | None:
        archive_path = self._archive_cache_path("precipitation", year)
        if archive_path.exists() and not self.refresh_cache:
            return archive_path
        zip_url = self._discover_rainfall_zip_url(session, year)
        if not zip_url:
            return None
        try:
            response = session.get(zip_url, timeout=60)
            response.raise_for_status()
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = archive_path.with_suffix(archive_path.suffix + ".part")
            with temp_path.open("wb") as handle:
                handle.write(response.content)
            os.replace(temp_path, archive_path)
            logger.info(
                "TAMSAT yearly rainfall zip ready | year=%s | path=%s",
                year,
                archive_path,
            )
            return archive_path
        except Exception as exc:
            logger.info(
                "TAMSAT yearly rainfall zip unavailable for %s: %s",
                year,
                exc,
            )
            return None

    def _populate_rainfall_from_year_zip(
        self,
        *,
        session: requests.Session,
        year: int,
        requested_dates: list[date],
        expected_var: str,
        lat0: float,
        lon0: float,
        values_by_date: dict,
        month_caches: dict[tuple[int, int], dict[str, object]],
        dirty_months: set[tuple[int, int]],
    ) -> tuple[int, list[date]]:
        archive_path = self._download_rainfall_year_archive(session, year)
        if archive_path is None:
            return 0, list(requested_dates)
        fetched = 0
        unresolved_dates: list[date] = []
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                members_by_date = {}
                for member in archive.namelist():
                    dt = self._extract_date_from_member_name(member)
                    if dt is not None:
                        members_by_date[dt] = member
                for dt in requested_dates:
                    day_key = dt.isoformat()
                    month_key = (dt.year, dt.month)
                    month_cache = month_caches.setdefault(
                        month_key,
                        self._load_month_cache("precipitation", dt.year, dt.month),
                    )
                    if day_key in month_cache:
                        continue
                    member = members_by_date.get(dt)
                    if member is None:
                        unresolved_dates.append(dt)
                        continue
                    try:
                        with archive.open(member) as handle:
                            raw = handle.read()
                        value = self._extract_value_from_raw_bytes(
                            raw=raw,
                            expected_var=expected_var,
                            lat0=lat0,
                            lon0=lon0,
                        )
                        month_cache[day_key] = value
                        dirty_months.add(month_key)
                        values_by_date[dt] = value
                        fetched += 1
                    except Exception as exc:
                        logger.info(
                            "TAMSAT yearly rainfall zip member failed for %s: %s",
                            dt.isoformat(),
                            exc,
                        )
                        unresolved_dates.append(dt)
        except Exception as exc:
            logger.info(
                "TAMSAT yearly rainfall zip parse failed for %s: %s",
                year,
                exc,
            )
            return 0, list(requested_dates)
        return fetched, unresolved_dates

    def _open_netcdf_bytes(self, raw: bytes):
        """
        Open NetCDF content from bytes by writing to a temp file and trying explicit engines in order. The temp file is kept alive for the
        lifetime of the returned dataset (caller is responsible for closing the dataset; the temp file is cleaned up by close-handler in
        `_read_nc_variable`). Returns (Dataset, tmp_path) or (None, None).
        We write to disk rather than passing BytesIO because some xarray backends leave lazy references that break when the BytesIO closes.
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".nc", prefix="tamsat_")
        try:
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(raw)
        except Exception:
            try: os.unlink(tmp_path)
            except OSError: pass
            raise

        last_err = None
        for engine in self._NETCDF_ENGINES:
            try:
                ds = xr.open_dataset(tmp_path, engine=engine).load()
                return ds, tmp_path
            except Exception as e:
                last_err = e
                continue
        logger.debug("All NetCDF engines failed; last error: %s", last_err)
        try: os.unlink(tmp_path)
        except OSError: pass
        return None, None

    def _read_nc_variable(self, prefix: str) -> list[float]:
        """
        Read a TAMSAT variable as a daily series at (lat, lon).
        Strategy: TAMSAT's public JASMIN tree publishes one NetCDF file per day
        at `…/{year}/{month:02d}/{prefix}{year}_{month:02d}_{day:02d}.{version}.nc`,
        each containing a single time-step on a (lat, lon) grid. We download
        one file per requested day, select the gridcell nearest the requested
        point, and read the single value. Days that can't be fetched or read
        return NaN — never silently replaced with 0. A single `requests.Session`
        is reused across days for HTTP keep-alive.
        """
        cfg = self.settings.tamsat
        if prefix == "rfe":
            base_url     = cfg.rainfall_url
            expected_var = cfg.variable.get_band("precipitation")
            version      = "v3.1"
            file_prefix  = "rfe"
        elif prefix == "smcl":
            base_url     = cfg.soil_moisture_url
            expected_var = cfg.variable.get_band("soil_moisture")
            version      = "v2.3.1"
            file_prefix  = "sm"
        else:
            raise ValueError(f"Unknown prefix {prefix}")
        if not expected_var:
            raise ValueError(
                f"TAMSAT settings missing band name for prefix {prefix!r}"
            )

        lat0, lon0 = self.location_coord
        values_by_date: dict = {}
        total_days = len(self.dates)
        started_at = time.perf_counter()
        failed_days: list[tuple[date, str]] = []
        cache_hits = 0
        fetched_days = 0

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        variable_label = "precipitation" if prefix == "rfe" else "soil_moisture"
        logger.info(
            "TAMSAT fetch start | variable=%s | location=%.4f,%.4f | period=%s..%s | days=%d",
            variable_label,
            lat0,
            lon0,
            self.date_from_utc.isoformat(),
            self.date_to_utc.isoformat(),
            total_days,
        )

        try:
            month_caches: dict[tuple[int, int], dict[str, object]] = {}
            dirty_months: set[tuple[int, int]] = set()
            if prefix == "rfe":
                requested_dates_by_year: dict[int, list[date]] = {}
                for dt in self.dates:
                    requested_dates_by_year.setdefault(dt.year, []).append(dt)
                for year, requested_dates in sorted(requested_dates_by_year.items()):
                    zip_fetched, unresolved_dates = self._populate_rainfall_from_year_zip(
                        session=session,
                        year=year,
                        requested_dates=requested_dates,
                        expected_var=expected_var,
                        lat0=lat0,
                        lon0=lon0,
                        values_by_date=values_by_date,
                        month_caches=month_caches,
                        dirty_months=dirty_months,
                    )
                    fetched_days += zip_fetched
                    if unresolved_dates:
                        logger.info(
                            "TAMSAT yearly rainfall zip partial fallback | year=%s | unresolved_days=%d",
                            year,
                            len(unresolved_dates),
                        )
            for index, dt in enumerate(self.dates, start=1):
                month_key = (dt.year, dt.month)
                if month_key not in month_caches:
                    month_caches[month_key] = self._load_month_cache(
                        variable_label,
                        dt.year,
                        dt.month,
                    )
                month_cache = month_caches[month_key]
                day_key = dt.isoformat()
                if dt in values_by_date:
                    if (
                        index == 1
                        or index == total_days
                        or index % max(total_days // 4, 1) == 0
                    ):
                        elapsed = time.perf_counter() - started_at
                        logger.info(
                            "TAMSAT progress | variable=%s | %d/%d day(s) | elapsed=%.1fs | cache_hits=%d | fetched=%d | failures=%d",
                            variable_label,
                            index,
                            total_days,
                            elapsed,
                            cache_hits,
                            fetched_days,
                            len(failed_days),
                        )
                    continue
                if day_key in month_cache:
                    cached_value = month_cache[day_key]
                    values_by_date[dt] = float(cached_value) if cached_value is not None else np.nan
                    cache_hits += 1
                    if (
                        index == 1
                        or index == total_days
                        or index % max(total_days // 4, 1) == 0
                    ):
                        elapsed = time.perf_counter() - started_at
                        logger.info(
                            "TAMSAT progress | variable=%s | %d/%d day(s) | elapsed=%.1fs | cache_hits=%d | fetched=%d | failures=%d",
                            variable_label,
                            index,
                            total_days,
                            elapsed,
                            cache_hits,
                            fetched_days,
                            len(failed_days),
                        )
                    continue
                file_name = (
                    f"{file_prefix}{dt.year}_{dt.month:02d}_{dt.day:02d}"
                    f".{version}.nc"
                )
                url = (
                    f"{base_url.rstrip('/')}/{dt.year}/{dt.month:02d}/{file_name}"
                )
                try:
                    value = self._fetch_single_day_value(
                        session=session,
                        url=url,
                        expected_var=expected_var,
                        lat0=lat0,
                        lon0=lon0,
                    )
                    values_by_date[dt] = value
                    month_cache[day_key] = value
                    dirty_months.add(month_key)
                    fetched_days += 1
                except Exception as e:
                    failed_days.append((dt, str(e)))
                    values_by_date[dt] = np.nan
                if (
                    index == 1
                    or index == total_days
                    or index % max(total_days // 4, 1) == 0
                ):
                    elapsed = time.perf_counter() - started_at
                    logger.info(
                        "TAMSAT progress | variable=%s | %d/%d day(s) | elapsed=%.1fs | cache_hits=%d | fetched=%d | failures=%d",
                        variable_label,
                        index,
                        total_days,
                        elapsed,
                        cache_hits,
                        fetched_days,
                        len(failed_days),
                    )
            for year, month in sorted(dirty_months):
                self._write_month_cache(
                    variable_label,
                    year,
                    month,
                    month_caches[(year, month)],
                )
        finally:
            session.close()

        elapsed_total = time.perf_counter() - started_at
        if failed_days:
            preview = "; ".join(
                f"{dt.isoformat()} ({msg})"
                for dt, msg in failed_days[: self._FAILURE_PREVIEW_LIMIT]
            )
            if len(failed_days) > self._FAILURE_PREVIEW_LIMIT:
                preview += f"; ... +{len(failed_days) - self._FAILURE_PREVIEW_LIMIT} more"
            logger.warning(
                "TAMSAT fetch completed with failures | variable=%s | ok=%d | failed=%d | cache_hits=%d | fetched=%d | elapsed=%.1fs | sample_failures=%s",
                variable_label,
                total_days - len(failed_days),
                len(failed_days),
                cache_hits,
                fetched_days,
                elapsed_total,
                preview,
            )
        else:
            logger.info(
                "TAMSAT fetch complete | variable=%s | ok=%d | failed=0 | cache_hits=%d | fetched=%d | elapsed=%.1fs",
                variable_label,
                total_days,
                cache_hits,
                fetched_days,
                elapsed_total,
            )

        return [values_by_date.get(dt, np.nan) for dt in self.dates]

    def download_precipitation(self):
        return self._read_nc_variable("rfe")

    def download_rainfall(self):
        return self.download_precipitation()

    def download_soil_moisture(self):
        return self._read_nc_variable("smcl")

    def download_temperature(self):
        raise NotImplementedError("TAMSAT does not provide temperature data")

    def download_windspeed(self):
        raise NotImplementedError("TAMSAT does not provide wind speed data")

    def download_solar_radiation(self):
        raise NotImplementedError("TAMSAT does not provide solar radiation data")

    def download_humidity(self):
        raise NotImplementedError("TAMSAT does not provide humidity data")

    def download_variables(self) -> pd.DataFrame:
        """
        Returns a DataFrame with a `date` column plus one column per requested variable that TAMSAT actually provides. Unsupported variables (e.g.
        temperature, wind, radiation, humidity) are skipped with a warning — we do NOT fabricate zero-filled columns for variables this dataset
        doesn't produce.

        Comparison is by `.name` (string), not by enum identity, because depending on how callers set up `sys.path` (e.g. compare_datasets adds
        both `source_data/` and `source_data/sources/`), `ClimateVariable` can be loaded under two different module paths and yield two distinct
        enum classes whose members do not compare equal.
        """
        data_dict = {}
        for variable in self.variables:
            name = getattr(variable, "name", str(variable))
            if name in ("rainfall", "precipitation"):
                data_dict["precipitation"] = self.download_precipitation()
            elif name == "soil_moisture":
                data_dict["soil_moisture"] = self.download_soil_moisture()
            else:
                logger.warning(
                    "TAMSAT does not provide '%s'; skipping (no column emitted).",
                    name,
                )
        return pd.DataFrame({"date": self.dates, **data_dict})
