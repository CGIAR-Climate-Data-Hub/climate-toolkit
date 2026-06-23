from datetime import date
import contextlib
import io
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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

from climate_tookit.fetch_data.fetch_data import fetch_data
from climate_tookit.fetch_data.cache_inventory import save_output as save_cache_inventory_output
from climate_tookit.fetch_data.fetch_data import save_output as save_fetch_output
from climate_tookit.fetch_data.gee_xee_batch import (
    _requested_band_names as batch_requested_band_names,
)
from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.transform_data.transform_data import transform_data
from climate_tookit.fetch_data.source_data.sources.gee import DownloadData as GeeDownloadData
from climate_tookit.fetch_data.source_data.sources.gee_xee import (
    DownloadData as GeeXeeDownloadData,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    SoilVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings
from climate_tookit.fetch_data.transform_data.transform_data import validate_inputs
from climate_tookit.fetch_data.preprocess_data.preprocess_data import apply_unit_conversions

fetch_data_module = importlib.import_module("climate_tookit.fetch_data.fetch_data")
source_data_module = importlib.import_module("climate_tookit.fetch_data.source_data.source_data")


class FetchPipelineTests(unittest.TestCase):
    def test_fetch_save_output_creates_missing_output_directory(self):
        frame = pd.DataFrame({"date": pd.to_datetime(["2020-01-01"]), "value": [1.0]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "fetch.csv"
            save_fetch_output(frame, output_path, "csv")
            self.assertTrue(output_path.exists())

    def test_cache_inventory_save_output_creates_missing_output_directory(self):
        frame = pd.DataFrame({"dataset": ["nex_gddp"], "entries": [1]})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "results" / "cache_inventory.json"
            save_cache_inventory_output(frame, output_path, "json")
            self.assertTrue(output_path.exists())

    def test_apply_unit_conversions_is_silent_while_still_converting(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "max_temperature": [300.15, 301.15],
                "min_temperature": [290.15, 291.15],
                "precipitation": [0.005, 0.010],
            }
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            converted = apply_unit_conversions(raw_df, source="era_5", verbose=True)

        self.assertEqual("", buf.getvalue())
        self.assertAlmostEqual(27.0, converted.loc[0, "max_temperature"], places=6)
        self.assertAlmostEqual(17.0, converted.loc[0, "min_temperature"], places=6)
        self.assertAlmostEqual(5.0, converted.loc[0, "precipitation"], places=6)

    def test_apply_unit_conversions_scales_imerg_daily_depth(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precipitation": [10.0, 4.0],
            }
        )

        converted = apply_unit_conversions(raw_df, source="imerg", verbose=True)

        self.assertAlmostEqual(5.0, converted.loc[0, "precipitation"], places=6)
        self.assertAlmostEqual(2.0, converted.loc[1, "precipitation"], places=6)

    def test_apply_unit_conversions_for_gsod(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "precipitation": [1.0],
                "max_temperature": [86.0],
                "min_temperature": [68.0],
                "mean_temperature": [77.0],
                "wind_speed": [10.0],
            }
        )

        converted = apply_unit_conversions(raw_df, source="gsod", verbose=True)

        self.assertAlmostEqual(25.4, converted.loc[0, "precipitation"], places=6)
        self.assertAlmostEqual(30.0, converted.loc[0, "max_temperature"], places=6)
        self.assertAlmostEqual(20.0, converted.loc[0, "min_temperature"], places=6)
        self.assertAlmostEqual(25.0, converted.loc[0, "mean_temperature"], places=6)
        self.assertAlmostEqual(5.14444, converted.loc[0, "wind_speed"], places=5)

    def test_era5_wind_speed_uses_both_components_and_returns_scalar_speed(self):
        settings = Settings.load()
        downloader = GeeDownloadData(
            variables=[ClimateVariable.wind_speed],
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=settings,
            source=ClimateDataset.era_5,
        )

        raw_df = pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-01-02"],
                "u_component_of_wind_10m": [3.0, -5.0],
                "v_component_of_wind_10m": [4.0, 12.0],
            }
        )

        with mock.patch.object(
            downloader,
            "get_gee_data_daily",
            return_value=raw_df,
        ) as mocked_fetch:
            result = downloader.download_variables()

        self.assertEqual(
            mocked_fetch.call_args.kwargs["bands"],
            ["u_component_of_wind_10m", "v_component_of_wind_10m"],
        )
        self.assertEqual(list(result.columns), ["date", "wind_speed"])
        self.assertAlmostEqual(5.0, result.loc[0, "wind_speed"], places=6)
        self.assertAlmostEqual(13.0, result.loc[1, "wind_speed"], places=6)

    def test_era5_batch_requested_bands_include_both_wind_components(self):
        settings = Settings.load()
        data_settings = settings.era_5

        bands = batch_requested_band_names(
            ClimateDataset.era_5,
            data_settings,
            [ClimateVariable.wind_speed],
        )

        self.assertEqual(
            bands,
            ["u_component_of_wind_10m", "v_component_of_wind_10m"],
        )

    def test_agera5_humidity_and_wind_are_derived_when_requested(self):
        settings = Settings.load()
        downloader = GeeDownloadData(
            variables=[ClimateVariable.humidity, ClimateVariable.wind_speed, ClimateVariable.solar_radiation],
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=settings,
            source=ClimateDataset.agera_5,
        )

        raw_df = pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-01-02"],
                "dewpoint_temperature_2m": [290.15, 289.15],
                "temperature_2m": [293.15, 295.15],
                "u_component_of_wind_10m": [3.0, -5.0],
                "v_component_of_wind_10m": [4.0, 12.0],
                "surface_solar_radiation_downwards_sum": [86400.0, 172800.0],
            }
        )

        with mock.patch.object(
            downloader,
            "get_gee_data_daily",
            return_value=raw_df,
        ) as mocked_fetch:
            result = downloader.download_variables()

        self.assertEqual(
            mocked_fetch.call_args.kwargs["bands"],
            [
                "dewpoint_temperature_2m",
                "temperature_2m",
                "u_component_of_wind_10m",
                "v_component_of_wind_10m",
                "surface_solar_radiation_downwards_sum",
            ],
        )
        self.assertEqual(
            list(result.columns),
            ["date", "humidity", "wind_speed", "surface_solar_radiation_downwards_sum"],
        )
        self.assertAlmostEqual(5.0, result.loc[0, "wind_speed"], places=6)
        self.assertTrue(0.0 <= result.loc[0, "humidity"] <= 100.0)
        self.assertAlmostEqual(1.0, result.loc[0, "surface_solar_radiation_downwards_sum"], places=6)

    def test_agera5_batch_requested_bands_include_humidity_wind_and_solar_inputs(self):
        settings = Settings.load()
        data_settings = settings.agera_5

        bands = batch_requested_band_names(
            ClimateDataset.agera_5,
            data_settings,
            [ClimateVariable.humidity, ClimateVariable.wind_speed, ClimateVariable.solar_radiation],
        )

        self.assertEqual(
            bands,
            [
                "dewpoint_temperature_2m",
                "temperature_2m",
                "u_component_of_wind_10m",
                "v_component_of_wind_10m",
                "surface_solar_radiation_downwards_sum",
            ],
        )

    def test_validate_inputs_rejects_bad_nex_model_and_scenario(self):
        errors = validate_inputs(
            source="nex_gddp",
            lat=-1.286,
            lon=36.817,
            date_from=date(2050, 1, 1),
            date_to=date(2049, 12, 31),
            model="BAD-MODEL",
            scenario="ssp999",
        )

        self.assertTrue(any("Start date must be before end date" in err for err in errors))
        self.assertTrue(any("Invalid model" in err for err in errors))
        self.assertTrue(any("Invalid scenario" in err for err in errors))

    def test_validate_inputs_accepts_historical_and_ssp370(self):
        historical_errors = validate_inputs(
            source="nex_gddp",
            lat=-1.286,
            lon=36.817,
            date_from=date(1991, 1, 1),
            date_to=date(1991, 1, 7),
            model="MRI-ESM2-0",
            scenario="historical",
        )
        ssp370_errors = validate_inputs(
            source="nex_gddp",
            lat=-1.286,
            lon=36.817,
            date_from=date(2050, 1, 1),
            date_to=date(2050, 1, 7),
            model="MRI-ESM2-0",
            scenario="ssp370",
        )

        self.assertEqual(historical_errors, [])
        self.assertEqual(ssp370_errors, [])

    def test_validate_inputs_rejects_era5_window_after_current_coverage(self):
        errors = validate_inputs(
            source="era_5",
            lat=-1.286,
            lon=36.817,
            date_from=date(2020, 12, 1),
            date_to=date(2020, 12, 31),
            model=None,
            scenario=None,
        )

        self.assertTrue(
            any("outside current coverage" in err and "2020-07-09" in err for err in errors)
        )

    def test_fetch_data_rejects_many_site_era5_window_after_current_coverage(self):
        with self.assertRaisesRegex(ValueError, "outside current coverage"):
            fetch_data(
                source="era_5",
                sites=[{"site": "Nairobi", "lat": -1.286, "lon": 36.817}],
                date_from=date(2020, 12, 1),
                date_to=date(2020, 12, 31),
                stage="preprocessed",
            )

    def test_source_data_uses_real_nex_downloader(self):
        calls = []

        class RealNexStub:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def download_variables(self):
                return pd.DataFrame()

        with mock.patch(
            "climate_tookit.fetch_data.source_data.source_data.DownloadNEXGDDP",
            RealNexStub,
        ):
            src = SourceData(
                location_coord=(-1.286, 36.817),
                variables=[ClimateVariable.precipitation],
                source=ClimateDataset.nex_gddp,
                date_from_utc=date(2050, 1, 1),
                date_to_utc=date(2050, 1, 2),
                settings=Settings.load(),
                model="MRI-ESM2-0",
                scenario="ssp245",
            )

        self.assertEqual(len(calls), 1)
        self.assertIsInstance(src.client, RealNexStub)

    def test_era5_dispatches_to_authoritative_era5_adapter(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.era_5,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )

        self.assertEqual(
            type(src.client).__module__,
            "climate_tookit.fetch_data.source_data.sources.era_5",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

    def test_agera5_dispatches_to_authoritative_agera5_adapter(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.agera_5,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )

        self.assertEqual(
            type(src.client).__module__,
            "climate_tookit.fetch_data.source_data.sources.agera_5",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

    def test_chirps_v3_daily_rnl_dispatches_to_gee_adapter(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.chirps_v3_daily_rnl,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )

        self.assertEqual(
            type(src.client).__module__,
            "climate_tookit.fetch_data.source_data.sources.gee_xee",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

    def test_imerg_dispatches_to_gee_xee_adapter(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[ClimateVariable.precipitation],
            source=ClimateDataset.imerg,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )

        self.assertEqual(
            type(src.client).__module__,
            "climate_tookit.fetch_data.source_data.sources.gee_xee",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

    def test_nasa_power_dispatches_verbose_and_cache_settings(self):
        calls = []

        class NASAStub:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def download_variables(self):
                return pd.DataFrame()

        with mock.patch(
            "climate_tookit.fetch_data.source_data.source_data.DownloadNASA",
            NASAStub,
        ):
            src = SourceData(
                location_coord=(-1.286, 36.817),
                variables=[ClimateVariable.precipitation],
                source=ClimateDataset.nasa_power,
                date_from_utc=date(2020, 1, 1),
                date_to_utc=date(2020, 1, 2),
                settings=Settings.load(),
                verbose=False,
                cache_dir="outputs/cache/power",
                refresh_cache=True,
            )

        self.assertIsInstance(src.client, NASAStub)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["verbose"])
        self.assertEqual("outputs/cache/power", calls[0]["cache_dir"])
        self.assertTrue(calls[0]["refresh_cache"])

    def test_soil_grid_stays_on_direct_gee_adapter(self):
        src = SourceData(
            location_coord=(-1.286, 36.817),
            variables=[SoilVariable.bulk_density],
            source=ClimateDataset.soil_grid,
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
        )

        self.assertEqual(
            type(src.client).__module__,
            "climate_tookit.fetch_data.source_data.sources.gee",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

    def test_single_site_xee_adapter_strips_site_identity_columns(self):
        downloader = GeeXeeDownloadData(
            variables=[ClimateVariable.precipitation],
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 2),
            settings=Settings.load(),
            source=ClimateDataset.chirps,
        )

        raw_df = pd.DataFrame(
            {
                "site": ["site", "site"],
                "lat": [-1.286, -1.286],
                "lon": [36.817, 36.817],
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precipitation": [0.0, 1.2],
            }
        )

        with mock.patch(
            "climate_tookit.fetch_data.gee_xee_batch.run_gee_xee_batch_extraction",
            return_value=(raw_df, pd.DataFrame(), pd.DataFrame()),
        ):
            result = downloader.download_variables()

        self.assertEqual(list(result.columns), ["date", "precipitation"])

    def test_nex_pipeline_stages_return_expected_columns(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2050-01-01", "2050-01-02", "2050-01-03", "2050-01-04"]
                ),
                "pr": [1.0, 0.0, 2.5, 3.1],
                "tasmax": [25.0, 26.0, 27.0, 28.0],
                "tasmin": [14.0, 15.0, 16.0, 17.0],
            }
        )

        kwargs = dict(
            source="nex_gddp",
            location_coord=(-1.286, 36.817),
            date_from=date(2050, 1, 1),
            date_to=date(2050, 1, 4),
            model="MRI-ESM2-0",
            scenario="ssp245",
        )

        with mock.patch.object(SourceData, "download", return_value=raw_df):
            raw_stage = fetch_data(stage="raw", **kwargs)
            transformed_stage = fetch_data(stage="transformed", **kwargs)
            preprocessed_stage = fetch_data(stage="preprocessed", **kwargs)

        self.assertEqual(list(raw_stage.columns), ["date", "pr", "tasmax", "tasmin"])
        self.assertEqual(
            list(transformed_stage.columns),
            ["date", "precipitation", "max_temperature", "min_temperature"],
        )
        self.assertEqual(
            list(preprocessed_stage.columns),
            ["date", "precipitation", "max_temperature", "min_temperature"],
        )
        self.assertEqual(len(preprocessed_stage), 4)
        self.assertEqual(str(preprocessed_stage["date"].dtype), "datetime64[ns]")

    def test_invalid_stage_raises(self):
        with self.assertRaises(ValueError):
            fetch_data(
                source="nex_gddp",
                location_coord=(-1.286, 36.817),
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 2),
                model="MRI-ESM2-0",
                scenario="ssp245",
                stage="bad-stage",
            )

    def test_fetch_data_routes_many_site_nex_to_batch_api(self):
        batch_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2050-01-01"])})

        with mock.patch(
            "climate_tookit.fetch_data.fetch_data.fetch_nex_gddp_batch_data",
            return_value=(batch_df, pd.DataFrame(), pd.DataFrame()),
        ) as batch_mock:
            result = fetch_data(
                source="nex_gddp",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 1),
                model="MRI-ESM2-0",
                scenario="ssp245",
                stage="raw",
            )

        self.assertIs(result, batch_df)
        batch_mock.assert_called_once()

    def test_fetch_data_routes_many_site_historical_gee_to_xee_batch_api(self):
        batch_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2020-01-01"])})

        with mock.patch(
            "climate_tookit.fetch_data.fetch_data.fetch_gee_xee_batch_data",
            return_value=(batch_df, pd.DataFrame(), pd.DataFrame()),
        ) as batch_mock:
            result = fetch_data(
                source="chirps",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
                stage="raw",
            )

        self.assertIs(result, batch_df)
        batch_mock.assert_called_once()

    def test_fetch_data_routes_many_site_chirps_v3_daily_rnl_to_xee_batch_api(self):
        batch_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2020-01-01"])})

        with mock.patch(
            "climate_tookit.fetch_data.fetch_data.fetch_gee_xee_batch_data",
            return_value=(batch_df, pd.DataFrame(), pd.DataFrame()),
        ) as batch_mock:
            result = fetch_data(
                source="chirps_v3_daily_rnl",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
                stage="raw",
            )

        self.assertIs(result, batch_df)
        batch_mock.assert_called_once()

    def test_fetch_data_routes_many_site_imerg_to_xee_batch_api(self):
        batch_df = pd.DataFrame({"site": ["Nairobi"], "date": pd.to_datetime(["2020-01-01"])})

        with mock.patch(
            "climate_tookit.fetch_data.fetch_data.fetch_gee_xee_batch_data",
            return_value=(batch_df, pd.DataFrame(), pd.DataFrame()),
        ) as batch_mock:
            result = fetch_data(
                source="imerg",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
                stage="raw",
                variables=[ClimateVariable.precipitation],
            )

        self.assertIs(result, batch_df)
        batch_mock.assert_called_once()

    def test_fetch_data_rejects_unsupported_many_site_source(self):
        with self.assertRaises(ValueError):
            fetch_data(
                source="nasa_power",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
            )

    def test_transform_data_keeps_nasa_power_humidity_wind_and_solar_columns(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "precipitation": [1.5],
                "max_temperature": [28.0],
                "min_temperature": [18.0],
                "mean_temperature": [23.0],
                "humidity": [65.0],
                "wind_speed": [2.1],
                "solar_radiation": [210.0],
            }
        )

        class _FakeSourceData:
            def __init__(self, **kwargs):
                pass

            def download(self):
                return raw_df.copy()

        with mock.patch(
            "climate_tookit.fetch_data.transform_data.transform_data.SourceData",
            _FakeSourceData,
        ):
            result = transform_data(
                source="nasa_power",
                location_coord=(-1.286, 36.817),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                    ClimateVariable.mean_temperature,
                    ClimateVariable.humidity,
                    ClimateVariable.wind_speed,
                    ClimateVariable.solar_radiation,
                ],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
                verbose=False,
            )

        self.assertEqual(
            list(result.columns),
            [
                "date",
                "precipitation",
                "max_temperature",
                "min_temperature",
                "mean_temperature",
                "humidity",
                "wind_speed",
                "solar_radiation",
            ],
        )

    def test_transform_data_maps_nex_gddp_hurs_to_humidity(self):
        raw_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2050-01-01"]),
                "pr": [1.5],
                "tasmax": [28.0],
                "tasmin": [18.0],
                "hurs": [72.0],
            }
        )

        class _FakeSourceData:
            def __init__(self, **kwargs):
                pass

            def download(self):
                return raw_df.copy()

        with mock.patch(
            "climate_tookit.fetch_data.transform_data.transform_data.SourceData",
            _FakeSourceData,
        ):
            result = transform_data(
                source="nex_gddp",
                location_coord=(-1.286, 36.817),
                variables=[
                    ClimateVariable.precipitation,
                    ClimateVariable.max_temperature,
                    ClimateVariable.min_temperature,
                    ClimateVariable.humidity,
                ],
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 1),
                model="MRI-ESM2-0",
                scenario="ssp245",
                verbose=False,
            )

        self.assertEqual(
            list(result.columns),
            ["date", "precipitation", "max_temperature", "min_temperature", "humidity"],
        )

    def test_fetch_data_requires_location_for_single_site_mode(self):
        with self.assertRaises(ValueError):
            fetch_data(
                source="chirps",
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
            )

    def test_main_prints_simple_message_when_ee_project_id_missing(self):
        argv = [
            "fetch_data.py",
            "--source",
            "chirps",
            "--site",
            "Nairobi,-1.286,36.817",
            "--start",
            "2020-01-01",
            "--end",
            "2020-01-02",
        ]
        buf = io.StringIO()
        with mock.patch.object(
            fetch_data_module,
            "fetch_data",
            side_effect=ValueError(
                "Earth Engine project ID is required. Pass ee_project_id or set one of "
                "GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or EE_PROJECT_ID."
            ),
        ), mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            exit_code = fetch_data_module.main()

        output = buf.getvalue()
        self.assertEqual(1, exit_code)
        self.assertIn("Earth Engine project ID missing.", output)
        self.assertIn("GCP_PROJECT_ID", output)

    def test_source_data_main_prints_full_table_for_small_extract(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precipitation": [1.0, 2.0],
            }
        )

        class _FakeSourceData:
            def __init__(self, **kwargs):
                pass

            def download(self):
                return frame.copy()

        argv = [
            "source_data.py",
            "--source",
            "chirps_v2",
            "--variables",
            "precipitation",
            "--from",
            "2020-01-01",
            "--to",
            "2020-01-02",
            "--lon",
            "36.817",
            "--lat",
            "-1.286",
        ]
        buf = io.StringIO()
        with mock.patch.object(
            source_data_module,
            "SourceData",
            _FakeSourceData,
        ), mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            exit_code = source_data_module.main()

        output = buf.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("2020-01-01", output)
        self.assertIn("precipitation", output)
        self.assertNotIn("Retrieved 2 row(s)", output)

    def test_source_data_main_prints_compact_summary_for_large_extract(self):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", "2020-12-31", freq="D"),
                "precipitation": range(366),
            }
        )

        class _FakeSourceData:
            def __init__(self, **kwargs):
                pass

            def download(self):
                return frame.copy()

        argv = [
            "source_data.py",
            "--source",
            "chirps_v2",
            "--variables",
            "precipitation",
            "--from",
            "2020-01-01",
            "--to",
            "2020-12-31",
            "--lon",
            "36.817",
            "--lat",
            "-1.286",
        ]
        buf = io.StringIO()
        with mock.patch.object(
            source_data_module,
            "SourceData",
            _FakeSourceData,
        ), mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            exit_code = source_data_module.main()

        output = buf.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn("Retrieved 366 row(s) across 2 column(s).", output)
        self.assertIn("Date range: 2020-01-01 .. 2020-12-31", output)
        self.assertIn("Preview (first 5 rows):", output)
        self.assertIn("Preview (last 5 rows):", output)
        self.assertIn("Use --format csv --output <path>", output)

    def test_source_data_main_warns_when_source_cannot_supply_requested_variables(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precipitation": [1.0, 2.0],
            }
        )

        class _FakeSourceData:
            def __init__(self, **kwargs):
                pass

            def download(self):
                return frame.copy()

        argv = [
            "source_data.py",
            "--source",
            "chirps_v2",
            "--variables",
            "precipitation,max_temperature,humidity",
            "--from",
            "2020-01-01",
            "--to",
            "2020-01-02",
            "--lon",
            "36.817",
            "--lat",
            "-1.286",
        ]
        buf = io.StringIO()
        with mock.patch.object(
            source_data_module,
            "SourceData",
            _FakeSourceData,
        ), mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            exit_code = source_data_module.main()

        output = buf.getvalue()
        self.assertEqual(0, exit_code)
        self.assertIn(
            "Warning: Source 'chirps_v2' did not return requested variables: "
            "max_temperature, humidity",
            output,
        )


if __name__ == "__main__":
    unittest.main()
