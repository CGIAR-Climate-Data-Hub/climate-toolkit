"""Offline provider, failure, cache and scientific-contract regressions."""

from contextlib import contextmanager
from datetime import date
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from climate_toolkit.fetch_data import direct_cloud as cloud
from climate_toolkit.fetch_data.backend_policy import (
    backend_policy,
    resolve_policy,
    require_gee_allowed,
)
from climate_toolkit.fetch_data.fetch_data import fetch_data
from climate_toolkit.fetch_data.transform_data.transform_data import transform_data


@pytest.fixture
def fake_provider(monkeypatch):
    pytest.importorskip("zarr")
    calls = []
    state = {
        "revision": "v1",
        "fail": set(),
        "missing_date": False,
        "bad": False,
        "nan": False,
        "units": None,
    }

    @contextmanager
    def opened(source, backend, workers=1):
        calls.append((source, backend))
        if backend in state["fail"]:
            raise cloud.BackendUnavailable("simulated outage")
        times = pd.date_range("2019-12-30", "2021-01-03")
        if state["missing_date"]:
            times = times.delete(2)
        ds = xr.Dataset(
            coords={"time": times, "latitude": [-1.275, -1.225], "longitude": [36.825, 36.875]}
        )
        names = (
            {"precipitation": "precipitation_surface" if backend == "dynamical" else "precip"}
            if source.startswith("chirps")
            else cloud.CAPABILITIES[source]
        )
        for canonical, native in names.items():
            if native == state.get("missing_variable"):
                continue
            value = (
                12
                if canonical == "min_temperature"
                else 25
                if canonical == "max_temperature"
                else 8
            )
            if native == "precipitation_surface":
                value /= 86400
            values = np.full((len(times), 2, 2), value, dtype=float)
            if state["bad"]:
                values[:, 0, 0] = 99
            if state["nan"]:
                values[2, 0, 0] = np.nan
            units = (
                "kg m-2 s-1"
                if native == "precipitation_surface"
                else "mm"
                if native == "precip"
                else "degC"
            )
            ds[native] = xr.DataArray(
                values,
                dims=("time", "latitude", "longitude"),
                attrs={"units": state["units"] or units},
            )
        yield ds, names, {"revision": state["revision"], "source": source, "backend": backend}

    monkeypatch.setattr(cloud, "open_provider", opened)
    return calls, state


def run(tmp_path, **kwargs):
    options = dict(
        source="chirps_v3_daily_rnl",
        location_coord=(-1.286, 36.817),
        date_from=date(2020, 1, 1),
        date_to=date(2020, 1, 3),
        allow_gee=False,
        cache_dir=tmp_path,
        verbose=False,
    )
    options.update(kwargs)
    return fetch_data(**options)


def test_direct_failover_and_provider_identity(tmp_path, fake_provider):
    calls, state = fake_provider
    state["fail"] = {"dynamical"}
    frame = run(tmp_path)
    assert [b for _, b in calls] == ["dynamical", "huggingface"]
    assert frame.precipitation.tolist() == [8, 8, 8]
    assert frame.attrs["data_provenance"][0]["backend"] == "huggingface"
    assert frame.attrs["backend_attempts"][0]["reason"].endswith("simulated outage")


def test_explicit_backend_never_switches(tmp_path, fake_provider):
    calls, state = fake_provider
    state["fail"] = {"dynamical"}
    with pytest.raises(cloud.BackendUnavailable, match="All eligible"):
        run(tmp_path, backend="dynamical")
    assert len(calls) == 1


def test_warm_cache_offline_and_refresh(tmp_path, fake_provider, monkeypatch):
    original = run(tmp_path, backend="huggingface")
    spy = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(cloud, "open_provider", spy)
    cached = run(tmp_path, backend="huggingface")
    pd.testing.assert_frame_equal(original, cached)
    spy.assert_not_called()
    with pytest.raises(AssertionError, match="Network forbidden"):
        run(tmp_path, backend="huggingface", refresh_cache=True)


def test_corrupt_cache_is_refetched(tmp_path, fake_provider):
    run(tmp_path, backend="huggingface")
    path = next(tmp_path.rglob("*.json"))
    value = json.loads(path.read_text())
    value["payload"] += " "
    path.write_text(json.dumps(value))
    run(tmp_path, backend="huggingface")
    assert len(fake_provider[0]) == 2


def test_provider_cache_isolation(tmp_path, fake_provider):
    run(tmp_path, backend="huggingface")
    run(tmp_path, backend="dynamical")
    assert len(list(tmp_path.rglob("*.json"))) == 2


def test_missing_year_resumes_only_same_revision(tmp_path, fake_provider):
    run(tmp_path, backend="huggingface", date_from=date(2019, 12, 30), date_to=date(2020, 1, 3))
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 2
    files[0].unlink()
    fake_provider[1]["revision"] = "v2"
    frame = run(
        tmp_path, backend="huggingface", date_from=date(2019, 12, 30), date_to=date(2020, 1, 3)
    )
    assert {p["revision"] for p in frame.attrs["data_provenance"]} == {"v2"}


def test_multi_site_matches_single_and_preserves_labels(tmp_path, fake_provider):
    single = run(tmp_path)
    batch = run(
        tmp_path, location_coord=None, sites=[("Nairobi", -1.286, 36.817), ("nearby", -1.23, 36.85)]
    )
    assert len(batch) == 6
    assert batch.site.nunique() == 2
    pd.testing.assert_frame_equal(
        single, batch.loc[batch.site == "Nairobi", ["date", "precipitation"]].reset_index(drop=True)
    )


def test_batch_cache_preserves_float_coordinates_and_column_order(tmp_path, fake_provider):
    sites = [(str(i), -1.286 + i * 0.001, 36.817 + i * 0.001) for i in range(10)]
    original = run(tmp_path, location_coord=None, sites=sites)
    cached = run(tmp_path, location_coord=None, sites=sites)
    pd.testing.assert_frame_equal(original, cached, check_exact=True)
    assert original.equals(cached)


def test_direct_cache_inventory(tmp_path, fake_provider):
    from climate_toolkit.fetch_data.cache_inventory import cache_inventory

    run(tmp_path)
    rows = cache_inventory(cache_root=tmp_path, dataset="direct_cloud")
    assert len(rows) == 1
    assert rows.iloc[0]["complete"]
    assert "dynamical@v1" in rows.iloc[0]["selected_version"]


@pytest.mark.parametrize("stage", ["raw", "transformed", "preprocessed"])
def test_temperature_stages_and_units(tmp_path, fake_provider, stage):
    frame = run(tmp_path, source="chirts_era5", stage=stage)
    name = "Tmax" if stage == "raw" else "max_temperature"
    assert frame[name].tolist() == [25, 25, 25]


def test_chirts_packing_at_heat_thresholds(tmp_path, monkeypatch):
    pytest.importorskip("zarr")
    from climate_toolkit.calculate_hazards.hazards import calculate_season_statistics

    # Original daily maxima would count one day >= 35 and none >= 40.
    # At mirror precision 34.96 and 39.96 become exact threshold values.
    coords = {
        "time": pd.date_range("2020-01-01", periods=3),
        "latitude": [-1.275, -1.225],
        "longitude": [36.825, 36.875],
    }
    packed = xr.Dataset(coords=coords)
    for name, tenths in [("Tmax", [349, 350, 400]), ("Tmin", [180, 181, 182])]:
        packed[name] = xr.DataArray(
            np.broadcast_to(np.array(tenths, dtype="int16")[:, None, None], (3, 2, 2)),
            dims=("time", "latitude", "longitude"),
            attrs={"scale_factor": 0.1, "units": "degC"},
        )

    @contextmanager
    def opened(source, backend, workers=1):
        yield xr.decode_cf(packed), cloud.CAPABILITIES[source], {
            "revision": "packing-test", "source": source, "backend": backend,
        }

    monkeypatch.setattr(cloud, "open_provider", opened)
    frame = run(tmp_path, source="chirts_era5", stage="preprocessed")
    stats = calculate_season_statistics(frame)
    assert (stats["NTx35"], stats["NTx40"]) == (2, 1)
    assert stats["mean_tmax_c"] == pytest.approx((34.9 + 35.0 + 40.0) / 3)
    assert stats["mean_tmin_c"] == pytest.approx(18.1)


def test_impossible_temperatures_available_raw_but_rejected_analysis(tmp_path, fake_provider):
    calls, state = fake_provider
    state["bad"] = True
    raw = run(tmp_path, source="chirts_era5", stage="raw")
    assert raw.Tmax.iloc[0] == 99
    assert raw.attrs["quality_control"]["flagged_rows"] == 3
    with pytest.raises(cloud.DataQualityError, match="inspect stage='raw'"):
        run(tmp_path, source="chirts_era5")
    assert len(calls) == 1  # cached bad scientific values do not trigger another provider


def test_nodata_not_filled_with_zero(tmp_path, fake_provider):
    fake_provider[1]["nan"] = True
    with pytest.raises(cloud.DataQualityError):
        run(tmp_path)


def test_missing_dates_and_unknown_units_rejected(tmp_path, fake_provider):
    fake_provider[1]["missing_date"] = True
    with pytest.raises(cloud.BackendUnavailable, match="Incomplete provider coverage"):
        run(tmp_path)
    fake_provider[1]["missing_date"] = False
    fake_provider[1]["units"] = "unknown"
    with pytest.raises(cloud.BackendUnavailable, match="Unexpected units"):
        run(tmp_path)


def test_source_data_transform_uses_direct_and_keeps_provenance(tmp_path, fake_provider):
    with backend_policy(allow_gee=False):
        frame = transform_data(
            "chirts_era5",
            location_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 1, 3),
            cache_dir=tmp_path,
        )
    assert frame.max_temperature.iloc[0] == 25
    assert frame.attrs["data_provenance"][0]["source"] == "chirts_era5"


def test_policy_nesting_and_gee_prohibition(monkeypatch):
    monkeypatch.delenv("CLIMATE_TOOLKIT_BACKEND", raising=False)
    monkeypatch.delenv("CLIMATE_TOOLKIT_ALLOW_GEE", raising=False)
    assert resolve_policy().allow_gee
    with backend_policy(allow_gee=False):
        with pytest.raises(ValueError, match="disabled"):
            require_gee_allowed()
        with backend_policy(backend="huggingface"):
            assert resolve_policy().backend == "huggingface"
        assert resolve_policy().backend == "auto"
    assert resolve_policy().allow_gee


def test_gee_not_initialized_when_prohibited(monkeypatch):
    import ee

    initialize = Mock(side_effect=AssertionError("Must not initialize GEE"))
    monkeypatch.setattr(ee, "Initialize", initialize)
    with pytest.raises(ValueError, match="disabled"):
        fetch_data("era5_land", location_coord=(0, 0), allow_gee=False)
    initialize.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"variables": ["humidity"]},
        {"location_coord": (80, 0)},
        {"location_coord": (float("nan"), 0)},
        {"workers": 0},
        {"date_from": date(2021, 1, 1)},
        {"backend": "gee"},
    ],
)
def test_invalid_inputs_do_not_access_provider(tmp_path, monkeypatch, kwargs):
    spy = Mock(side_effect=AssertionError("No network for invalid request"))
    monkeypatch.setattr(cloud, "open_provider", spy)
    with pytest.raises(ValueError):
        run(tmp_path, **kwargs)
    spy.assert_not_called()


def test_tmin_gt_tmax_is_flagged():
    frame = pd.DataFrame({"Tmax": [20.0, 21.0], "Tmin": [22.0, 15.0]})
    qc = cloud.quality_summary(frame, "chirts_era5")
    assert qc["tmin_gt_tmax"] == qc["flagged_rows"] == 1


def test_gee_fallback_rejects_truncated_output(tmp_path, fake_provider):
    fake_provider[1]["fail"] = {"dynamical", "huggingface"}
    with pytest.raises(cloud.BackendUnavailable, match="GEE fallback returned incomplete"):
        cloud.fetch_direct(
            "chirps_v3_daily_rnl",
            location_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 1, 3),
            cache_dir=tmp_path,
            verbose=False,
            gee_fetch=lambda: pd.DataFrame(
                {"date": [pd.Timestamp("2020-01-01")], "precipitation": [1.0]}
            ),
        )


def test_auto_reuses_fallback_cache_without_trying_primary(tmp_path, fake_provider, monkeypatch):
    fake_provider[1]["fail"] = {"dynamical"}
    original = run(tmp_path)
    spy = Mock(side_effect=AssertionError("No network on complete fallback cache"))
    monkeypatch.setattr(cloud, "open_provider", spy)
    cached = run(tmp_path)
    pd.testing.assert_frame_equal(original, cached)
    spy.assert_not_called()


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
def test_metadata_retries_bounded(monkeypatch, failure):
    import requests

    ok = Mock(status_code=200)
    ok.json.return_value = {"sha": "v1"}
    failed = (
        requests.Timeout("timeout")
        if failure == "timeout"
        else Mock(status_code=failure, headers={"Retry-After": "100"})
    )
    get = Mock(side_effect=[failed, ok])
    sleep = Mock()
    monkeypatch.setattr(cloud.requests, "get", get)
    monkeypatch.setattr(cloud.time, "sleep", sleep)
    assert cloud._json_get("https://example.invalid") == {"sha": "v1"}
    assert get.call_count == 2
    assert sleep.call_args.args[0] <= 2


def test_metadata_exhausted_timeout_is_not_retried_forever(monkeypatch):
    import requests

    get = Mock(side_effect=requests.Timeout("unavailable"))
    monkeypatch.setattr(cloud.requests, "get", get)
    monkeypatch.setattr(cloud.time, "sleep", Mock())
    with pytest.raises(requests.Timeout):
        cloud._json_get("https://example.invalid")
    assert get.call_count == 2


def test_no_gee_auto_uses_new_pair_in_both_workflows(monkeypatch):
    from climate_toolkit.climate_statistics import statistics
    from climate_toolkit.season_analysis import seasons

    pair = Mock(return_value=pd.DataFrame())
    merge = Mock(return_value=pd.DataFrame())
    monkeypatch.setattr(statistics, "_fetch_paired_sources", pair)
    monkeypatch.setattr(seasons, "_merge_precip_temp", merge)
    with backend_policy(allow_gee=False):
        statistics._fetch_auto(-1.286, 36.817, date(2020, 1, 1), date(2020, 12, 31))
        seasons._fetch_raw(-1.286, 36.817, date(2020, 1, 1), date(2020, 12, 31), None)
    assert pair.call_args.args[4:6] == ("chirps_v3_daily_rnl", "chirts_era5")
    assert merge.call_args.args[3:5] == ("chirps_v3_daily_rnl", "chirts_era5")


def _worker_policy_probe(task):
    return resolve_policy().allow_gee, resolve_policy().backend, task


def test_spawn_worker_preserves_no_gee_policy():
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from climate_toolkit.fetch_data.backend_policy import BackendPolicy, run_with_backend_policy

    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        outcome = pool.submit(
            run_with_backend_policy, _worker_policy_probe, 42, BackendPolicy("auto", False)
        ).result(timeout=30)
    assert outcome == (False, "auto", 42)


def test_grid_tie_is_independent_of_latitude_order(tmp_path, fake_provider):
    with cloud.open_provider("chirts_era5", "huggingface") as (ds, names, _):
        ds["Tmax"][:, 0, :] = 20
        ds["Tmax"][:, 1, :] = 30
        site = cloud.Site("boundary", -1.25, 36.85)
        kwargs = dict(
            names=names,
            source="chirts_era5",
            sites=[site],
            variables=["max_temperature"],
            start=date(2020, 2, 29),
            end=date(2020, 2, 29),
            workers=1,
        )
        ascending, ainfo = cloud._extract(ds, **kwargs)
        descending, dinfo = cloud._extract(ds.sortby("latitude", ascending=False), **kwargs)
    assert ascending.Tmax.tolist() == [20]
    pd.testing.assert_frame_equal(ascending, descending)
    assert ainfo["selected_cells"] == dinfo["selected_cells"]


@pytest.mark.parametrize("lat", [-60, 70])
@pytest.mark.parametrize("lon", [-180, 180])
def test_chirts_domain_corner_selects_outermost_cell(fake_provider, lat, lon):
    with cloud.open_provider("chirts_era5", "huggingface") as (ds, names, _):
        # The nearest centre is half a grid cell inside each outer boundary.
        latitudes = [lat + d if lat < 0 else lat - d for d in (0.025, 0.075)]
        longitudes = [lon + d if lon < 0 else lon - d for d in (0.025, 0.075)]
        ds = ds.assign_coords(latitude=latitudes, longitude=longitudes)
        kwargs = dict(
            names=names,
            source="chirts_era5",
            sites=[cloud.Site("corner", lat, lon)],
            variables=["min_temperature", "max_temperature"],
            start=date(2020, 2, 29),
            end=date(2020, 2, 29),
            workers=1,
        )
        frame, info = cloud._extract(ds, **kwargs)
        assert len(frame) == 1
        cell = info["selected_cells"][0]
        assert cell["lat"] == pytest.approx(latitudes[0])
        assert cell["lon"] == pytest.approx(longitudes[0])


def test_chirts_rejects_missing_native_temperature(tmp_path, fake_provider):
    fake_provider[1]["missing_variable"] = "Tmin"
    with pytest.raises(cloud.BackendUnavailable, match="missing requested variables"):
        run(tmp_path, source="chirts_era5", backend="huggingface")


def test_unconfigured_gee_fallback_preserves_all_attempts(tmp_path, fake_provider):
    fake_provider[1]["fail"] = {"dynamical", "huggingface"}
    with pytest.raises(cloud.BackendUnavailable) as caught:
        cloud.fetch_direct(
            "chirps_v3_daily_rnl",
            location_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 1, 3),
            cache_dir=tmp_path,
            verbose=False,
            gee_fetch=Mock(side_effect=ValueError("Earth Engine project ID is required")),
        )
    message = str(caught.value)
    assert all(provider in message for provider in ["dynamical:", "huggingface:", "gee:"])
    assert "Earth Engine project ID is required" in message


def test_cross_year_load_reuses_source_chunks(tmp_path, monkeypatch):
    """A chunk spanning New Year must be decoded once, not once per cache year."""
    da = pytest.importorskip("dask.array")
    dask = pytest.importorskip("dask")
    pytest.importorskip("zarr")
    reads = []
    times = pd.date_range("2019-12-30", "2020-01-03")

    @dask.delayed
    def read_chunk():
        reads.append(True)
        return np.full((5, 2, 2), 8.0)

    @contextmanager
    def opened(source, backend, workers=1):
        array = da.from_delayed(read_chunk(), shape=(5, 2, 2), dtype=float)
        ds = xr.Dataset(
            {"precip": (("time", "latitude", "longitude"), array, {"units": "mm"})},
            coords={"time": times, "latitude": [-1.275, -1.225], "longitude": [36.825, 36.875]},
        )
        ds.precip.encoding["chunks"] = (5, 2, 2)
        yield (
            ds,
            {"precipitation": "precip"},
            {"revision": "v1", "source": source, "backend": backend},
        )

    monkeypatch.setattr(cloud, "open_provider", opened)
    kwargs = dict(backend="huggingface", date_from=date(2019, 12, 30), date_to=date(2020, 1, 3))
    cold = run(tmp_path, **kwargs)
    assert len(reads) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 2
    assert cold.precipitation.tolist() == [8.0] * 5
    warm = run(tmp_path, **kwargs)
    pd.testing.assert_frame_equal(cold, warm, check_exact=True)
    assert len(reads) == 1


def test_missing_year_groups_preserve_cached_year(tmp_path, fake_provider, monkeypatch):
    kwargs = dict(backend="huggingface", date_from=date(2019, 12, 30), date_to=date(2021, 1, 3))
    cold = run(tmp_path, **kwargs)
    cached_2020 = None
    for path in tmp_path.rglob("*.json"):
        data = json.loads(json.loads(path.read_text())["payload"])
        if data["request"]["start"] == "2020-01-01":
            cached_2020 = (path, path.read_bytes())
        else:
            path.unlink()
    original = cloud._extract
    windows = []

    def extract(*args):
        windows.append((args[5], args[6]))
        return original(*args)

    monkeypatch.setattr(cloud, "_extract", extract)
    resumed = run(tmp_path, **kwargs)
    assert windows == [
        (date(2019, 12, 30), date(2019, 12, 31)),
        (date(2021, 1, 1), date(2021, 1, 3)),
    ]
    assert cached_2020[0].read_bytes() == cached_2020[1]
    pd.testing.assert_frame_equal(cold, resumed, check_exact=True)


def test_bounded_loads_save_progress_before_later_outage(tmp_path, fake_provider, monkeypatch):
    monkeypatch.setattr(cloud, "MAX_LOAD_YEARS", 2)
    original = cloud._extract
    windows = []
    fail = [True]

    def extract(*args):
        windows.append((args[5], args[6]))
        if args[5].year == 2021 and fail[0]:
            raise cloud.BackendUnavailable("later batch outage")
        return original(*args)

    monkeypatch.setattr(cloud, "_extract", extract)
    kwargs = dict(backend="huggingface", date_from=date(2019, 12, 30), date_to=date(2021, 1, 3))
    with pytest.raises(cloud.BackendUnavailable, match="later batch outage"):
        run(tmp_path, **kwargs)
    assert windows == [
        (date(2019, 12, 30), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2021, 1, 3)),
    ]
    assert len(list(tmp_path.rglob("*.json"))) == 2
    fail[0] = False
    windows.clear()
    frame = run(tmp_path, **kwargs)
    assert windows == [(date(2021, 1, 1), date(2021, 1, 3))]
    assert len(frame) == 371
    assert len(list(tmp_path.rglob("*.json"))) == 3
