"""Exercise real workflow calculations and exports; only external data are fixtures."""

from contextlib import contextmanager
from datetime import date
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

import climate_toolkit as ct
from climate_toolkit.fetch_data import direct_cloud as cloud


@pytest.fixture
def providers(tmp_path, monkeypatch):
    pytest.importorskip("zarr")
    monkeypatch.chdir(tmp_path)
    calls = []
    state = {"fail_primary": False, "bad_temperature": False, "offline": False}
    dates = pd.date_range("2018-01-01", "2021-12-31")

    @contextmanager
    def opened(source, backend, workers=1):
        assert not state["offline"], "Warm pipeline attempted provider access"
        calls.append((source, backend, workers))
        if backend == "dynamical" and state["fail_primary"]:
            raise cloud.BackendUnavailable("fixture primary outage")
        ds = xr.Dataset(
            coords={"time": dates, "latitude": [-1.275, -1.225], "longitude": [36.825, 36.875]}
        )
        rain = np.where((dates.dayofyear.to_numpy() % 9) < 4, 12.3, 0.0)
        seasonal = np.sin(dates.dayofyear.to_numpy() * 2 * np.pi / 365)
        names = (
            {"precipitation": "precipitation_surface" if backend == "dynamical" else "precip"}
            if source.startswith("chirps")
            else cloud.CAPABILITIES[source]
        )
        for canonical, native in names.items():
            values = (
                rain
                if canonical == "precipitation"
                else (29.1 if canonical == "max_temperature" else 16.2) + seasonal
            )
            units = "degC"
            if canonical == "precipitation":
                units = "mm"
                if backend == "dynamical":
                    values = values / 86400
                    units = "kg m-2 s-1"
            if source == "chirts_era5" and state["bad_temperature"]:
                values = values.copy()
                values[dates == "2020-04-15"] = 99
            ds[native] = xr.DataArray(
                np.broadcast_to(values[:, None, None], (len(dates), 2, 2)).copy(),
                dims=("time", "latitude", "longitude"),
                attrs={"units": units},
            )
        yield ds, names, {"source": source, "backend": backend, "revision": "fixture-v1"}

    monkeypatch.setattr(cloud, "open_provider", opened)
    import ee

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected external network/authentication call")

    monkeypatch.setattr(ee, "Initialize", forbidden)
    monkeypatch.setattr(ee, "Authenticate", forbidden)
    monkeypatch.setattr(cloud.requests, "get", forbidden)
    # Elevation is an independent external data service, not a climate calculation.
    from climate_toolkit.weather_station import dem

    monkeypatch.setattr(dem, "fetch_anchor_elevation", lambda *a, **k: 1650.0)
    return calls, state


def options(tmp_path):
    return dict(
        name="Nairobi",
        location_coord=(-1.286, 36.817),
        source="paired",
        precip_source="chirps_v3_daily_rnl",
        temp_source="chirts_era5",
        start_year=2020,
        end_year=2020,
        climatology_baseline=(2019, 2020),
        fixed_season="03-01:05-31",
        crop_name="maize",
        run_compare_sources=True,
        compare_sources_list=["paired", "chirps_v3_daily_rnl", "chirts_era5"],
        run_compare_periods=True,
        baseline_start=2019,
        baseline_end=2019,
        focal_year=2020,
        output_dir=str(tmp_path / "reports"),
        allow_gee=False,
        workers=2,
        verbose=False,
    )


def source_ids(provenance):
    return {item["source"] for item in provenance}


def test_full_pipeline_calculations_exports_and_offline_repeat(tmp_path, providers):
    providers[1]["fail_primary"] = True
    result = ct.run_pipeline(**options(tmp_path))
    assert result.errors == []
    site = result.site_results[0]
    assert site.status == "completed"
    assert site.completed_steps == [
        "fetch",
        "climatology",
        "source_comparison",
        "statistics",
        "hazards",
        "period_comparison",
    ]
    expected = {"chirps_v3_daily_rnl", "chirts_era5"}
    assert source_ids(site.raw_fetch.attrs["data_provenance"]) == expected
    assert source_ids(site.long_term_climatology["data_provenance"]) == expected
    assert source_ids(site.climate_statistics["data_provenance"]) == expected
    assert source_ids(site.hazards["data_provenance"]) == expected
    assert source_ids(site.period_comparison["data_provenance"]["baseline"]) == expected
    assert source_ids(site.period_comparison["data_provenance"]["focal"]) == expected
    assert site.long_term_climatology["climatology"]["temperature"][
        "mean_annual_tmax_c"
    ] == pytest.approx(29.1, abs=0.01)
    assert site.long_term_climatology["period"]["years_with_data"] == 2
    assert site.climate_statistics["season_statistics"]
    bundle = site.climate_statistics["human_heat_bundle"]
    assert bundle["temperature_source"] == "chirts_era5"
    assert all(
        bundle[key] is None
        for key in ("humidity_source", "dewpoint_source", "wind_source", "solar_source")
    )
    assert site.hazards["hazard_evaluation"]
    assert all(workers == 2 for _, _, workers in providers[0])
    root = tmp_path / "reports" / "001_Nairobi"
    for filename in [
        "climate_statistics.json",
        "long_term_climatology.json",
        "hazards.json",
        "period_comparison.json",
        "source_comparison.json",
        "status.json",
        "daily.csv.metadata.json",
    ]:
        saved = json.loads(
            (root / filename).read_text(),
            parse_constant=lambda value: pytest.fail(f"Nonstandard JSON {value}"),
        )
        assert saved
    assert json.loads((root / "status.json").read_text())["status"] == "completed"
    assert len(pd.read_csv(root / "daily.csv")) == 366
    assert json.loads((tmp_path / "reports" / "metadata.json").read_text())["allow_gee"] is False
    providers[1]["offline"] = True
    warm = ct.run_pipeline(**options(tmp_path))
    assert warm.errors == []
    pd.testing.assert_frame_equal(site.raw_fetch, warm.site_results[0].raw_fetch)
    assert (
        warm.site_results[0].climate_statistics["overall_statistics"]
        == site.climate_statistics["overall_statistics"]
    )


def test_auto_pipeline_uses_direct_pair(tmp_path, providers):
    kw = options(tmp_path)
    kw.update(
        source="auto",
        precip_source=None,
        temp_source=None,
        run_compare_sources=False,
        run_compare_periods=False,
    )
    result = ct.run_pipeline(**kw)
    assert result.errors == []
    bundle = result.site_results[0].climate_statistics["human_heat_bundle"]
    assert bundle["temperature_source"] == "chirts_era5"
    assert bundle["humidity_source"] is None
    assert source_ids(result.site_results[0].raw_fetch.attrs["data_provenance"]) == {
        "chirps_v3_daily_rnl",
        "chirts_era5",
    }


def test_bad_temperature_fails_without_downstream_reports(tmp_path, providers):
    providers[1]["bad_temperature"] = True
    result = ct.run_pipeline(**options(tmp_path))
    site = result.site_results[0]
    assert site.status == "failed"
    assert "invalid" in site.error
    assert site.completed_steps == []
    assert site.hazards is None
    assert not (tmp_path / "reports" / "001_Nairobi" / "hazards.json").exists()


def test_climatology_does_not_silently_drop_qc_failed_year(tmp_path, providers):
    from climate_toolkit.climatology.long_term_climatology import calculate_climatology

    providers[1]["bad_temperature"] = True
    with ct.backend_policy(allow_gee=False), pytest.raises(cloud.DataQualityError):
        calculate_climatology((-1.286, 36.817), 2019, 2020, "chirts_era5", verbose=False)


def test_cli_fetch_exports_real_pipeline_columns_and_metadata(tmp_path, providers, monkeypatch):
    from climate_toolkit.cli import main
    import sys

    monkeypatch.setattr(sys, "argv", ["climate-toolkit"])
    output = tmp_path / "temperature.csv"
    code = main(
        [
            "fetch",
            "--no-gee",
            "--source",
            "chirts_era5",
            "--lat",
            "-1.286",
            "--lon",
            "36.817",
            "--start",
            "2020-02-28",
            "--end",
            "2020-03-01",
            "--output",
            str(output),
            "--format",
            "csv",
        ]
    )
    assert code == 0
    frame = pd.read_csv(output)
    assert list(frame.columns) == ["date", "max_temperature", "min_temperature"]
    assert frame.date.tolist() == ["2020-02-28", "2020-02-29", "2020-03-01"]
    assert source_ids(
        json.loads(Path(str(output) + ".metadata.json").read_text())["data_provenance"]
    ) == {"chirts_era5"}


def test_climatology_requires_every_direct_source_year(tmp_path, providers):
    from climate_toolkit.climatology.long_term_climatology import calculate_climatology

    with ct.backend_policy(allow_gee=False):
        result = calculate_climatology((-1.286, 36.817), 2017, 2021, "chirts_era5", verbose=False)
    assert "error" in result
    assert "4/5" in result["error"]


def test_station_comparison_with_custom_observations(tmp_path, providers):
    with ct.backend_policy(allow_gee=False):
        temperature = ct.fetch_climate_data(
            "chirts_era5",
            location_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 12, 31),
            verbose=False,
        )
        path = tmp_path / "station.csv"
        temperature.to_csv(path, index=False)
        result = ct.compare_station_to_grids(
            station_source="custom_csv",
            station_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 12, 31),
            grid_sources=["chirts_era5"],
            variables=["max_temperature", "min_temperature"],
            custom_station_file=str(path),
            custom_station_name="fixture station",
            auto_anchor_elevation=False,
            verbose=False,
        )
    assert result["grid_failures"] == []
    assert result["metrics"]
    # Custom station ingestion rounds to 0.01 C; grid precision stays intact.
    assert all(row["rmse"] <= 0.005 for row in result["metrics"])
    assert all(row["data_provenance"] for row in result["grid_fetch_summary"])


@pytest.mark.parametrize("source,expected", [("paired", 0), ("chirts_era5", 1)])
def test_climatology_cli_pair_and_failure_status(
    tmp_path, providers, monkeypatch, source, expected
):
    from climate_toolkit.cli import main
    import sys

    monkeypatch.setattr(sys, "argv", ["climate-toolkit"])
    args = [
        "climatology",
        "--no-gee",
        "--location=-1.286,36.817",
        "--source",
        source,
        "--start-year",
        "2020" if source == "paired" else "2017",
        "--end-year",
        "2020",
        "--output-dir",
        "",
        "--format",
        "json",
        "--output",
        str(tmp_path / "climatology.json"),
    ]
    if source == "paired":
        args.extend(["--precip-source", "chirps_v3_daily_rnl", "--temp-source", "chirts_era5"])
    assert main(args) == expected
    result = json.loads((tmp_path / "climatology.json").read_text())
    if expected:
        assert result["error"]
    else:
        assert source_ids(result["data_provenance"]) == {"chirps_v3_daily_rnl", "chirts_era5"}


def test_failed_rerun_removes_stale_pipeline_reports(tmp_path, providers):
    kw = options(tmp_path)
    kw.update(run_compare_sources=False, run_compare_periods=False, run_climatology=False)
    assert not ct.run_pipeline(**kw).errors
    root = tmp_path / "reports" / "001_Nairobi"
    assert (root / "hazards.json").exists()
    # A new unsupported location reuses the requested output location/name.
    kw["location_coord"] = (80, 36.817)
    result = ct.run_pipeline(**kw)
    assert result.site_results[0].status == "failed"
    assert not (root / "hazards.json").exists()
    assert not (root / "daily.csv").exists()
    assert json.loads((root / "status.json").read_text())["status"] == "failed"


def test_source_comparison_does_not_hide_bad_temperature(tmp_path, providers):
    providers[1]["bad_temperature"] = True
    with ct.backend_policy(allow_gee=False), pytest.raises(cloud.DataQualityError):
        ct.compare_climate_sources(
            ["chirps_v3_daily_rnl", "chirts_era5"],
            lat=-1.286,
            lon=36.817,
            start="2020-01-01",
            end="2020-12-31",
            output_dir=str(tmp_path / "compare"),
        )


def test_export_reopen_preserves_provenance_and_replacement_clears_it(tmp_path, providers):
    from climate_toolkit.fetch_data.fetch_data import save_output
    from climate_toolkit.fetch_data.backend_policy import save_frame_metadata

    frame = ct.fetch_climate_data(
        "chirts_era5",
        location_coord=(-1.286, 36.817),
        date_from=date(2020, 1, 1),
        date_to=date(2020, 1, 3),
        allow_gee=False,
    )
    source = tmp_path / "daily.csv"
    save_output(frame, source, "csv")
    restored = ct.compare_climate_sources(
        [], input_file=str(source), output_dir=str(tmp_path / "reopened")
    )["input_file"]
    pd.testing.assert_frame_equal(frame, restored, check_exact=True)
    assert restored.attrs == frame.attrs
    metadata_path = Path(str(source) + ".metadata.json")
    frame.attrs.clear()
    save_frame_metadata(frame, source)
    assert not metadata_path.exists()


def test_batch_pipeline_isolates_invalid_site_and_reports(tmp_path, providers):
    kw = options(tmp_path)
    kw.update(
        sites=[
            {"name": "same", "lat": -1.286, "lon": 36.817},
            {"name": "same", "lat": 80, "lon": 36.817},
        ],
        run_climatology=False,
        run_compare_sources=False,
        run_compare_periods=False,
    )
    result = ct.run_pipeline(**kw)
    assert [s.status for s in result.site_results] == ["completed", "failed"]
    assert result.metadata["n_failed"] == 1
    assert (tmp_path / "reports" / "001_same" / "hazards.json").exists()
    assert not (tmp_path / "reports" / "002_same" / "hazards.json").exists()
