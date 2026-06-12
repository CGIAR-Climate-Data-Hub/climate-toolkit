from datetime import date
import contextlib
import io
import importlib
import sys
import types
import unittest
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
from climate_tookit.fetch_data.source_data.source_data import SourceData
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings
from climate_tookit.fetch_data.transform_data.transform_data import validate_inputs
from climate_tookit.fetch_data.preprocess_data.preprocess_data import apply_unit_conversions

fetch_data_module = importlib.import_module("climate_tookit.fetch_data.fetch_data")


class FetchPipelineTests(unittest.TestCase):
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
            "climate_tookit.fetch_data.source_data.sources.gee",
        )
        self.assertEqual(type(src.client).__name__, "DownloadData")

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

    def test_fetch_data_rejects_unsupported_many_site_source(self):
        with self.assertRaises(ValueError):
            fetch_data(
                source="nasa_power",
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2020, 1, 1),
                date_to=date(2020, 1, 1),
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


if __name__ == "__main__":
    unittest.main()
