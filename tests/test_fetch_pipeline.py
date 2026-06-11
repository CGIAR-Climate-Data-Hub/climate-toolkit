from datetime import date
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


class FetchPipelineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
