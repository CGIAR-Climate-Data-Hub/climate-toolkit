"""Validated point extraction from public CHC cloud mirrors.

Providers are mirrors of named scientific products, never substitute datasets.
Cache chunks contain decoded source-native values plus immutable provenance.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import warnings
import sys
import os

import numpy as np
import pandas as pd
import requests

from .backend_policy import resolve_policy
from .multi_site import Site, load_sites, site_date_integrity_summary


CACHE_VERSION = 2
CAPABILITIES = {
    "chirps_v3_daily_rnl": {"precipitation": "precipitation"},
    "chirts_era5": {"max_temperature": "Tmax", "min_temperature": "Tmin"},
}
HF_REPOS = {
    "chirps_v3_daily_rnl": "aaguilar90/chirps-v3-daily-rnl",
    "chirts_era5": "aaguilar90/chirts-era5-daily",
}
STAC_URL = "https://stac.dynamical.org/ucsb-chc-chirps-analysis-final/collection.json"


class BackendUnavailable(RuntimeError):
    """Provider failed or cannot supply the entire requested window."""


class DataQualityError(ValueError):
    """Scientific values cannot safely enter analysis; never retry as an outage."""


def _json_get(url):
    # Two bounded attempts. Respect short Retry-After values without allowing an
    # unavailable mirror to stall the entire workflow indefinitely.
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=(10, 30))
        except (requests.Timeout, requests.ConnectionError):
            if attempt:
                raise
            time.sleep(1)
            continue
        if response.status_code not in {429, 500, 502, 503, 504} or attempt:
            response.raise_for_status()
            return response.json()
        try:
            delay = min(2.0, max(0.0, float(response.headers.get("Retry-After", 1))))
        except ValueError:
            delay = 1.0
        time.sleep(delay)


@contextmanager
def open_provider(source, backend, workers=1):
    """Open anonymous, revision-pinned storage with bounded transport retries."""
    if sys.version_info < (3, 12):
        raise BackendUnavailable(
            "Direct cloud backends require Python >=3.12 and climate-toolkit[cloud]"
        )
    try:
        import xarray as xr
        import zarr
        import dask  # noqa: F401
    except ImportError as exc:
        raise BackendUnavailable("Install climate-toolkit[cloud] for direct cloud access") from exc
    ds = None
    try:
        if backend == "huggingface":
            import aiohttp

            repo = HF_REPOS[source]
            revision = _json_get(f"https://huggingface.co/api/datasets/{repo}")["sha"]
            store = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{repo.split('/')[-1]}.zarr"
            options = {
                "client_kwargs": {"timeout": aiohttp.ClientTimeout(total=45), "trust_env": True}
            }
            with zarr.config.set({"async.concurrency": workers, "async.timeout": 60}):
                ds = xr.open_zarr(store, consolidated=True, chunks={}, storage_options=options)
            identity = str(ds.attrs.get("source", ""))
            expected = "CHIRTS-ERA5" if source == "chirts_era5" else "CHIRPS v3.0 daily final RNL"
            if expected not in identity:
                raise BackendUnavailable(
                    f"Unexpected product identity from {backend}: {identity!r}"
                )
            names = (
                {"precipitation": "precip"} if source.startswith("chirps") else CAPABILITIES[source]
            )
            rename = {"lat": "latitude", "lon": "longitude"}
            ds = ds.rename({key: value for key, value in rename.items() if key in ds.coords})
        elif backend == "dynamical" and source == "chirps_v3_daily_rnl":
            try:
                import icechunk
            except ImportError as exc:
                raise BackendUnavailable(
                    "Install climate-toolkit[cloud] for Dynamical access"
                ) from exc
            if not hasattr(icechunk, "http_storage"):
                raise BackendUnavailable("Dynamical requires icechunk>=2.3")
            catalog = _json_get(STAC_URL)
            if catalog.get("id") != "ucsb-chc-chirps-analysis-final":
                raise BackendUnavailable("Unexpected Dynamical product identity")
            store = catalog["assets"]["icechunk-https"]["href"]
            config = icechunk.RepositoryConfig.default()
            config.storage = icechunk.StorageSettings(
                retries=icechunk.StorageRetriesSettings(max_tries=2, max_backoff_ms=1000),
            )
            repo = icechunk.Repository.open(
                icechunk.http_storage(store, opts={"timeout": "45s", "connect_timeout": "10s"}),
                config=config,
            )
            session = repo.readonly_session("main")
            revision = session.snapshot_id
            ds = xr.open_zarr(session.store, consolidated=False, chunks={})
            names = {"precipitation": "precipitation_surface"}
        else:
            raise ValueError(f"Backend {backend!r} does not support {source!r}")
        provenance = {
            "source": source,
            "backend": backend,
            "revision": str(revision),
            "store": store,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "cache_schema_version": CACHE_VERSION,
        }
        yield ds, names, provenance
    finally:
        if ds is not None:
            ds.close()


def _validate_request(source, sites, variables, start, end):
    if source not in CAPABILITIES:
        raise ValueError(f"No direct adapters for {source!r}")
    if start > end:
        raise ValueError("Start date must be before end date")
    names = list(dict.fromkeys(getattr(v, "name", str(v)) for v in variables))
    names = ["precipitation" if v == "rainfall" else v for v in names]
    unsupported = set(names) - CAPABILITIES[source].keys()
    if unsupported or not names:
        raise ValueError(
            f"{source} supports only {', '.join(CAPABILITIES[source])}; requested {names}"
        )
    north = 70 if source == "chirts_era5" else 60
    for site in sites:
        if not (math.isfinite(site.lat) and math.isfinite(site.lon)):
            raise ValueError("Site coordinates must be finite")
        if not (-60 <= site.lat <= north and -180 <= site.lon <= 180):
            raise ValueError(
                f"Site {site.name!r} outside {source} domain: 60 S to {north} N, 180 W to 180 E"
            )
    return names


def _extract(ds, names, source, sites, variables, start, end, workers):
    import xarray as xr
    import dask
    import zarr

    expected = pd.date_range(start, end)
    times = pd.DatetimeIndex(ds.time.values)
    if times.has_duplicates or not times.is_monotonic_increasing:
        raise BackendUnavailable("Provider has duplicate or unordered dates")
    if not expected.isin(times).all():
        raise BackendUnavailable(
            f"Incomplete provider coverage: {times.min()}..{times.max()}, requested {start}..{end}"
        )
    native = [names[v] for v in variables]
    missing = set(native) - set(ds.data_vars)
    if missing:
        raise BackendUnavailable(f"Provider missing required variables: {sorted(missing)}")
    for key in native:
        units = ds[key].attrs.get("units")
        acceptable = (
            {"kg m-2 s-1", "kg/m^2/s"}
            if key == "precipitation_surface"
            else {"mm"}
            if key == "precip"
            else {"degC", "degree_Celsius", "degrees_Celsius"}
        )
        if units not in acceptable:
            raise BackendUnavailable(f"Unexpected units for {key}: {units!r}")
        if set(ds[key].dims) != {"time", "latitude", "longitude"}:
            raise BackendUnavailable(f"Unexpected dimensions for {key}: {ds[key].dims}")
    # Resolve indices explicitly: nearest ties consistently choose lower numeric
    # coordinate, regardless of axis order. Refuse a different grid resolution.
    indices = {}
    cells = {}
    for axis, values in (
        ("latitude", [s.lat for s in sites]),
        ("longitude", [s.lon for s in sites]),
    ):
        grid = np.asarray(ds[axis].values)
        if grid.ndim != 1 or len(grid) < 2 or not np.all(np.isfinite(grid)):
            raise BackendUnavailable(f"Invalid {axis} coordinate")
        diffs = np.diff(grid)
        if not (np.all(diffs > 0) or np.all(diffs < 0)) or not np.allclose(
            np.abs(diffs), 0.05, atol=2e-5
        ):
            raise BackendUnavailable(f"Expected regular 0.05-degree {axis} grid")
        ix = []
        for value in values:
            delta = np.abs(grid - value)
            ties = np.flatnonzero(np.isclose(delta, delta.min(), atol=1e-7, rtol=0))
            i = ties[np.argmin(grid[ties])]
            if delta[i] > 0.02502:
                raise ValueError(f"Requested {axis} {value} outside provider grid")
            ix.append(i)
        indices[axis] = xr.DataArray(ix, dims="point")
        cells[axis] = grid[ix].tolist()
    # Lazy vectorized point selection shares source chunks across nearby sites.
    subset = ds[native].sel(time=slice(str(start), str(end))).isel(indices)
    with (
        dask.config.set(scheduler="threads", num_workers=workers),
        zarr.config.set({"async.concurrency": workers, "async.timeout": 60}),
    ):
        subset.load()
    frames = []
    for i, site in enumerate(sites):
        frame = pd.DataFrame(
            {"date": expected, "site": site.name, "lat": site.lat, "lon": site.lon}
        )
        for variable in variables:
            key = names[variable]
            values = np.asarray(subset[key].isel(point=i).values, dtype=float)
            if key == "precipitation_surface":
                values = values * 86400.0
            frame[CAPABILITIES[source][variable]] = values
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), {
        "coverage": [times.min().isoformat(), times.max().isoformat()],
        "source_units": {key: ds[key].attrs["units"] for key in native},
        "output_units": {
            CAPABILITIES[source][v]: "mm/day" if v == "precipitation" else "degC" for v in variables
        },
        "selected_cells": [
            {"site": s.name, "lat": cells["latitude"][i], "lon": cells["longitude"][i]}
            for i, s in enumerate(sites)
        ],
        "conversion": "daily mean kg m-2 s-1 * 86400 -> mm/day"
        if "precipitation_surface" in native
        else "CF scale/offset and fill decoded by xarray",
    }


def _cache_path(root, request):
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    return (
        Path(root or "outputs/cache")
        / "direct_cloud"
        / f"v{CACHE_VERSION}"
        / request["source"]
        / request["backend"]
        / f"{digest}.json"
    )


def _read_cache(path, request):
    try:
        envelope = json.loads(path.read_text())
        payload = envelope["payload"]
        if hashlib.sha256(payload.encode()).hexdigest() != envelope["sha256"]:
            return None
        cached = json.loads(payload)
        if cached["request"] != request:
            return None
        frame = pd.DataFrame(cached["frame"], columns=cached["columns"])
        frame["date"] = pd.to_datetime(frame["date"])
        for column, dtype in cached["dtypes"].items():
            if column != "date":
                frame[column] = frame[column].astype(dtype)
        frame.attrs["data_provenance"] = [cached["provenance"]]
        return frame
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path, request, frame, provenance):
    serial = frame.copy()
    serial["date"] = serial["date"].dt.strftime("%Y-%m-%d")
    serial = serial.astype(object).where(pd.notna(serial), None)
    # Python's JSON encoder round-trips binary floats, unlike DataFrame.to_json's
    # maximum 15 decimal digits, which can move requested site coordinates.
    payload = json.dumps(
        {
            "request": request,
            "frame": serial.to_dict("list"),
            "columns": list(frame.columns),
            "dtypes": {c: str(d) for c, d in frame.dtypes.items()},
            "provenance": provenance,
        },
        sort_keys=True,
        allow_nan=False,
    )
    envelope = json.dumps(
        {"payload": payload, "sha256": hashlib.sha256(payload.encode()).hexdigest()}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(envelope)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _year_requests(source, backend, sites, variables, start, end):
    for year in range(start.year, end.year + 1):
        yield {
            "schema": CACHE_VERSION,
            "source": source,
            "backend": backend,
            "sites": [[s.name, float(s.lat), float(s.lon)] for s in sites],
            "variables": variables,
            "start": str(max(start, date(year, 1, 1))),
            "end": str(min(end, date(year, 12, 31))),
        }


def estimate_read_work(ds, names, sites, variables, start, end):
    """Upper estimate of source chunk bytes decoded, not network transfer size."""
    indices = {}
    for axis, values in (
        ("latitude", [s.lat for s in sites]),
        ("longitude", [s.lon for s in sites]),
    ):
        grid = np.asarray(ds[axis].values)
        indices[axis] = [int(np.abs(grid - v).argmin()) for v in values]
    times = pd.DatetimeIndex(ds.time.values)
    active = np.flatnonzero((times >= pd.Timestamp(start)) & (times <= pd.Timestamp(end)))
    total = 0
    for variable in variables:
        array = ds[names[variable]]
        shape = array.encoding.get("chunks", array.shape)
        chunks = dict(zip(array.dims, shape))
        spatial = {
            (i // chunks["latitude"], j // chunks["longitude"])
            for i, j in zip(indices["latitude"], indices["longitude"])
        }
        time_chunks = len(set(active // chunks["time"]))
        total += (
            len(spatial)
            * time_chunks
            * math.prod(shape)
            * np.dtype(array.encoding.get("dtype", array.dtype)).itemsize
        )
    return int(total)


def _provider_fetch(
    source,
    backend,
    sites,
    variables,
    start,
    end,
    cache_dir,
    refresh_cache,
    workers,
    cache_only=False,
):
    requests_ = list(_year_requests(source, backend, sites, variables, start, end))
    paths = [_cache_path(cache_dir, request) for request in requests_]
    frames = [
        None if refresh_cache else _read_cache(path, req) for path, req in zip(paths, requests_)
    ]
    revisions = {f.attrs["data_provenance"][0]["revision"] for f in frames if f is not None}
    if any(f is None for f in frames) or len(revisions) != 1:
        if cache_only:
            raise BackendUnavailable("No complete cache for this provider")
        with open_provider(source, backend, workers) as (ds, names, provenance):
            if not {"time", "latitude", "longitude"}.issubset(ds.coords):
                raise BackendUnavailable("Provider missing time/latitude/longitude coordinates")
            if not set(names[v] for v in variables).issubset(ds.data_vars):
                raise BackendUnavailable("Provider missing requested variables")
            work = estimate_read_work(ds, names, sites, variables, start, end)
            budget = int(os.getenv("CLIMATE_TOOLKIT_MAX_DECODED_BYTES", str(4 * 1024**3)))
            if budget <= 0:
                raise ValueError("CLIMATE_TOOLKIT_MAX_DECODED_BYTES must be positive")
            if work > budget:
                raise BackendUnavailable(
                    f"Estimated chunk read work {work / 1024**3:.2f} GiB exceeds {budget / 1024**3:.2f} GiB budget; "
                    "use another backend, fewer dispersed sites, or explicitly raise CLIMATE_TOOLKIT_MAX_DECODED_BYTES"
                )
            provenance["estimated_source_chunk_bytes"] = work
            for i, (req, path) in enumerate(zip(requests_, paths)):
                if (
                    frames[i] is not None
                    and frames[i].attrs["data_provenance"][0]["revision"] == provenance["revision"]
                ):
                    continue
                frame, details = _extract(
                    ds,
                    names,
                    source,
                    sites,
                    variables,
                    date.fromisoformat(req["start"]),
                    date.fromisoformat(req["end"]),
                    workers,
                )
                info = {**provenance, **details, "window": [req["start"], req["end"]]}
                frame.attrs["data_provenance"] = [info]
                _write_cache(path, req, frame, info)
                frames[i] = frame
    infos = [f.attrs["data_provenance"][0] for f in frames]
    combined = pd.concat(frames, ignore_index=True)
    if not site_date_integrity_summary(combined, start, end, sites)["complete"]:
        raise BackendUnavailable("Provider/cache returned incomplete or duplicate site dates")
    combined.attrs["data_provenance"] = infos
    return combined


def quality_summary(frame, source):
    columns = list(CAPABILITIES[source].values())
    invalid = pd.DataFrame(False, index=frame.index, columns=columns)
    counts = {}
    for col in columns:
        if col not in frame:
            continue
        invalid[col] = ~np.isfinite(frame[col])
        if source == "chirts_era5":
            invalid[col] |= (frame[col] < -90) | (frame[col] > 60)
        else:
            invalid[col] |= frame[col] < 0
        counts[col] = int(invalid[col].sum())
    inverted = (
        (frame.Tmin > frame.Tmax)
        if {"Tmin", "Tmax"}.issubset(frame)
        else pd.Series(False, index=frame.index)
    )
    if inverted.any():
        invalid.loc[inverted, ["Tmax", "Tmin"]] = True
    return {
        "invalid_or_missing": counts,
        "tmin_gt_tmax": int(inverted.sum()),
        "flagged_rows": int(invalid.any(axis=1).sum()),
    }


def fetch_direct(
    source,
    *,
    location_coord=None,
    sites=None,
    sites_csv=None,
    variables=None,
    date_from=None,
    date_to=None,
    stage="raw",
    backend=None,
    allow_gee=None,
    cache_dir=None,
    refresh_cache=False,
    workers=1,
    gee_fetch=None,
    verbose=True,
):
    """Fetch a complete request; try each eligible equivalent provider once.

    Provider transport retries are bounded internally. Partial progress is cached
    per year, but a returned record always uses one provider and one revision.
    """
    if stage not in {"raw", "transformed", "preprocessed"}:
        raise ValueError(f"Unknown stage {stage!r}")
    policy = resolve_policy(backend, allow_gee)
    batch = bool(sites or sites_csv)
    if batch and location_coord is not None:
        raise ValueError("Use location_coord or sites, not both")
    if not batch and location_coord is None:
        raise ValueError("location_coord is required for a single-site fetch")
    points = load_sites(sites, sites_csv) if batch else [Site("point", *location_coord)]
    start, end = (
        pd.Timestamp(date_from or date.today()).date(),
        pd.Timestamp(date_to or date.today()).date(),
    )
    variables = _validate_request(
        source, points, variables or list(CAPABILITIES[source]), start, end
    )
    if not isinstance(workers, int) or not 1 <= workers <= 8:
        raise ValueError("Direct cloud workers must be an integer between 1 and 8")
    # CHIRPS ordering is selected from live benchmark evidence; HF remains an
    # independent direct backup. CHIRTS-ERA5 currently has only one cloud mirror.
    providers = (
        (["dynamical", "huggingface"] if source == "chirps_v3_daily_rnl" else ["huggingface"])
        if policy.backend == "auto"
        else [policy.backend]
    )
    if policy.backend == "auto" and policy.allow_gee and gee_fetch is not None:
        providers.append("gee")
    if source == "chirts_era5" and any(p != "huggingface" for p in providers):
        raise ValueError("chirts_era5 currently supports only huggingface (or auto)")
    failures = []
    frame = None
    cached = {}
    if not refresh_cache:
        for provider in providers:
            if provider == "gee":
                continue
            try:
                cached[provider] = _provider_fetch(
                    source,
                    provider,
                    points,
                    variables,
                    start,
                    end,
                    cache_dir,
                    False,
                    workers,
                    cache_only=True,
                )
                # Prefer an already complete cache, even if its provider was a
                # fallback on the previous run. No metadata/auth calls are needed.
                providers = [provider]
                break
            except BackendUnavailable:
                pass
    for provider in providers:
        try:
            if provider == "gee":
                if not policy.allow_gee or gee_fetch is None:
                    raise ValueError("GEE backend is unavailable or disabled")
                try:
                    frame = gee_fetch()
                except Exception as exc:
                    # Setup/auth errors use several exception classes in the
                    # legacy adapters. Preserve them in the attempt report.
                    raise BackendUnavailable(
                        f"GEE fetch failed: {type(exc).__name__}: {exc}"
                    ) from exc
                expected = pd.date_range(start, end)
                if batch:
                    complete = site_date_integrity_summary(frame, start, end, points)["complete"]
                else:
                    actual = pd.DatetimeIndex(pd.to_datetime(frame.get("date", [])))
                    complete = (
                        not actual.has_duplicates
                        and len(actual) == len(expected)
                        and expected.isin(actual).all()
                    )
                if not complete or not set(variables).issubset(frame.columns):
                    raise BackendUnavailable("GEE fallback returned incomplete dates or variables")
                if not np.isfinite(frame[variables].to_numpy(dtype=float)).all():
                    raise DataQualityError("GEE fallback returned missing/invalid values")
                qc = quality_summary(frame, source)
                if stage != "raw" and qc["flagged_rows"]:
                    raise DataQualityError("GEE fallback returned invalid precipitation")
                attempts = failures + [{"backend": "gee", "status": "success"}]
                frame.attrs["data_provenance"] = [
                    {
                        "source": source,
                        "backend": "gee",
                        "revision": None,
                        "collection": "UCSB-CHC/CHIRPS/V3/DAILY_RNL",
                        "window": [str(start), str(end)],
                        "revision_note": "Earth Engine collection revision is not exposed",
                        "backend_attempts": attempts,
                    }
                ]
                frame.attrs["backend_attempts"] = attempts
                frame.attrs["quality_control"] = qc
                return frame
            frame = cached.get(provider)
            if frame is None:
                frame = _provider_fetch(
                    source,
                    provider,
                    points,
                    variables,
                    start,
                    end,
                    cache_dir,
                    refresh_cache,
                    workers,
                )
        except (
            BackendUnavailable,
            requests.RequestException,
            OSError,
            TimeoutError,
            ImportError,
            KeyError,
            RuntimeError,
        ) as exc:
            failures.append(
                {"backend": provider, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
            )
            if verbose:
                warnings.warn(
                    f"{source} via {provider} unavailable: {exc}", RuntimeWarning, stacklevel=2
                )
            continue
        break
    else:
        raise BackendUnavailable(
            f"All eligible backends failed for {source}: "
            + "; ".join(f"{f['backend']}: {f['reason']}" for f in failures)
        )
    frame.attrs["backend_attempts"] = failures + [{"backend": provider, "status": "success"}]
    frame.attrs["data_provenance"] = [
        {**info, "backend_attempts": frame.attrs["backend_attempts"]}
        for info in frame.attrs["data_provenance"]
    ]
    qc = quality_summary(frame, source)
    frame.attrs["quality_control"] = qc
    # Raw remains available for diagnosis. Analysis never interpolates source
    # nodata, impossible temperatures or reversed daily extremes into results.
    if stage != "raw" and qc["flagged_rows"]:
        raise DataQualityError(
            f"{source}: {qc['flagged_rows']} rows contain missing/invalid values; inspect stage='raw'. QC: {qc}"
        )
    if stage != "raw":
        frame = frame.rename(
            columns={native: canonical for canonical, native in CAPABILITIES[source].items()}
        )
    if not batch:
        frame = frame.drop(columns=["site", "lat", "lon"])
    return frame


class DirectDownload:
    """SourceData adapter returning decoded native columns."""

    def __init__(self, source, **kwargs):
        self.source = source
        self.kwargs = kwargs

    def download_variables(self):
        return fetch_direct(self.source, **self.kwargs)
