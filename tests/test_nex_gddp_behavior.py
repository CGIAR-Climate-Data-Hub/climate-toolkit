from datetime import date
import sys
import types
import unittest

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

    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    ticker = types.ModuleType("matplotlib.ticker")

    class _MaxNLocator:
        def __init__(self, *args, **kwargs):
            pass

    ticker.MaxNLocator = _MaxNLocator
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)
    sys.modules.setdefault("matplotlib.ticker", ticker)


_install_test_stubs()

from climate_tookit.compare_datasets.compare_datasets import _build_nex_ensemble
from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    DownloadData,
    _normalize_scenario,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
)
from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings


class NexGddpBehaviorTests(unittest.TestCase):
    def test_normalize_scenario_accepts_catalog_aliases(self):
        self.assertEqual(_normalize_scenario("SSP3-7.0"), "ssp370")
        self.assertEqual(_normalize_scenario("ssp2-4.5"), "ssp245")
        self.assertEqual(_normalize_scenario("historical"), "historical")

    def test_download_data_rejects_historical_after_2014(self):
        with self.assertRaises(ValueError):
            DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2050, 1, 1),
                date_to_utc=date(2050, 1, 7),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="historical",
            )

    def test_download_data_rejects_future_before_2015(self):
        with self.assertRaises(ValueError):
            DownloadData(
                variables=[ClimateVariable.precipitation],
                location_coord=(-1.286, 36.817),
                date_from_utc=date(2014, 12, 31),
                date_to_utc=date(2015, 1, 7),
                settings=Settings.load(),
                source=ClimateDataset.nex_gddp,
                model="MRI-ESM2-0",
                scenario="ssp245",
            )

    def test_download_data_accepts_ssp370_future_window(self):
        client = DownloadData(
            variables=[ClimateVariable.precipitation],
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2050, 1, 1),
            date_to_utc=date(2050, 1, 7),
            settings=Settings.load(),
            source=ClimateDataset.nex_gddp,
            model="MRI-ESM2-0",
            scenario="ssp370",
        )
        self.assertEqual(client.scenario, "ssp370")

    def test_ensemble_builder_averages_matching_dates(self):
        a = pd.DataFrame(
            {
                "date": pd.to_datetime(["2050-01-01", "2050-01-02"]),
                "precipitation": [1.0, 3.0],
                "max_temperature": [20.0, 22.0],
            }
        )
        b = pd.DataFrame(
            {
                "date": pd.to_datetime(["2050-01-01", "2050-01-02"]),
                "precipitation": [5.0, 7.0],
                "max_temperature": [24.0, 26.0],
            }
        )

        ensemble = _build_nex_ensemble({"A": a, "B": b})

        self.assertEqual(list(ensemble["precipitation"]), [3.0, 5.0])
        self.assertEqual(list(ensemble["max_temperature"]), [22.0, 24.0])


if __name__ == "__main__":
    unittest.main()
