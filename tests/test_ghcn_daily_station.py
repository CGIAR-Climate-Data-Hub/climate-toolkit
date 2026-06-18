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
from climate_tookit.weather_station.custom_station import (
    custom_station_format_help,
    load_custom_station_data,
)
from climate_tookit.fetch_data.preprocess_data.preprocess_data import (
    apply_unit_conversions,
    clean_climate_data,
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
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GSOD_LIKE_CUSTOM_STATION_FIXTURE = FIXTURES_DIR / "custom_station_gsod_like.csv"


def _build_dly_line(station_id: str, year: int, month: int, element: str, values: list[int]) -> str:
    padded = list(values) + [-9999] * (31 - len(values))
    day_chunks = [f"{value:>5}   " for value in padded[:31]]
    return f"{station_id}{year:04d}{month:02d}{element}{''.join(day_chunks)}"


class GHCNDailyStationTests(unittest.TestCase):
    def test_load_gsod_stations_parses_isd_history_metadata(self):
        csv_text = "\n".join(
            [
                "USAF,WBAN,STATION NAME,CTRY,STATE,ICAO,LAT,LON,ELEV(M),BEGIN,END",
                "637400,99999,JOMO KENYATTA INTL,KE,,HKJK,-1.317,36.917,1624,19570101,20241231",
                "637410,99999,NAIROBI/DAGORETTI,KE,,HKNW,-1.300,36.750,1798,19500101,20221231",
            ]
        )
        orig_loader = gsod._download_station_history_text
        gsod._download_station_history_text = lambda **kwargs: csv_text
        try:
            frame = gsod.load_gsod_stations(cache_dir="unused", refresh_cache=False)
        finally:
            gsod._download_station_history_text = orig_loader

        self.assertEqual(2, len(frame))
        self.assertEqual(["63740099999", "63741099999"], frame["station_id"].tolist())
        self.assertEqual("JOMO KENYATTA INTL", frame.iloc[0]["station_name"])
        self.assertEqual(-1.317, frame.iloc[0]["lat"])
        self.assertEqual(1624, frame.iloc[0]["elevation_m"])


class PreprocessClimateDataTests(unittest.TestCase):
    def test_preprocess_preserves_all_missing_precipitation(self):
        transformed_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-03-01", "2020-03-02"]),
                "precipitation": [None, None],
                "max_temperature": [24.0, 25.0],
                "min_temperature": [14.0, 15.0],
            }
        )

        result = preprocess_transformed_data(
            transformed_df,
            source="tamsat",
            verbose=False,
        )

        self.assertTrue(result["precipitation"].isna().all())

    def test_clean_climate_data_grouped_keeps_all_missing_precip_group_missing(self):
        raw_df = pd.DataFrame(
            {
                "site": ["a", "a", "b", "b"],
                "date": pd.to_datetime(["2020-03-01", "2020-03-02", "2020-03-01", "2020-03-02"]),
                "precipitation": [1.0, None, None, None],
            }
        )

        result = clean_climate_data(raw_df, group_columns=["site"])

        self.assertEqual([1.0, 0.0], result.loc[result["site"] == "a", "precipitation"].tolist())
        self.assertTrue(result.loc[result["site"] == "b", "precipitation"].isna().all())

    def test_download_station_history_text_rejects_html_error_page(self):
        class _Resp:
            status_code = 200
            text = "<!DOCTYPE HTML><html><body>503 Service Unavailable</body></html>"

            def raise_for_status(self):
                return None

        orig_get = gsod.requests.get
        gsod.requests.get = lambda *args, **kwargs: _Resp()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaisesRegex(RuntimeError, "non-CSV content"):
                    gsod._download_station_history_text(
                        cache_dir=tmpdir,
                        refresh_cache=True,
                    )
        finally:
            gsod.requests.get = orig_get

    def test_render_candidate_map_html_uses_leaflet_and_focal_location_label(self):
        frame = pd.DataFrame(
            {
                "station_id": ["63740099999"],
                "station_name": ["JOMO KENYATTA INTL"],
                "station_source": ["gsod"],
                "lat": [-1.32],
                "lon": [36.93],
                "distance_km": [11.64],
                "min_completeness_ratio": [0.93],
                "mean_completeness_ratio": [0.97],
                "field_counts": [{"precipitation": 3386, "max_temperature": 3614, "min_temperature": 3614}],
                "expected_days": [3653],
                "requested_fields": [["precipitation", "max_temperature", "min_temperature"]],
            }
        )

        html_text = station_download._render_candidate_map_html(
            candidates=frame,
            anchor_lat=-1.286,
            anchor_lon=36.817,
            title="Observed station candidate review",
            period_start="2011-01-01",
            period_end="2020-12-31",
            scope_summary={
                "scope_label": "NOAA GHCN + GSOD",
                "search_radius_km": 100.0,
                "ghcn_local_station_records": 2,
                "gsod_local_station_records": 2,
                "unique_noaa_physical_stations": 2,
                "displayed_station_count": 1,
                "deduped_backend_records": 2,
                "scope_note": "GSOD local discovery currently keys off WMO-linked station metadata.",
            },
        )

        self.assertIn("leaflet", html_text.lower())
        self.assertIn("Focal location", html_text)
        self.assertIn("Map review", html_text)
        self.assertIn("CARTO", html_text)
        self.assertIn("Assessment Period", html_text)
        self.assertIn("2011-01-01 to 2020-12-31", html_text)
        self.assertIn("Variable completeness", html_text)
        self.assertIn("precipitation: 3386/3653", html_text)
        self.assertIn("GHCN Records In Bounds", html_text)
        self.assertIn("GSOD Records In Bounds", html_text)
        self.assertIn("Unique Physical Stations", html_text)
        self.assertIn("backend duplicates merged=2", html_text)

    def test_station_scope_summary_counts_unique_physical_stations_across_backends(self):
        fake_ghcn_stations = pd.DataFrame(
            {
                "station_id": ["KEM00063741", "KE000063740"],
                "lat": [-1.300, -1.317],
                "lon": [36.750, 36.917],
                "elevation_m": [1798.0, 1624.0],
                "station_name": ["NAIROBI/DAGORETTI", "JOMO KENYATTA INTL"],
                "wmo_id": ["63741", "63740"],
            }
        )
        fake_gsod_stations = pd.DataFrame(
            {
                "station_id": ["63741099999", "63740099999"],
                "lat": [-1.300, -1.317],
                "lon": [36.750, 36.917],
                "elevation_m": [1798.0, 1624.0],
                "station_name": ["NAIROBI/DAGORETTI", "JOMO KENYATTA INTL"],
            }
        )
        orig_ghcn_loader = station_selector.load_ghcn_stations
        orig_gsod_loader = station_selector.load_gsod_stations
        station_selector.load_ghcn_stations = lambda **kwargs: fake_ghcn_stations.copy()
        station_selector.load_gsod_stations = lambda **kwargs: fake_gsod_stations.copy()
        try:
            summary = station_selector.summarize_station_search_scope(
                station_source="auto",
                location_coord=(-1.286, 36.817),
                max_distance_km=100.0,
                displayed_candidates=pd.DataFrame({"station_id": ["63740099999", "63741099999"]}),
            )
        finally:
            station_selector.load_ghcn_stations = orig_ghcn_loader
            station_selector.load_gsod_stations = orig_gsod_loader

        self.assertEqual("NOAA GHCN + GSOD", summary["scope_label"])
        self.assertEqual(2, summary["ghcn_local_station_records"])
        self.assertEqual(2, summary["gsod_local_station_records"])
        self.assertEqual(2, summary["unique_noaa_physical_stations"])
        self.assertEqual(2, summary["displayed_station_count"])
        self.assertEqual(2, summary["deduped_backend_records"])

    def test_open_report_html_uses_available_opener(self):
        calls = []
        orig_which = station_download.shutil.which
        orig_run = station_download.subprocess.run
        station_download.shutil.which = lambda name: "/usr/bin/open" if name == "open" else None
        station_download.subprocess.run = lambda cmd, check=False: calls.append((cmd, check))
        try:
            opened = station_download._open_report_html("demo.html")
        finally:
            station_download.shutil.which = orig_which
            station_download.subprocess.run = orig_run

        self.assertTrue(opened)
        self.assertEqual([(["/usr/bin/open", "demo.html"], False)], calls)

    def test_download_station_data_loads_custom_csv_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "custom_station.csv"
            pd.DataFrame(
                {
                    "date": ["2020-01-01", "2020-01-02"],
                    "rainfall": [5.0, 0.0],
                    "tmax": [25.0, 26.0],
                    "tmin": [15.0, 16.0],
                }
            ).to_csv(csv_path, index=False)

            first = station_download.download_station_data(
                station_source="custom_csv",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                selection_mode="specified",
                custom_station_file=str(csv_path),
                custom_station_name="User Station",
                cache_dir=tmpdir,
                verbose=False,
            )
            second = station_download.download_station_data(
                station_source="custom_csv",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                ],
                selection_mode="specified",
                custom_station_file=str(csv_path),
                custom_station_name="User Station",
                cache_dir=tmpdir,
                verbose=False,
            )

        self.assertEqual([5.0, 0.0], first["precipitation"].tolist())
        self.assertEqual("custom_csv", first.loc[0, "station_source"])
        self.assertEqual("User Station", first.loc[0, "station_name"])
        self.assertFalse(first.attrs["cache_hit"])
        self.assertTrue(second.attrs["cache_hit"])

    def test_download_station_data_requires_custom_station_file_for_custom_source(self):
        with self.assertRaisesRegex(ValueError, "--custom-station-file"):
            station_download.download_station_data(
                station_source="custom_csv",
                station_coord=(-1.286, 36.817),
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 2),
                variables=[ClimateVariable.precipitation],
            )

    def test_load_custom_station_data_missing_date_column_explains_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "custom_station.csv"
            pd.DataFrame({"rainfall": [5.0]}).to_csv(csv_path, index=False)
            with self.assertRaisesRegex(ValueError, "date column"):
                load_custom_station_data(
                    custom_station_file=csv_path,
                    date_from=date(2020, 1, 1),
                    date_to=date(2020, 1, 2),
                    variables=[ClimateVariable.precipitation],
                )
        self.assertIn("rainfall/precip/precipitation", custom_station_format_help())
        self.assertIn("GSOD-style columns PRCP, MAX, MIN, TEMP, and WDSP", custom_station_format_help())

    def test_load_custom_station_data_accepts_gsod_like_columns_and_units(self):
        frame = load_custom_station_data(
            custom_station_file=GSOD_LIKE_CUSTOM_STATION_FIXTURE,
            date_from=date(2020, 1, 1),
            date_to=date(2020, 1, 10),
            variables=[
                ClimateVariable.precipitation,
                ClimateVariable.max_temperature,
                ClimateVariable.min_temperature,
                ClimateVariable.mean_temperature,
                ClimateVariable.wind_speed,
            ],
            stage="transformed",
            station_coord=(-1.286, 36.817),
            cache_dir=None,
            refresh_cache=True,
            custom_temp_unit="f",
            custom_precip_unit="inch",
        )

        self.assertEqual(
            [
                "date",
                "station_distance_km",
                "station_elevation_m",
                "station_id",
                "station_lat",
                "station_lon",
                "station_name",
                "station_source",
                "precipitation",
                "max_temperature",
                "min_temperature",
                "mean_temperature",
                "wind_speed",
            ],
            frame.columns.tolist(),
        )
        self.assertEqual("63740099999", frame.loc[0, "station_id"])
        self.assertEqual("JOMO KENYATTA INTL", frame.loc[0, "station_name"])
        self.assertAlmostEqual(0.0, frame.loc[0, "precipitation"], places=2)
        self.assertAlmostEqual(1.27, frame.loc[2, "precipitation"], places=2)
        self.assertAlmostEqual(25.0, frame.loc[0, "max_temperature"], places=2)
        self.assertAlmostEqual(14.44, frame.loc[0, "min_temperature"], places=2)
        self.assertAlmostEqual(19.72, frame.loc[0, "mean_temperature"], places=2)
        self.assertAlmostEqual(7.5, frame.loc[0, "wind_speed"], places=2)
        self.assertEqual("custom_csv", frame.loc[0, "station_source"])

    def test_download_station_data_loads_gsod_like_custom_csv(self):
        frame = station_download.download_station_data(
            station_source="custom_csv",
            station_coord=(-1.286, 36.817),
            date_from=date(2020, 1, 1),
            date_to=date(2020, 1, 10),
            variables=[
                ClimateVariable.precipitation,
                ClimateVariable.max_temperature,
                ClimateVariable.min_temperature,
                ClimateVariable.mean_temperature,
            ],
            selection_mode="specified",
            custom_station_file=str(GSOD_LIKE_CUSTOM_STATION_FIXTURE),
            custom_station_name="GSOD Upload",
            custom_temp_unit="f",
            custom_precip_unit="inch",
            verbose=False,
        )

        self.assertEqual(10, len(frame))
        self.assertEqual("63740099999", frame.loc[0, "station_id"])
        self.assertEqual("JOMO KENYATTA INTL", frame.loc[0, "station_name"])
        self.assertAlmostEqual(19.72, frame.loc[0, "mean_temperature"], places=2)
        self.assertAlmostEqual(0.0, frame.loc[0, "station_distance_km"], places=2)

    def test_render_list_candidate_summary_for_custom_station_shows_source_file(self):
        frame = pd.DataFrame(
            {
                "station_source": ["custom_csv"],
                "station_id": ["demo_station"],
                "station_name": ["Demo Station"],
                "custom_station_file": ["demo.csv"],
                "field_counts": [{"precipitation": 10}],
                "expected_days": [10],
                "threshold_status": ["custom_file"],
                "requested_fields": [["precipitation"]],
                "fields_passing_threshold": [["precipitation"]],
                "fields_failing_threshold": [[]],
            }
        )
        rendered = station_download.render_station_output_summary(frame, selection_mode="list")
        self.assertIn("source file=demo.csv", rendered)

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

    def test_compare_station_to_grids_accepts_custom_csv_and_saves_candidate_map(self):
        grid_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "precipitation": [0.0, 4.0, 12.0],
            }
        )
        orig_fetch_grid_source = station_compare._fetch_grid_source
        station_compare._fetch_grid_source = lambda **kwargs: grid_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "custom_station.csv"
                report_prefix = Path(tmpdir) / "candidate_review"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                        "precipitation": [0.0, 5.0, 10.0],
                        "station_lat": [-1.30, -1.30, -1.30],
                        "station_lon": [36.75, 36.75, 36.75],
                    }
                ).to_csv(csv_path, index=False)
                result = station_compare.compare_station_to_grids(
                    station_source="custom_csv",
                    station_coord=(-1.286, 36.817),
                    date_from=date(2020, 1, 1),
                    date_to=date(2020, 1, 3),
                    grid_sources=["nasa_power"],
                    variables=[ClimateVariable.precipitation],
                    selection_mode="specified",
                    custom_station_file=str(csv_path),
                    custom_station_name="Uploaded Station",
                    candidate_report_prefix=str(report_prefix),
                    cache_dir=tmpdir,
                    verbose=False,
                )
                self.assertTrue(Path(result["candidate_review_artifacts"]["html"]).exists())
        finally:
            station_compare._fetch_grid_source = orig_fetch_grid_source

        self.assertEqual(1, len(result["metrics"]))
        self.assertIsNotNone(result["candidate_review_artifacts"])
        self.assertEqual("Uploaded Station", result["station_summary"][0]["station_name"])

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
        self.assertIn("selected_for=precipitation", result["selected_stations_by_variable"][0]["selection_reason"])
        self.assertIn("selected_for=min_temperature", result["selected_stations_by_variable"][1]["selection_reason"])
        self.assertEqual(2, len(result["station_summary"]))
        metric_variables = sorted(row["variable"] for row in result["metrics"])
        self.assertEqual(["min_temperature", "precipitation"], metric_variables)

    def test_compare_station_to_grids_best_per_variable_records_missing_variable_reason(self):
        precip_candidate = pd.DataFrame(
            {
                "station_source": ["ghcn_daily"],
                "station_id": ["RAIN001"],
                "station_name": ["Rain Station"],
                "distance_km": [5.0],
                "elevation_diff_m": [10.0],
                "selection_status": ["strict"],
                "selection_threshold_used": [0.7],
                "threshold_status": ["strict_all_fields"],
                "fields_passing_threshold": [["precipitation"]],
                "fields_failing_threshold": [[]],
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
        }
        grid_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                "precipitation": [1.5, 1.0],
            }
        )

        orig_list = station_compare.list_ghcn_station_candidates
        orig_download = station_compare.download_station_data
        orig_fetch_grid = station_compare._fetch_grid_source

        def _fake_list(**kwargs):
            variable = kwargs["variables"][0]
            if variable == ClimateVariable.precipitation:
                return precip_candidate.copy()
            return pd.DataFrame()

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

        missing = [
            row for row in result["selected_stations_by_variable"]
            if row["variable"] == "min_temperature"
        ][0]
        self.assertIsNone(missing["station_id"])
        self.assertEqual("unavailable", missing["selection_status"])
        self.assertIn("No candidate station found", missing["selection_reason"])
        self.assertTrue(any("No station selected for variable 'min_temperature'" in warning for warning in result["warnings"]))

    def test_render_compare_report_shows_selection_reasons(self):
        result = {
            "anchor_location": {"lat": -1.286, "lon": 36.817},
            "date_from": "2020-01-01",
            "date_to": "2020-01-02",
            "selection_strategy": "best_per_variable",
            "grid_sources": ["nasa_power"],
            "station_summary": [],
            "selected_stations_by_variable": [
                {
                    "variable": "precipitation",
                    "station_id": "RAIN001",
                    "station_name": "Rain Station",
                    "distance_km": 5.0,
                    "elevation_diff_m": 10.0,
                    "selection_status": "strict",
                    "selection_reason": "mode=auto | status=strict | selected_for=precipitation",
                },
                {
                    "variable": "min_temperature",
                    "station_id": None,
                    "station_name": None,
                    "distance_km": None,
                    "elevation_diff_m": None,
                    "selection_status": "unavailable",
                    "selection_reason": "No candidate station found for variable 'min_temperature'.",
                },
            ],
            "candidate_review_artifacts": None,
            "grid_failures": [],
            "grid_source_metadata": [],
            "use_case_rankings": [],
            "warnings": [],
            "metrics": [],
            "monthly_metrics": [],
            "seasonal_metrics": [],
            "annual_metrics": [],
            "xclim_precip_indices": [],
            "pooled_daily_metrics": [],
            "pooled_monthly_metrics": [],
            "pooled_seasonal_metrics": [],
            "pooled_annual_metrics": [],
            "overall_metrics": [],
        }
        rendered = station_compare.render_compare_report(result)
        self.assertIn("reason=mode=auto | status=strict | selected_for=precipitation", rendered)
        self.assertIn("min_temperature: no station selected | reason=No candidate station found", rendered)

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

    def test_annotate_annual_overlap_summary_assigns_high_confidence(self):
        overlap = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=365, freq="D"),
                "precipitation_station": [1.0] * 365,
                "precipitation_grid": [1.0] * 365,
            }
        )
        metric_row = {"variable": "precipitation"}
        result = station_compare._annotate_annual_overlap_summary(
            overlap,
            variable="precipitation",
            metric_row=metric_row,
        )
        self.assertEqual("high", result["confidence_class"])
        self.assertFalse(result["low_confidence"])
        self.assertEqual("suitable for annual interpretation", result["confidence_note"])
        self.assertEqual("descriptive_only", result["window_status"])
        self.assertAlmostEqual(1.0, result["window_years"], places=1)

    def test_annotate_annual_overlap_summary_assigns_very_low_confidence(self):
        overlap = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=20, freq="D"),
                "precipitation_station": [1.0] * 20,
                "precipitation_grid": [1.0] * 20,
            }
        )
        metric_row = {"variable": "precipitation"}
        result = station_compare._annotate_annual_overlap_summary(
            overlap,
            variable="precipitation",
            metric_row=metric_row,
        )
        self.assertEqual("very_low", result["confidence_class"])
        self.assertTrue(result["low_confidence"])
        self.assertEqual("sparse overlap; descriptive only", result["confidence_note"])
        self.assertEqual("descriptive_only", result["window_status"])

    def test_annotate_annual_overlap_summary_assigns_period_average_window(self):
        overlap = pd.DataFrame(
            {
                "date": pd.date_range("2010-01-01", "2020-12-31", freq="D"),
                "precipitation_station": 1.0,
                "precipitation_grid": 1.0,
            }
        )
        metric_row = {"variable": "precipitation"}
        result = station_compare._annotate_annual_overlap_summary(
            overlap,
            variable="precipitation",
            metric_row=metric_row,
        )
        self.assertEqual("period_average", result["window_status"])
        self.assertGreaterEqual(result["window_years"], 10.0)

    def test_render_compare_report_shows_confidence_summary(self):
        result = {
            "anchor_location": {"lat": -1.286, "lon": 36.817},
            "date_from": "2020-01-01",
            "date_to": "2020-12-31",
            "selection_strategy": "all_vars_single_station",
            "grid_sources": ["nasa_power"],
            "station_summary": [],
            "selected_stations_by_variable": [],
            "candidate_review_artifacts": None,
            "grid_failures": [],
            "grid_source_metadata": [],
            "use_case_rankings": [],
            "warnings": [],
            "confidence_summary": {
                "daily": {"high": 1, "medium": 0, "low": 0, "very_low": 1, "total": 2, "low_confidence": 1},
                "annual": {"high": 0, "medium": 1, "low": 0, "very_low": 0, "total": 1, "low_confidence": 0},
                "pooled_daily": {"high": 1, "medium": 0, "low": 0, "very_low": 0, "total": 1, "low_confidence": 0},
                "pooled_annual": {"high": 0, "medium": 0, "low": 1, "very_low": 0, "total": 1, "low_confidence": 1},
            },
            "metrics": [],
            "monthly_metrics": [],
            "seasonal_metrics": [],
            "annual_metrics": [],
            "xclim_precip_indices": [],
            "pooled_daily_metrics": [],
            "pooled_monthly_metrics": [],
            "pooled_seasonal_metrics": [],
            "pooled_annual_metrics": [],
            "overall_metrics": [],
        }
        rendered = station_compare.render_compare_report(result)
        self.assertIn("Confidence summary", rendered)
        self.assertIn("daily: high=1 medium=0 low=0 very_low=1", rendered)
        self.assertIn("pooled_annual: high=0 medium=0 low=1 very_low=0", rendered)

    def test_render_compare_report_shows_window_status_summary(self):
        result = {
            "anchor_location": {"lat": -1.286, "lon": 36.817},
            "date_from": "2010-01-01",
            "date_to": "2020-12-31",
            "selection_strategy": "all_vars_single_station",
            "grid_sources": ["nasa_power"],
            "station_summary": [],
            "selected_stations_by_variable": [],
            "candidate_review_artifacts": None,
            "grid_failures": [],
            "grid_source_metadata": [],
            "use_case_rankings": [],
            "warnings": [],
            "confidence_summary": {
                "daily": {"high": 0, "medium": 0, "low": 0, "very_low": 0, "total": 0, "low_confidence": 0},
                "annual": {"high": 0, "medium": 0, "low": 0, "very_low": 0, "total": 0, "low_confidence": 0},
                "pooled_daily": {"high": 0, "medium": 0, "low": 0, "very_low": 0, "total": 0, "low_confidence": 0},
                "pooled_annual": {"high": 0, "medium": 0, "low": 0, "very_low": 0, "total": 0, "low_confidence": 0},
            },
            "window_status_summary": {
                "annual": {
                    "descriptive_only": 1,
                    "screening_only": 0,
                    "preliminary_ranking": 0,
                    "period_average": 2,
                    "near_climatology": 0,
                    "climatology_grade": 0,
                    "total": 3,
                },
                "pooled_annual": {
                    "descriptive_only": 0,
                    "screening_only": 0,
                    "preliminary_ranking": 1,
                    "period_average": 0,
                    "near_climatology": 0,
                    "climatology_grade": 0,
                    "total": 1,
                },
            },
            "metrics": [],
            "monthly_metrics": [],
            "seasonal_metrics": [],
            "annual_metrics": [],
            "xclim_precip_indices": [],
            "pooled_daily_metrics": [],
            "pooled_monthly_metrics": [],
            "pooled_seasonal_metrics": [],
            "pooled_annual_metrics": [],
            "overall_metrics": [],
        }
        rendered = station_compare.render_compare_report(result)
        self.assertIn("Window status summary", rendered)
        self.assertIn("annual: descriptive_only=1 screening_only=0 preliminary_ranking=0 period_average=2", rendered)
        self.assertIn("pooled_annual: descriptive_only=0 screening_only=0 preliminary_ranking=1", rendered)

    def test_get_climate_data_applies_custom_station_override(self):
        stats_module = importlib.import_module("climate_tookit.climate_statistics.statistics")
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                "precipitation": [1.0, 2.0],
                "max_temperature": [24.0, 25.0],
                "min_temperature": [14.0, 15.0],
            }
        )
        orig_stats_call_preprocess = stats_module._call_preprocess
        stats_module._call_preprocess = lambda *args, **kwargs: base_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "override.csv"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-02"],
                        "precipitation": [9.0, 8.0],
                    }
                ).to_csv(csv_path, index=False)
                result = stats_module.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-02",
                    "agera_5",
                    custom_station_file=str(csv_path),
                    custom_station_variables=["precipitation"],
                    custom_precip_unit="mm",
                )
        finally:
            stats_module._call_preprocess = orig_stats_call_preprocess

        self.assertEqual([9.0, 8.0], result["precip"].tolist())
        self.assertEqual([24.0, 25.0], result["tmax"].tolist())

    def test_get_climate_data_custom_station_override_preserves_base_on_missing_days(self):
        stats_module = importlib.import_module("climate_tookit.climate_statistics.statistics")
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "precipitation": [1.0, 2.0, 3.0],
                "max_temperature": [24.0, 25.0, 26.0],
                "min_temperature": [14.0, 15.0, 16.0],
            }
        )
        orig_stats_call_preprocess = stats_module._call_preprocess
        stats_module._call_preprocess = lambda *args, **kwargs: base_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "override_gap.csv"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-03"],
                        "precipitation": [9.0, 8.0],
                    }
                ).to_csv(csv_path, index=False)
                result = stats_module.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-03",
                    "agera_5",
                    custom_station_file=str(csv_path),
                    custom_station_variables=["precipitation"],
                )
        finally:
            stats_module._call_preprocess = orig_stats_call_preprocess

        self.assertEqual([9.0, 2.0, 8.0], result["precip"].tolist())
        self.assertEqual([24.0, 25.0, 26.0], result["tmax"].tolist())

    def test_get_climate_data_applies_custom_station_temp_override_only(self):
        stats_module = importlib.import_module("climate_tookit.climate_statistics.statistics")
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=2, freq="D"),
                "precipitation": [1.0, 2.0],
                "max_temperature": [24.0, 25.0],
                "min_temperature": [14.0, 15.0],
            }
        )
        orig_stats_call_preprocess = stats_module._call_preprocess
        stats_module._call_preprocess = lambda *args, **kwargs: base_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "override_temp.csv"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-02"],
                        "tmax": [30.0, 31.0],
                        "tmin": [20.0, 21.0],
                    }
                ).to_csv(csv_path, index=False)
                result = stats_module.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-02",
                    "agera_5",
                    custom_station_file=str(csv_path),
                    custom_station_variables=["tmax", "tmin"],
                    custom_temp_unit="c",
                )
        finally:
            stats_module._call_preprocess = orig_stats_call_preprocess

        self.assertEqual([1.0, 2.0], result["precip"].tolist())
        self.assertEqual([30.0, 31.0], result["tmax"].tolist())
        self.assertEqual([20.0, 21.0], result["tmin"].tolist())
        summary = result.attrs.get("custom_station_override_summary", [])
        self.assertEqual("tmax", summary[0]["variable"])
        self.assertEqual(0, summary[0]["fallback_days"])

    def test_get_climate_data_skips_custom_override_when_no_overlap(self):
        stats_module = importlib.import_module("climate_tookit.climate_statistics.statistics")
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-03-01", periods=2, freq="D"),
                "precipitation": [1.0, 2.0],
                "max_temperature": [24.0, 25.0],
                "min_temperature": [14.0, 15.0],
            }
        )
        orig_stats_call_preprocess = stats_module._call_preprocess
        stats_module._call_preprocess = lambda *args, **kwargs: base_frame.copy()
        try:
            result = stats_module.get_climate_data(
                -1.286,
                36.817,
                "2020-03-01",
                "2020-03-02",
                "agera_5",
                custom_station_file=str(GSOD_LIKE_CUSTOM_STATION_FIXTURE),
                custom_station_variables=["precipitation"],
                custom_temp_unit="f",
                custom_precip_unit="inch",
            )
        finally:
            stats_module._call_preprocess = orig_stats_call_preprocess

        self.assertEqual([1.0, 2.0], result["precip"].tolist())
        self.assertTrue(result.attrs.get("custom_station_warnings"))
        summary = result.attrs.get("custom_station_override_summary", [])
        self.assertEqual("skipped_no_overlap", summary[0]["status"])
        self.assertEqual(2, summary[0]["fallback_days"])

    def test_get_climate_data_reports_partial_custom_override_coverage(self):
        stats_module = importlib.import_module("climate_tookit.climate_statistics.statistics")
        base_frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "precipitation": [1.0, 2.0, 3.0],
                "max_temperature": [24.0, 25.0, 26.0],
                "min_temperature": [14.0, 15.0, 16.0],
            }
        )
        orig_stats_call_preprocess = stats_module._call_preprocess
        stats_module._call_preprocess = lambda *args, **kwargs: base_frame.copy()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_path = Path(tmpdir) / "override_gap.csv"
                pd.DataFrame(
                    {
                        "date": ["2020-01-01", "2020-01-03"],
                        "precipitation": [9.0, 8.0],
                    }
                ).to_csv(csv_path, index=False)
                result = stats_module.get_climate_data(
                    -1.286,
                    36.817,
                    "2020-01-01",
                    "2020-01-03",
                    "agera_5",
                    custom_station_file=str(csv_path),
                    custom_station_variables=["precipitation"],
                )
        finally:
            stats_module._call_preprocess = orig_stats_call_preprocess

        summary = result.attrs.get("custom_station_override_summary", [])
        self.assertEqual("partial_override", summary[0]["status"])
        self.assertEqual(2, summary[0]["override_days"])
        self.assertEqual(1, summary[0]["fallback_days"])

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
