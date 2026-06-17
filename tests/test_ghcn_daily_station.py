from datetime import date
import importlib
from io import StringIO
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd


def _install_test_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    ee = types.ModuleType("ee")
    ee.Authenticate = lambda *args, **kwargs: None
    ee.Initialize = lambda *args, **kwargs: None
    sys.modules.setdefault("ee", ee)

    cdsapi = types.ModuleType("cdsapi")
    cdsapi_api = types.ModuleType("cdsapi.api")

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

    cdsapi_api.Client = _Client
    cdsapi.api = cdsapi_api
    sys.modules.setdefault("cdsapi", cdsapi)
    sys.modules.setdefault("cdsapi.api", cdsapi_api)


_install_test_stubs()

import climate_tookit.weather_station.ghcn_daily as ghcn
import climate_tookit.weather_station.gsod as gsod
import climate_tookit.weather_station.dem as dem
import climate_tookit.weather_station.compare as station_compare
import climate_tookit.weather_station.download as station_download
import climate_tookit.weather_station.station_selector as station_selector
from climate_tookit.fetch_data.preprocess_data.preprocess_data import (
    apply_unit_conversions,
    preprocess_transformed_data,
)
from climate_tookit.climatology.xclim_reference import (
    XCLIM_AVAILABLE,
    assess_xclim_precip_annual_readiness,
    compare_xclim_precip_indices,
    compute_xclim_precip_indices,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable

fetch_data_module = importlib.import_module("climate_tookit.fetch_data.fetch_data")


def _build_dly_line(station_id: str, year: int, month: int, element: str, values: list[int]) -> str:
    padded = list(values) + [-9999] * (31 - len(values))
    day_chunks = [f"{value:>5}   " for value in padded[:31]]
    return f"{station_id}{year:04d}{month:02d}{element}{''.join(day_chunks)}"


class GHCNDailyStationTests(unittest.TestCase):
    def test_parse_auto_select_scope_supports_numeric_and_all(self):
        self.assertEqual(1, station_download.parse_auto_select_scope("auto-1"))
        self.assertEqual(3, station_download.parse_auto_select_scope("auto-3"))
        self.assertEqual(10, station_download.parse_auto_select_scope("auto-all"))
        self.assertEqual(4, station_download.parse_auto_select_scope("auto-all", max_auto_stations=4))

    def test_parse_auto_select_scope_clamps_above_cap(self):
        self.assertEqual(10, station_download.parse_auto_select_scope("auto-11", max_auto_stations=10))

    def test_gsod_normalizes_5_digit_station_id(self):
        self.assertEqual("63742099999", gsod._normalize_station_id("63742"))

    def test_gsod_candidate_evaluation_reuses_cached_coverage_summary(self):
        candidate = {
            "station_id": "63741099999",
            "station_name": "Test GSOD",
            "lat": -1.286,
            "lon": 36.817,
            "distance_km": 5.0,
        }
        gsod_csv = "\n".join(
            [
                "STATION,DATE,PRCP",
                "63741099999,2020-01-01,1.0",
                "63741099999,2020-01-02,2.0",
            ]
        )
        calls = []
        orig_download_text = gsod._download_text

        def fake_download_text(**kwargs):
            calls.append((kwargs["station_id"], kwargs["year"]))
            return gsod_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            gsod._download_text = fake_download_text
            try:
                first = gsod.evaluate_gsod_station_candidate(
                    candidate=candidate,
                    date_from=date(2020, 1, 1),
                    date_to=date(2020, 1, 2),
                    variables=[ClimateVariable.precipitation],
                    cache_dir=tmpdir,
                    refresh_cache=False,
                    verbose=False,
                )
                self.assertFalse(first["coverage_cache_hit"])
                self.assertEqual(1.0, first["min_completeness_ratio"])
                self.assertEqual([("63741099999", 2020)], calls)

                def fail_download_text(**kwargs):
                    raise AssertionError("coverage cache should avoid re-downloading GSOD data")

                gsod._download_text = fail_download_text
                second = gsod.evaluate_gsod_station_candidate(
                    candidate=candidate,
                    date_from=date(2020, 1, 1),
                    date_to=date(2020, 1, 2),
                    variables=[ClimateVariable.precipitation],
                    cache_dir=tmpdir,
                    refresh_cache=False,
                    verbose=False,
                )
            finally:
                gsod._download_text = orig_download_text

        self.assertTrue(second["coverage_cache_hit"])
        self.assertEqual(1.0, second["mean_completeness_ratio"])

    def test_download_station_data_rejects_gsod_auto_mode(self):
        with self.assertRaisesRegex(ValueError, "selection_mode='specified' only"):
            station_download.download_station_data(
                station_source="gsod",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
            )

    def test_download_station_data_routes_gsod_specified_to_fetch_pipeline(self):
        calls = []

        def _fake_fetch_data(**kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01"]),
                    "precipitation": [12.7],
                    "station_id": ["63742099999"],
                }
            )

        orig_fetch_data = station_download.fetch_data
        station_download.fetch_data = _fake_fetch_data
        try:
            result = station_download.download_station_data(
                station_source="gsod",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="specified",
                station_id="63742099999",
                stage="preprocessed",
                verbose=False,
            )
        finally:
            station_download.fetch_data = orig_fetch_data

        self.assertEqual(1, len(calls))
        self.assertEqual("gsod", calls[0]["source"])
        self.assertEqual("63742099999", calls[0]["station_id"])
        self.assertEqual(1, len(result))

    def test_download_text_uses_cache_on_second_call(self):
        calls = []

        class _Response:
            text = "abc123"

            def raise_for_status(self):
                return None

        orig_get = ghcn.requests.get
        ghcn.requests.get = lambda *args, **kwargs: calls.append((args, kwargs)) or _Response()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                cache_path = Path(tmpdir) / "sample.txt"
                first = ghcn._download_text(
                    url="https://example.com/sample.txt",
                    cache_path=cache_path,
                    refresh_cache=False,
                )
                second = ghcn._download_text(
                    url="https://example.com/sample.txt",
                    cache_path=cache_path,
                    refresh_cache=False,
                )
        finally:
            ghcn.requests.get = orig_get

        self.assertEqual("abc123", first)
        self.assertEqual("abc123", second)
        self.assertEqual(1, len(calls))

    def test_select_station_allows_tavg_for_mean_temperature(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Near TAVG",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                },
                {
                    "station_id": "BBB00000002",
                    "lat": -1.500,
                    "lon": 36.500,
                    "elevation_m": 1600.0,
                    "station_name": "Far TMAX TMIN",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                },
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TAVG", "start_year": 1990, "end_year": 2025},
                {"station_id": "BBB00000002", "lat": -1.500, "lon": 36.500, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "BBB00000002", "lat": -1.500, "lon": 36.500, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )

        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = lambda **kwargs: _build_dly_line("AAA00000001", 2020, 1, "TAVG", [250, 260])
        try:
            result = ghcn.select_ghcn_station(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.mean_temperature],
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        self.assertEqual("AAA00000001", result["station_id"])
        self.assertIn("TAVG", result["available_elements"])

    def test_list_candidates_can_return_below_threshold_rows_when_not_enforced(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Near partial",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                }
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )
        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = lambda **kwargs: "\n".join(
            [
                _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10]),
                _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300]),
            ]
        )
        try:
            result = ghcn.list_ghcn_station_candidates(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                min_completeness_ratio=0.7,
                enforce_threshold=False,
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        self.assertEqual(1, len(result))
        self.assertFalse(bool(result.iloc[0]["all_fields_meet_threshold"]))
        self.assertEqual("below_threshold", result.iloc[0]["threshold_status"])

    def test_select_station_candidates_relaxes_thresholds_before_failing(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Near partial",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                }
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )
        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = lambda **kwargs: "\n".join(
            [
                _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10, 5]),
                _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300, 301]),
                _build_dly_line("AAA00000001", 2020, 1, "TMIN", [200]),
            ]
        )
        try:
            result = ghcn.select_ghcn_station_candidates(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                min_completeness_ratio=0.7,
                candidate_limit=1,
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        self.assertEqual(1, len(result))
        self.assertEqual("relaxed", result.iloc[0]["selection_status"])
        self.assertAlmostEqual(0.5, float(result.iloc[0]["selection_threshold_used"]), places=6)

    def test_compute_variable_metrics_for_precipitation(self):
        merged = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=4, freq="D"),
                "precipitation_station": [0.0, 5.0, 0.0, 10.0],
                "precipitation_grid": [0.0, 4.0, 1.0, 9.0],
            }
        )

        metrics = station_compare._compute_variable_metrics(
            merged,
            variable="precipitation",
            wet_day_threshold_mm=1.0,
        )

        self.assertIsNotNone(metrics)
        self.assertEqual(4, metrics["overlap_days"])
        self.assertEqual(15.0, metrics["station_total_mm"])
        self.assertEqual(14.0, metrics["grid_total_mm"])
        self.assertEqual(-1.0, metrics["delta_total_mm"])
        self.assertEqual(2, metrics["station_wet_days"])
        self.assertEqual(3, metrics["grid_wet_days"])
        self.assertEqual(2, metrics["wet_day_hits"])
        self.assertEqual(0, metrics["wet_day_misses"])
        self.assertEqual(1, metrics["wet_day_false_alarms"])
        self.assertEqual(1.0, metrics["wet_day_hit_rate"])
        self.assertEqual(0.6667, metrics["precision"])
        self.assertEqual(0.3333, metrics["false_alarm_ratio"])
        self.assertEqual(0.6667, metrics["critical_success_index"])
        self.assertEqual(1.5, metrics["frequency_bias"])
        self.assertEqual(0.75, metrics["wet_day_agreement"])
        self.assertEqual("very_low", metrics["confidence_class"])
        self.assertTrue(metrics["low_confidence"])

    def test_compute_variable_metrics_for_precipitation_extremes(self):
        merged = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=6, freq="D"),
                "precipitation_station": [0.0, 5.0, 0.0, 10.0, 20.0, 1.0],
                "precipitation_grid": [0.0, 4.0, 1.0, 12.0, 25.0, 2.0],
            }
        )

        metrics = station_compare._compute_variable_metrics(
            merged,
            variable="precipitation",
            wet_day_threshold_mm=1.0,
        )

        self.assertIsNotNone(metrics)
        self.assertEqual(9.0, metrics["wet_day_intensity_station"])
        self.assertEqual(8.8, metrics["wet_day_intensity_grid"])
        self.assertEqual(-0.2, metrics["wet_day_intensity_delta"])
        self.assertEqual(20.0, metrics["rx1day_mm_station"])
        self.assertEqual(25.0, metrics["rx1day_mm_grid"])
        self.assertEqual(5.0, metrics["rx1day_mm_delta"])
        self.assertEqual(36.0, metrics["rx5day_mm_station"])
        self.assertEqual(44.0, metrics["rx5day_mm_grid"])
        self.assertEqual(8.0, metrics["rx5day_mm_delta"])
        self.assertEqual(2, metrics["r10mm_days_station"])
        self.assertEqual(2, metrics["r10mm_days_grid"])
        self.assertEqual(0, metrics["r10mm_days_delta"])
        self.assertEqual(1, metrics["r20mm_days_station"])
        self.assertEqual(1, metrics["r20mm_days_grid"])
        self.assertEqual(0, metrics["r20mm_days_delta"])
        self.assertIn("p90_mm_station", metrics)
        self.assertIn("p95_mm_grid", metrics)

    def test_compare_station_to_grids_uses_station_coordinates_and_builds_metrics(self):
        station_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "station_id": ["STAT001"] * 3,
                "station_name": ["Demo Station"] * 3,
                "station_source": ["ghcn_daily"] * 3,
                "station_lat": [-1.30] * 3,
                "station_lon": [36.75] * 3,
                "station_distance_km": [7.61] * 3,
                "station_elevation_m": [1798.0] * 3,
                "precipitation": [0.0, 5.0, 10.0],
                "max_temperature": [25.0, 26.0, 27.0],
                "min_temperature": [15.0, 16.0, 17.0],
            }
        )
        grid_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "precipitation": [0.0, 4.0, 12.0],
                "max_temperature": [24.0, 27.0, 28.0],
                "min_temperature": [14.0, 15.0, 18.0],
            }
        )
        fetch_calls = []

        orig_download_station_data = station_compare.download_station_data
        orig_fetch_grid_source = station_compare._fetch_grid_source
        station_compare.download_station_data = lambda **kwargs: station_frame.copy()

        def _fake_fetch_grid_source(**kwargs):
            fetch_calls.append(
                (
                    kwargs["source"],
                    kwargs["lat"],
                    kwargs["lon"],
                    kwargs.get("cache_dir"),
                    kwargs.get("refresh_cache"),
                )
            )
            return grid_frame.copy()

        station_compare._fetch_grid_source = _fake_fetch_grid_source
        try:
            result = station_compare.compare_station_to_grids(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 3),
                grid_sources=["agera_5", "chirps_v2"],
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                cache_dir="outputs/cache/test_station_compare",
                refresh_cache=True,
                verbose=False,
            )
        finally:
            station_compare.download_station_data = orig_download_station_data
            station_compare._fetch_grid_source = orig_fetch_grid_source

        self.assertEqual(
            [
                ("agera_5", -1.3, 36.75, "outputs/cache/test_station_compare", True),
                ("chirps_v2", -1.3, 36.75, "outputs/cache/test_station_compare", True),
            ],
            fetch_calls,
        )
        self.assertEqual(1, len(result["station_summary"]))
        self.assertEqual(6, len(result["metrics"]))
        precip_rows = [
            row for row in result["metrics"]
            if row["grid_source"] == "agera_5" and row["variable"] == "precipitation"
        ]
        self.assertEqual(1, len(precip_rows))
        self.assertEqual(15.0, precip_rows[0]["station_total_mm"])
        self.assertEqual(16.0, precip_rows[0]["grid_total_mm"])
        self.assertEqual(1.0, precip_rows[0]["delta_total_mm"])
        metadata_by_source = {
            row["grid_source"]: row["product_class"]
            for row in result["grid_source_metadata"]
        }
        self.assertEqual("reanalysis", metadata_by_source["agera_5"])
        self.assertEqual("gauge_satellite_precipitation", metadata_by_source["chirps_v2"])
        ranking_use_cases = {
            row["use_case"]
            for row in result["use_case_rankings"]
        }
        self.assertIn("daily_monitoring", ranking_use_cases)
        self.assertIn("seasonal_totals", ranking_use_cases)
        self.assertIn("drought_screening", ranking_use_cases)
        self.assertIn("temperature_climatology", ranking_use_cases)
        overall_precip = [
            row for row in result["overall_metrics"]
            if row["grid_source"] == "chirps_v2" and row["variable"] == "precipitation"
        ]
        self.assertEqual(1, len(overall_precip))

    def test_compare_station_to_grids_best_per_variable_selects_different_stations(self):
        precip_candidate = pd.DataFrame(
            {
                "station_id": ["RAIN001"],
                "station_name": ["Rain Station"],
                "distance_km": [5.0],
                "elevation_diff_m": [20.0],
                "selection_status": ["guard_disabled"],
                "selection_threshold_used": [pd.NA],
                "threshold_status": ["guard_disabled"],
            }
        )
        tmin_candidate = pd.DataFrame(
            {
                "station_id": ["TMIN001"],
                "station_name": ["Tmin Station"],
                "distance_km": [8.0],
                "elevation_diff_m": [35.0],
                "selection_status": ["guard_disabled"],
                "selection_threshold_used": [pd.NA],
                "threshold_status": ["guard_disabled"],
            }
        )
        station_frames = {
            ("RAIN001", "precipitation"): pd.DataFrame(
                {
                    "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                    "station_id": ["RAIN001", "RAIN001"],
                    "station_name": ["Rain Station", "Rain Station"],
                    "station_source": ["ghcn_daily", "ghcn_daily"],
                    "station_lat": [-1.20, -1.20],
                    "station_lon": [36.70, 36.70],
                    "station_distance_km": [5.0, 5.0],
                    "station_elevation_m": [1700.0, 1700.0],
                    "precipitation": [1.0, 2.0],
                }
            ),
            ("TMIN001", "min_temperature"): pd.DataFrame(
                {
                    "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                    "station_id": ["TMIN001", "TMIN001"],
                    "station_name": ["Tmin Station", "Tmin Station"],
                    "station_source": ["ghcn_daily", "ghcn_daily"],
                    "station_lat": [-1.40, -1.40],
                    "station_lon": [36.90, 36.90],
                    "station_distance_km": [8.0, 8.0],
                    "station_elevation_m": [1680.0, 1680.0],
                    "min_temperature": [12.0, 13.0],
                }
            ),
        }
        grid_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                "precipitation": [1.5, 1.0],
                "min_temperature": [11.0, 14.0],
            }
        )

        orig_list = station_compare.list_ghcn_station_candidates
        orig_download = station_compare.download_station_data
        orig_fetch_grid = station_compare._fetch_grid_source

        def _fake_list(**kwargs):
            variable = kwargs["variables"][0]
            if variable == ClimateVariable.precipitation:
                return precip_candidate.copy()
            if variable == ClimateVariable.min_temperature:
                return tmin_candidate.copy()
            raise AssertionError(variable)

        def _fake_download(**kwargs):
            variable = kwargs["variables"][0].name
            return station_frames[(kwargs["station_id"], variable)].copy()

        station_compare.list_ghcn_station_candidates = _fake_list
        station_compare.download_station_data = _fake_download
        station_compare._fetch_grid_source = lambda **kwargs: grid_frame.copy()
        try:
            result = station_compare.compare_station_to_grids(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                grid_sources=["nasa_power"],
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.min_temperature,
                ],
                selection_strategy="best_per_variable",
                disable_completeness_guard=True,
                verbose=False,
            )
        finally:
            station_compare.list_ghcn_station_candidates = orig_list
            station_compare.download_station_data = orig_download
            station_compare._fetch_grid_source = orig_fetch_grid

        self.assertEqual("best_per_variable", result["selection_strategy"])
        self.assertEqual(2, len(result["selected_stations_by_variable"]))
        self.assertEqual("RAIN001", result["selected_stations_by_variable"][0]["station_id"])
        self.assertEqual("TMIN001", result["selected_stations_by_variable"][1]["station_id"])
        self.assertEqual(2, len(result["station_summary"]))
        metric_variables = sorted(row["variable"] for row in result["metrics"])
        self.assertEqual(["min_temperature", "precipitation"], metric_variables)

    def test_compare_station_to_grids_auto_multi_station_splits_payloads(self):
        station_frame = pd.DataFrame(
            {
                "date": list(pd.date_range("2020-01-01", periods=2, freq="D"))
                + list(pd.date_range("2020-01-01", periods=2, freq="D")),
                "station_id": ["STAT001", "STAT001", "STAT002", "STAT002"],
                "station_name": ["Station One", "Station One", "Station Two", "Station Two"],
                "station_source": ["ghcn_daily"] * 4,
                "station_lat": [-1.30, -1.30, -1.31, -1.31],
                "station_lon": [36.75, 36.75, 36.76, 36.76],
                "station_distance_km": [7.61, 7.61, 9.12, 9.12],
                "station_elevation_m": [1798.0, 1798.0, 1702.0, 1702.0],
                "selection_rank": [1, 1, 2, 2],
                "selection_mode": ["auto-2"] * 4,
                "selection_status": ["guard_disabled"] * 4,
                "selection_threshold_used": [pd.NA] * 4,
                "threshold_status": ["guard_disabled"] * 4,
                "distance_km": [7.61, 7.61, 9.12, 9.12],
                "elevation_diff_m": [131.0, 131.0, 35.0, 35.0],
                "precipitation": [0.0, 5.0, 1.0, 6.0],
            }
        )
        fetch_calls = []

        def _fake_fetch_grid_source(**kwargs):
            fetch_calls.append((kwargs["lat"], kwargs["lon"]))
            return pd.DataFrame(
                {
                    "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                    "precipitation": [0.0, 4.0] if kwargs["lat"] == -1.30 else [1.0, 5.0],
                }
            )

        orig_download_station_data = station_compare.download_station_data
        orig_fetch_grid_source = station_compare._fetch_grid_source
        station_compare.download_station_data = lambda **kwargs: station_frame.copy()
        station_compare._fetch_grid_source = _fake_fetch_grid_source
        try:
            result = station_compare.compare_station_to_grids(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                grid_sources=["nasa_power"],
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                selection_strategy="all_vars_single_station",
                auto_select="auto-2",
                disable_completeness_guard=True,
                verbose=False,
            )
        finally:
            station_compare.download_station_data = orig_download_station_data
            station_compare._fetch_grid_source = orig_fetch_grid_source

        self.assertEqual(2, len(result["station_summary"]))
        self.assertEqual(2, len(result["metrics"]))
        self.assertEqual(
            [
                ("all_variables", "STAT001", 1),
                ("all_variables", "STAT002", 2),
            ],
            [
                (row["variable"], row["station_id"], row["selection_rank"])
                for row in result["selected_stations_by_variable"]
            ],
        )
        self.assertEqual([(-1.3, 36.75), (-1.31, 36.76)], fetch_calls)
        pooled_daily = [
            row for row in result["pooled_daily_metrics"]
            if row["grid_source"] == "nasa_power" and row["variable"] == "precipitation"
        ]
        self.assertEqual(1, len(pooled_daily))
        self.assertEqual(2, pooled_daily[0]["overlap_days"])
        self.assertEqual(2.0, pooled_daily[0]["stations_contributing_mean"])
        self.assertEqual(2, pooled_daily[0]["stations_contributing_min"])
        self.assertEqual(2, pooled_daily[0]["stations_contributing_max"])
        self.assertEqual(6.0, pooled_daily[0]["station_total_mm"])
        self.assertEqual(5.0, pooled_daily[0]["grid_total_mm"])
        stacked_daily = [
            row for row in result["overall_metrics"]
            if row["grid_source"] == "nasa_power" and row["variable"] == "precipitation"
        ]
        self.assertEqual(1, len(stacked_daily))
        self.assertEqual(4, stacked_daily[0]["overlap_days"])

    def test_overlap_warning_added_for_low_sample_metrics(self):
        station_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=11, freq="D"),
                "station_id": ["STAT001"] * 11,
                "station_name": ["Demo Station"] * 11,
                "station_source": ["ghcn_daily"] * 11,
                "station_lat": [-1.30] * 11,
                "station_lon": [36.75] * 11,
                "station_distance_km": [7.61] * 11,
                "station_elevation_m": [1798.0] * 11,
                "max_temperature": list(range(20, 31)),
            }
        )
        grid_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=11, freq="D"),
                "max_temperature": list(range(21, 32)),
            }
        )

        orig_download_station_data = station_compare.download_station_data
        orig_fetch_grid_source = station_compare._fetch_grid_source
        station_compare.download_station_data = lambda **kwargs: station_frame.copy()
        station_compare._fetch_grid_source = lambda **kwargs: grid_frame.copy()
        try:
            result = station_compare.compare_station_to_grids(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 11),
                grid_sources=["nasa_power"],
                variables=[ClimateVariable.max_temperature],
                min_overlap_days=30,
                verbose=False,
            )
        finally:
            station_compare.download_station_data = orig_download_station_data
            station_compare._fetch_grid_source = orig_fetch_grid_source

        self.assertEqual("very_low", result["metrics"][0]["confidence_class"])
        self.assertTrue(result["metrics"][0]["low_confidence"])
        self.assertTrue(any("Low overlap" in warning for warning in result["warnings"]))

    def test_compute_aggregated_metrics_monthly_precipitation(self):
        overlap = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2020-01-01",
                        "2020-01-02",
                        "2020-02-01",
                        "2020-02-02",
                    ]
                ),
                "precipitation_station": [1.0, 2.0, 3.0, 4.0],
                "precipitation_grid": [2.0, 2.0, 5.0, 5.0],
            }
        )

        metrics = station_compare._compute_aggregated_metrics(
            overlap,
            variable="precipitation",
            frequency="M",
        )

        self.assertIsNotNone(metrics)
        self.assertEqual("monthly", metrics["timescale"])
        self.assertEqual(2, metrics["period_count"])
        self.assertEqual(5.0, metrics["station_mean"])
        self.assertEqual(7.0, metrics["grid_mean"])
        self.assertEqual(2.0, metrics["bias"])
        self.assertEqual(2.0, metrics["mae"])
        self.assertEqual(2.2361, metrics["rmse"])
        self.assertEqual(10.0, metrics["station_total_mm"])
        self.assertEqual(14.0, metrics["grid_total_mm"])
        self.assertEqual(4.0, metrics["delta_total_mm"])

    def test_compute_aggregated_metrics_annual_temperature(self):
        overlap = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2020-01-01",
                        "2020-02-01",
                        "2021-01-01",
                        "2021-02-01",
                    ]
                ),
                "min_temperature_station": [10.0, 12.0, 11.0, 13.0],
                "min_temperature_grid": [11.0, 13.0, 10.0, 14.0],
            }
        )

        metrics = station_compare._compute_aggregated_metrics(
            overlap,
            variable="min_temperature",
            frequency="Y",
        )

        self.assertIsNotNone(metrics)
        self.assertEqual("annual", metrics["timescale"])
        self.assertEqual(2, metrics["period_count"])
        self.assertEqual(11.5, metrics["station_mean"])
        self.assertEqual(12.0, metrics["grid_mean"])
        self.assertEqual(0.5, metrics["bias"])
        self.assertEqual(0.5, metrics["mae"])
        self.assertEqual(0.7071, metrics["rmse"])

    def test_compute_aggregated_metrics_seasonal_precipitation(self):
        overlap = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    [
                        "2020-12-01",
                        "2021-01-15",
                        "2021-03-01",
                        "2021-07-01",
                    ]
                ),
                "precipitation_station": [2.0, 3.0, 4.0, 5.0],
                "precipitation_grid": [1.0, 5.0, 3.0, 7.0],
            }
        )

        metrics = station_compare._compute_aggregated_metrics(
            overlap,
            variable="precipitation",
            frequency="seasonal",
        )

        self.assertIsNotNone(metrics)
        self.assertEqual("seasonal", metrics["timescale"])
        self.assertEqual(3, metrics["period_count"])
        self.assertEqual(4.6667, metrics["station_mean"])
        self.assertEqual(5.3333, metrics["grid_mean"])
        self.assertEqual(0.6667, metrics["bias"])
        self.assertEqual(1.3333, metrics["mae"])
        self.assertEqual(1.4142, metrics["rmse"])
        self.assertEqual(14.0, metrics["station_total_mm"])
        self.assertEqual(16.0, metrics["grid_total_mm"])
        self.assertEqual(2.0, metrics["delta_total_mm"])

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_compute_xclim_precip_indices(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=366, freq="D"),
                "precipitation": [0.0] * 366,
            }
        )
        frame.loc[1, "precipitation"] = 1.0
        frame.loc[2, "precipitation"] = 5.0
        frame.loc[4, "precipitation"] = 10.0
        frame.loc[5, "precipitation"] = 2.0
        frame.loc[8, "precipitation"] = 20.0
        frame.loc[30, "precipitation"] = 11.0

        result = compute_xclim_precip_indices(frame)

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertEqual(20.0, row["rx1day_mm"])
        self.assertEqual(32.0, row["rx5day_mm"])
        self.assertEqual(335.0, row["cdd_days"])
        self.assertEqual(2.0, row["cwd_days"])
        self.assertEqual(3.0, row["r10mm_days"])
        self.assertEqual(1.0, row["r20mm_days"])
        self.assertAlmostEqual(8.1667, row["sdii_mm_per_day"], places=4)

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_compare_xclim_precip_indices(self):
        overlap = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=366, freq="D"),
                "precipitation_station": [0.0] * 366,
                "precipitation_grid": [0.0] * 366,
            }
        )
        overlap.loc[8, "precipitation_station"] = 20.0
        overlap.loc[8, "precipitation_grid"] = 18.0
        overlap.loc[30, "precipitation_station"] = 11.0
        overlap.loc[30, "precipitation_grid"] = 13.0

        result = compare_xclim_precip_indices(overlap)

        self.assertEqual(1, len(result))
        row = result[0]
        self.assertEqual("2020-01-01", row["period_start"])
        self.assertEqual(20.0, row["rx1day_mm_station"])
        self.assertEqual(18.0, row["rx1day_mm_grid"])
        self.assertEqual(-2.0, row["rx1day_mm_delta"])

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_compute_xclim_precip_indices_tolerates_small_daily_gaps(self):
        full = pd.date_range("2020-01-01", "2020-12-31", freq="D")
        keep = full.delete(list(range(0, 20)))
        frame = pd.DataFrame(
            {
                "date": keep,
                "precipitation": [0.0] * len(keep),
            }
        )
        frame.loc[1, "precipitation"] = 5.0
        frame.loc[10, "precipitation"] = 20.0
        frame.loc[30, "precipitation"] = 11.0

        result = compute_xclim_precip_indices(frame, min_days_per_year=330)

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertEqual(20.0, row["rx1day_mm"])

    def test_assess_xclim_precip_annual_readiness_rejects_sparse_overlap(self):
        overlap = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-05"]),
                "precipitation_station": [0.0, 5.0, 10.0],
            }
        )

        result = assess_xclim_precip_annual_readiness(
            overlap,
            value_column="precipitation_station",
        )

        self.assertIsNotNone(result)
        self.assertIn("too sparse", result)

    def test_assess_xclim_precip_annual_readiness_accepts_high_coverage_with_some_missing_days(self):
        full = pd.date_range("2020-01-01", "2020-12-31", freq="D")
        keep = full.delete(list(range(0, 20)))
        overlap = pd.DataFrame(
            {
                "date": keep,
                "precipitation_station": [1.0] * len(keep),
            }
        )

        result = assess_xclim_precip_annual_readiness(
            overlap,
            value_column="precipitation_station",
        )

        self.assertIsNone(result)

    def test_fetch_anchor_elevation_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first = dem._save_anchor_elevation
            first(
                lat=-1.286,
                lon=36.817,
                anchor_elevation_m=1684.2,
                dataset=dem.DEFAULT_DEM_DATASET,
                band=dem.DEFAULT_DEM_BAND,
                scale_m=dem.DEFAULT_DEM_SCALE_M,
                cache_dir=tmpdir,
            )
            cached = dem.fetch_anchor_elevation(
                lat=-1.286,
                lon=36.817,
                cache_dir=tmpdir,
                refresh_cache=False,
            )
        self.assertAlmostEqual(1684.2, cached, places=6)

    def test_apply_unit_conversions_for_ghcn_daily(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "precipitation": [12.0],
                "max_temperature": [300.0],
                "min_temperature": [250.0],
                "wind_speed": [35.0],
            }
        )

        converted = apply_unit_conversions(raw_df, source="ghcn_daily", verbose=True)

        self.assertAlmostEqual(1.2, converted.loc[0, "precipitation"], places=6)
        self.assertAlmostEqual(30.0, converted.loc[0, "max_temperature"], places=6)
        self.assertAlmostEqual(25.0, converted.loc[0, "min_temperature"], places=6)
        self.assertAlmostEqual(3.5, converted.loc[0, "wind_speed"], places=6)

    def test_preprocess_station_data_derives_mean_temperature(self):
        transformed_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "precipitation": [12.0],
                "max_temperature": [300.0],
                "min_temperature": [250.0],
            }
        )

        result = preprocess_transformed_data(transformed_df, source="ghcn_daily", verbose=False)

        self.assertIn("mean_temperature", result.columns)
        self.assertAlmostEqual(27.5, result.loc[0, "mean_temperature"], places=6)

    def test_fetch_data_uses_station_specific_default_variables(self):
        seen = {}

        class _FakeSourceData:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            def download(self):
                return pd.DataFrame({"date": pd.to_datetime(["2020-01-01"])})

        orig_source_data = fetch_data_module.SourceData
        fetch_data_module.SourceData = _FakeSourceData
        try:
            fetch_data_module.fetch_data(
                source="ghcn_daily",
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                stage="raw",
                station_id="KE000063612",
            )
        finally:
            fetch_data_module.SourceData = orig_source_data

        self.assertEqual("KE000063612", seen["station_id"])
        self.assertEqual(
            [ClimateVariable.precipitation, ClimateVariable.max_temperature, ClimateVariable.min_temperature],
            seen["variables"],
        )

    def test_fetch_data_uses_gsod_station_specific_default_variables(self):
        seen = {}

        class _FakeSourceData:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            def download(self):
                return pd.DataFrame({"date": pd.to_datetime(["2020-01-01"])})

        orig_source_data = fetch_data_module.SourceData
        fetch_data_module.SourceData = _FakeSourceData
        try:
            fetch_data_module.fetch_data(
                source="gsod",
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                stage="raw",
                station_id="63742099999",
            )
        finally:
            fetch_data_module.SourceData = orig_source_data

        self.assertEqual("63742099999", seen["station_id"])
        self.assertEqual(
            [ClimateVariable.precipitation, ClimateVariable.max_temperature, ClimateVariable.min_temperature],
            seen["variables"],
        )

    def test_fetch_records_prints_timing_and_cache_status_when_verbose(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Near TAVG",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                }
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )
        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = lambda **kwargs: "\n".join(
            [
                _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10, 0]),
                _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300, 300]),
                _build_dly_line("AAA00000001", 2020, 1, "TMIN", [200, 200]),
            ]
        )
        buf = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = buf
            frame = ghcn.fetch_ghcn_daily_records(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                verbose=True,
            )
        finally:
            sys.stdout = orig_stdout
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        rendered = buf.getvalue()
        self.assertIn("GHCN-Daily fetch start", rendered)
        self.assertIn("Station selected", rendered)
        self.assertIn("Station file ready", rendered)
        self.assertIn("GHCN-Daily fetch complete", rendered)
        self.assertEqual(2, len(frame))

    def test_fetch_records_with_station_id_bypasses_completeness_screen(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Explicit station",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                }
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )
        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        orig_select = ghcn.select_ghcn_station
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn.select_ghcn_station = lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not re-select"))
        ghcn._download_text = lambda **kwargs: "\n".join(
            [
                _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10]),
                _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300]),
                _build_dly_line("AAA00000001", 2020, 1, "TMIN", [200]),
            ]
        )
        try:
            frame = ghcn.fetch_ghcn_daily_records(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                station_id="AAA00000001",
                verbose=False,
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download
            ghcn.select_ghcn_station = orig_select

        self.assertEqual("AAA00000001", frame.loc[0, "station_id"])
        self.assertEqual("Explicit station", frame.loc[0, "station_name"])

    def test_list_candidates_uses_distance_and_completeness(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Near incomplete",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                },
                {
                    "station_id": "BBB00000002",
                    "lat": -1.300,
                    "lon": 36.830,
                    "elevation_m": 1510.0,
                    "station_name": "Near complete",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                },
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
                {"station_id": "BBB00000002", "lat": -1.300, "lon": 36.830, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "BBB00000002", "lat": -1.300, "lon": 36.830, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "BBB00000002", "lat": -1.300, "lon": 36.830, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )

        def fake_download_text(**kwargs):
            if "AAA00000001" in kwargs["url"]:
                return "\n".join(
                    [
                        _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10, -9999]),
                        _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300, -9999]),
                        _build_dly_line("AAA00000001", 2020, 1, "TMIN", [200, -9999]),
                    ]
                )
            return "\n".join(
                [
                    _build_dly_line("BBB00000002", 2020, 1, "PRCP", [10, 20]),
                    _build_dly_line("BBB00000002", 2020, 1, "TMAX", [300, 310]),
                    _build_dly_line("BBB00000002", 2020, 1, "TMIN", [200, 210]),
                ]
            )

        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = fake_download_text
        try:
            result = ghcn.list_ghcn_station_candidates(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                min_completeness_ratio=0.75,
                candidate_limit=5,
                score_limit=5,
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        self.assertEqual(2, len(result))
        self.assertEqual("BBB00000002", result.iloc[0]["station_id"])
        self.assertAlmostEqual(1.0, result.iloc[0]["min_completeness_ratio"], places=6)

    def test_download_station_data_auto_two_fetches_top_two_candidates(self):
        candidates = pd.DataFrame(
            [
                {"station_id": "AAA00000001"},
                {"station_id": "BBB00000002"},
                {"station_id": "CCC00000003"},
            ]
        )
        fetch_calls = []

        orig_select = station_download.select_ghcn_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.select_ghcn_station_candidates = lambda **kwargs: candidates.iloc[:2].copy()

        def fake_fetch_data(**kwargs):
            fetch_calls.append(kwargs["station_id"])
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01"]),
                    "station_id": [kwargs["station_id"]],
                    "precipitation": [1.0],
                }
            )

        station_download.fetch_data = fake_fetch_data
        try:
            result = station_download.download_station_data(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-2",
            )
        finally:
            station_download.select_ghcn_station_candidates = orig_select
            station_download.fetch_data = orig_fetch

        self.assertEqual(["AAA00000001", "BBB00000002"], fetch_calls)
        self.assertEqual(2, len(result))
        self.assertIn("selection_rank", result.columns)
        self.assertIn("selection_mode", result.columns)

    def test_download_station_data_auto_three_fetches_top_three_candidates(self):
        candidates = pd.DataFrame(
            [
                {"station_id": "AAA00000001"},
                {"station_id": "BBB00000002"},
                {"station_id": "CCC00000003"},
            ]
        )
        fetch_calls = []

        orig_select = station_download.select_ghcn_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.select_ghcn_station_candidates = lambda **kwargs: candidates.iloc[:3].copy()

        def fake_fetch_data(**kwargs):
            fetch_calls.append(kwargs["station_id"])
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01"]),
                    "station_id": [kwargs["station_id"]],
                    "precipitation": [1.0],
                }
            )

        station_download.fetch_data = fake_fetch_data
        try:
            result = station_download.download_station_data(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-3",
            )
        finally:
            station_download.select_ghcn_station_candidates = orig_select
            station_download.fetch_data = orig_fetch

        self.assertEqual(["AAA00000001", "BBB00000002", "CCC00000003"], fetch_calls)
        self.assertEqual(3, len(result))

    def test_auto_station_selector_prefers_best_backend_per_wmo_station(self):
        ghcn_candidates = pd.DataFrame(
            [
                {
                    "station_id": "GHCN001",
                    "station_name": "Shared station",
                    "wmo_id": "63741",
                    "lat": -1.3,
                    "lon": 36.8,
                    "distance_km": 5.0,
                    "mean_completeness_ratio": 0.35,
                    "min_completeness_ratio": 0.20,
                    "n_fields_passing_threshold": 0,
                    "all_fields_meet_threshold": False,
                    "field_ratios": {"precipitation": 0.35},
                }
            ]
        )
        gsod_candidates = pd.DataFrame(
            [
                {
                    "station_id": "63741099999",
                    "station_name": "Shared station",
                    "wmo_id": "63741",
                    "lat": -1.3,
                    "lon": 36.8,
                    "distance_km": 5.0,
                    "mean_completeness_ratio": 0.82,
                    "min_completeness_ratio": 0.82,
                    "n_fields_passing_threshold": 1,
                    "all_fields_meet_threshold": True,
                    "field_ratios": {"precipitation": 0.82},
                }
            ]
        )

        orig_ghcn = station_selector.list_ghcn_station_candidates
        orig_gsod = station_selector.list_gsod_station_candidates
        station_selector.list_ghcn_station_candidates = lambda **kwargs: ghcn_candidates.copy()
        station_selector.list_gsod_station_candidates = lambda **kwargs: gsod_candidates.copy()
        try:
            result = station_selector.list_station_candidates(
                station_source="auto",
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                candidate_limit=5,
            )
        finally:
            station_selector.list_ghcn_station_candidates = orig_ghcn
            station_selector.list_gsod_station_candidates = orig_gsod

        self.assertEqual(1, len(result))
        self.assertEqual("gsod", result.iloc[0]["station_source"])
        self.assertEqual("63741099999", result.iloc[0]["station_id"])

    def test_auto_station_selector_surfaces_backend_failure_warning(self):
        ghcn_candidates = pd.DataFrame(
            [
                {
                    "station_id": "KEM00063741",
                    "station_name": "Dagoretti",
                    "wmo_id": "63741",
                    "lat": -1.3,
                    "lon": 36.75,
                    "distance_km": 7.6,
                    "mean_completeness_ratio": 0.22,
                    "min_completeness_ratio": 0.22,
                    "n_fields_passing_threshold": 0,
                    "all_fields_meet_threshold": False,
                    "field_ratios": {"precipitation": 0.22},
                }
            ]
        )

        orig_ghcn = station_selector.list_ghcn_station_candidates
        orig_gsod = station_selector.list_gsod_station_candidates
        station_selector.list_ghcn_station_candidates = lambda **kwargs: ghcn_candidates.copy()
        station_selector.list_gsod_station_candidates = lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("GSOD probe timed out")
        )
        try:
            result = station_selector.list_station_candidates(
                station_source="auto",
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                candidate_limit=5,
            )
        finally:
            station_selector.list_ghcn_station_candidates = orig_ghcn
            station_selector.list_gsod_station_candidates = orig_gsod

        warnings = result.attrs.get("selection_warnings", [])
        self.assertTrue(any("skipped backend" in str(item).lower() for item in warnings))

    def test_download_station_data_auto_uses_candidate_backend_source(self):
        candidates = pd.DataFrame(
            [
                {
                    "station_source": "gsod",
                    "station_id": "63741099999",
                    "station_name": "Shared station",
                    "distance_km": 5.0,
                }
            ]
        )
        fetch_calls = []

        orig_select = station_download.select_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.select_station_candidates = lambda **kwargs: candidates.copy()

        def fake_fetch_data(**kwargs):
            fetch_calls.append((kwargs["source"], kwargs["station_id"]))
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01"]),
                    "station_id": [kwargs["station_id"]],
                    "precipitation": [1.0],
                    "station_source": [kwargs["source"]],
                }
            )

        station_download.fetch_data = fake_fetch_data
        try:
            result = station_download.download_station_data(
                station_source="auto",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-1",
            )
        finally:
            station_download.select_station_candidates = orig_select
            station_download.fetch_data = orig_fetch

        self.assertEqual([("gsod", "63741099999")], fetch_calls)
        self.assertEqual("gsod", result.loc[0, "station_source"])

    def test_download_station_data_auto_propagates_list_metadata(self):
        candidates = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "selection_status": "relaxed",
                    "selection_threshold_used": 0.5,
                    "threshold_status": "partial_fields",
                    "n_fields_passing_threshold": 1,
                    "requested_fields": "precipitation,max_temperature,min_temperature",
                    "fields_passing_threshold": ["precipitation"],
                    "fields_failing_threshold": ["max_temperature", "min_temperature"],
                    "distance_km": 7.61,
                    "elevation_diff_m": pd.NA,
                }
            ]
        )

        orig_select = station_download.select_ghcn_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.select_ghcn_station_candidates = lambda **kwargs: candidates.copy()

        def fake_fetch_data(**kwargs):
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                    "station_id": [kwargs["station_id"], kwargs["station_id"]],
                    "precipitation": [1.0, 0.0],
                }
            )

        station_download.fetch_data = fake_fetch_data
        try:
            result = station_download.download_station_data(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-1",
                disable_completeness_guard=False,
            )
        finally:
            station_download.select_ghcn_station_candidates = orig_select
            station_download.fetch_data = orig_fetch

        self.assertEqual(2, len(result))
        self.assertEqual("partial_fields", result.loc[0, "threshold_status"])
        self.assertEqual(
            ["max_temperature", "min_temperature"],
            result.loc[0, "fields_failing_threshold"],
        )
        self.assertEqual(
            ["max_temperature", "min_temperature"],
            result.loc[1, "fields_failing_threshold"],
        )

    def test_download_station_data_auto_guard_disabled_clears_threshold_diagnostics(self):
        candidates = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "threshold_status": "below_threshold",
                    "fields_passing_threshold": ["precipitation"],
                    "fields_failing_threshold": ["max_temperature"],
                    "n_fields_passing_threshold": 1,
                    "all_fields_meet_threshold": False,
                }
            ]
        )

        orig_list = station_download.list_ghcn_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.list_ghcn_station_candidates = lambda **kwargs: candidates.copy()
        station_download.fetch_data = lambda **kwargs: pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "station_id": [kwargs["station_id"]],
                "precipitation": [1.0],
            }
        )
        try:
            result = station_download.download_station_data(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-1",
                disable_completeness_guard=True,
            )
        finally:
            station_download.list_ghcn_station_candidates = orig_list
            station_download.fetch_data = orig_fetch

        self.assertEqual("guard_disabled", result.loc[0, "selection_status"])
        self.assertEqual("guard_disabled", result.loc[0, "threshold_status"])
        self.assertTrue(pd.isna(result.loc[0, "fields_failing_threshold"]))
        self.assertTrue(pd.isna(result.loc[0, "n_fields_passing_threshold"]))

    def test_render_station_output_summary_prints_station_headlines(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "station_id": ["AAA00000001", "AAA00000001"],
                "station_name": ["Demo Station", "Demo Station"],
                "selection_rank": [1, 1],
                "selection_status": ["relaxed", "relaxed"],
                "selection_threshold_used": [0.5, 0.5],
                "requested_fields": ["precipitation,max_temperature", "precipitation,max_temperature"],
                "fields_passing_threshold": [["precipitation"], ["precipitation"]],
                "fields_failing_threshold": [["max_temperature"], ["max_temperature"]],
                "distance_km": [7.61, 7.61],
                "station_elevation_m": [1798.0, 1798.0],
                "elevation_diff_m": [pd.NA, pd.NA],
                "precipitation": [1.0, 0.0],
                "max_temperature": [pd.NA, pd.NA],
            }
        )
        rendered = station_download.render_station_output_summary(
            frame,
            selection_mode="auto",
        )
        self.assertIn("Returned stations: 1 | rows=2", rendered)
        self.assertIn("Demo Station", rendered)
        self.assertIn("precipitation=2/2", rendered)

    def test_render_list_candidate_summary_uses_field_counts_not_min_mean(self):
        frame = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "station_name": "Demo Candidate",
                    "distance_km": 7.61,
                    "elevation_m": 1798.0,
                    "elevation_diff_m": 118.0,
                    "threshold_status": "below_threshold",
                    "requested_fields": "precipitation,max_temperature,min_temperature",
                    "fields_passing_threshold": [],
                    "fields_failing_threshold": ["precipitation", "max_temperature", "min_temperature"],
                    "field_counts": {
                        "precipitation": 0,
                        "max_temperature": 0,
                        "min_temperature": 10,
                    },
                    "expected_days": 10,
                }
            ]
        )
        rendered = station_download.render_station_output_summary(
            frame,
            selection_mode="list",
        )
        self.assertIn("coverage=precipitation=0/10 (0%)", rendered)
        self.assertIn("min_temperature=10/10 (100%)", rendered)
        self.assertNotIn("completeness min=", rendered)

    def test_download_station_data_auto_reports_when_fewer_candidates_than_requested(self):
        candidates = pd.DataFrame(
            [
                {"station_id": "AAA00000001"},
                {"station_id": "BBB00000002"},
            ]
        )
        orig_select = station_download.select_ghcn_station_candidates
        orig_fetch = station_download.fetch_data
        station_download.select_ghcn_station_candidates = lambda **kwargs: candidates.copy()
        station_download.fetch_data = lambda **kwargs: pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "station_id": [kwargs["station_id"]],
                "precipitation": [1.0],
            }
        )
        buf = StringIO()
        orig_stdout = sys.stdout
        try:
            sys.stdout = buf
            station_download.download_station_data(
                station_source="ghcn_daily",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
                selection_mode="auto",
                auto_select="auto-3",
                disable_completeness_guard=False,
                verbose=True,
            )
        finally:
            sys.stdout = orig_stdout
            station_download.select_ghcn_station_candidates = orig_select
            station_download.fetch_data = orig_fetch

        self.assertIn("Requested 3 station(s) via auto-3, but only 2 candidate(s) available", buf.getvalue())

    def test_list_candidates_keeps_station_when_one_requested_variable_passes_threshold(self):
        stations = pd.DataFrame(
            [
                {
                    "station_id": "AAA00000001",
                    "lat": -1.280,
                    "lon": 36.820,
                    "elevation_m": 1500.0,
                    "station_name": "Partial pass",
                    "state": None,
                    "gsn_flag": None,
                    "hcn_crn_flag": None,
                    "wmo_id": None,
                }
            ]
        )
        inventory = pd.DataFrame(
            [
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "PRCP", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMAX", "start_year": 1990, "end_year": 2025},
                {"station_id": "AAA00000001", "lat": -1.280, "lon": 36.820, "element": "TMIN", "start_year": 1990, "end_year": 2025},
            ]
        )

        def fake_download_text(**kwargs):
            return "\n".join(
                [
                    _build_dly_line("AAA00000001", 2020, 1, "PRCP", [10, 20]),
                    _build_dly_line("AAA00000001", 2020, 1, "TMAX", [300, -9999]),
                    _build_dly_line("AAA00000001", 2020, 1, "TMIN", [200, -9999]),
                ]
            )

        orig_stations = ghcn.load_ghcn_stations
        orig_inventory = ghcn.load_ghcn_inventory
        orig_download = ghcn._download_text
        ghcn.load_ghcn_stations = lambda **kwargs: stations.copy()
        ghcn.load_ghcn_inventory = lambda **kwargs: inventory.copy()
        ghcn._download_text = fake_download_text
        try:
            result = ghcn.list_ghcn_station_candidates(
                location_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                min_completeness_ratio=0.75,
                candidate_limit=5,
                score_limit=5,
            )
        finally:
            ghcn.load_ghcn_stations = orig_stations
            ghcn.load_ghcn_inventory = orig_inventory
            ghcn._download_text = orig_download

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertEqual("AAA00000001", row["station_id"])
        self.assertEqual(1, row["n_fields_passing_threshold"])
        self.assertEqual(["precipitation"], row["fields_passing_threshold"])
        self.assertIn("max_temperature", row["fields_failing_threshold"])
        self.assertIn("min_temperature", row["fields_failing_threshold"])
