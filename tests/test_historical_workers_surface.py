import sys
import unittest
import importlib
from unittest.mock import MagicMock, patch

import pandas as pd

from climate_tookit.calculate_hazards import hazards
from climate_tookit.climate_statistics import statistics
from climate_tookit.climatology import long_term_climatology as ltc
from climate_tookit.compare_datasets import compare_datasets
from climate_tookit.compare_periods import periods
from climate_tookit.fetch_data.source_data import source_data as source_data_module
from climate_tookit.season_analysis import seasons
from climate_tookit.weather_station import compare as station_compare

preprocess_module = importlib.import_module(
    "climate_tookit.fetch_data.preprocess_data.preprocess_data"
)
transform_module = importlib.import_module(
    "climate_tookit.fetch_data.transform_data.transform_data"
)


class HistoricalWorkersSurfaceTests(unittest.TestCase):
    def test_source_data_main_passes_workers(self):
        client = MagicMock()
        client.download.return_value = pd.DataFrame({"date": []})

        with patch.object(
            sys,
            "argv",
            [
                "source_data.py",
                "--lat",
                "-1.286",
                "--lon",
                "36.817",
                "--source",
                "agera_5",
                "--variables",
                "precipitation",
                "--from",
                "2020-01-01",
                "--to",
                "2020-01-02",
                "--workers",
                "3",
            ],
        ), patch.object(source_data_module, "SourceData", return_value=client) as source_mock:
            rc = source_data_module.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, source_mock.call_args.kwargs["workers"])

    def test_transform_function_passes_workers(self):
        client = MagicMock()
        client.download.return_value = pd.DataFrame({"date": pd.to_datetime(["2020-01-01"])})
        with patch.object(transform_module, "SourceData", return_value=client) as source_mock, patch.object(
            transform_module,
            "load_variable_mappings",
            return_value={"agera_5": {"date": "date"}},
        ):
            transform_module.transform_data(
                source="agera_5",
                location_coord=(-1.286, 36.817),
                date_from=pd.Timestamp("2020-01-01").date(),
                date_to=pd.Timestamp("2020-01-02").date(),
                workers=3,
            )

        self.assertEqual(3, source_mock.call_args.kwargs["workers"])

    def test_preprocess_function_passes_workers(self):
        with patch.object(
            preprocess_module,
            "transform_data",
            return_value=pd.DataFrame({"date": pd.to_datetime(["2020-01-01"])}),
        ) as transform_mock:
            preprocess_module.preprocess_data(
                source="agera_5",
                location_coord=(-1.286, 36.817),
                date_from=pd.Timestamp("2020-01-01").date(),
                date_to=pd.Timestamp("2020-01-02").date(),
                workers=3,
            )

        self.assertEqual(3, transform_mock.call_args.kwargs["workers"])

    def test_seasons_main_passes_workers(self):
        with patch.object(
            sys,
            "argv",
            [
                "seasons.py",
                "--location=-1.286,36.817",
                "--start-year",
                "2020",
                "--end-year",
                "2020",
                "--source",
                "agera_5",
                "--fixed-season",
                "03-01:05-31",
                "--workers",
                "3",
                "--no-save",
            ],
        ), patch.object(
            seasons,
            "resolve_thi_profile",
            return_value={"label": "test"},
        ), patch.object(
            seasons,
            "fetch_and_analyze_years_fixed",
            return_value=({}, {}),
        ) as fixed_mock, patch.object(seasons, "print_summary"):
            rc = seasons.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, fixed_mock.call_args.kwargs["workers"])

    def test_statistics_main_passes_workers(self):
        with patch.object(
            sys,
            "argv",
            [
                "statistics.py",
                "--location=-1.286,36.817",
                "--start-year",
                "2020",
                "--end-year",
                "2020",
                "--source",
                "agera_5",
                "--workers",
                "3",
                "--no-save",
            ],
        ), patch.object(
            statistics,
            "analyze_climate_statistics",
            return_value={},
        ) as analyze_mock, patch.object(statistics, "_print_pandas"):
            rc = statistics.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, analyze_mock.call_args.kwargs["workers"])

    def test_compare_periods_main_passes_workers(self):
        with patch.object(
            sys,
            "argv",
            [
                "periods.py",
                "--location=-1.286,36.817",
                "--baseline-start",
                "2018",
                "--baseline-end",
                "2019",
                "--focal-year",
                "2020",
                "--source",
                "agera_5",
                "--workers",
                "3",
            ],
        ), patch.object(periods, "compare", return_value={}) as compare_mock, patch.object(
            periods,
            "print_report",
        ):
            rc = periods.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, compare_mock.call_args.kwargs["workers"])

    def test_compare_datasets_main_passes_workers(self):
        results = {"agera_5": pd.DataFrame({"date": pd.to_datetime(["2020-01-01"])})}
        with patch.object(
            sys,
            "argv",
            [
                "compare_datasets.py",
                "--sources",
                "agera_5",
                "--lat",
                "-1.286",
                "--lon",
                "36.817",
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-02",
                "--workers",
                "3",
            ],
        ), patch.object(
            compare_datasets,
            "compare_sources",
            return_value=results,
        ) as compare_mock, patch.object(
            compare_datasets,
            "print_report",
            return_value={},
        ):
            rc = compare_datasets.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, compare_mock.call_args.kwargs["workers"])

    def test_hazards_main_passes_workers(self):
        with patch.object(
            sys,
            "argv",
            [
                "hazards.py",
                "maize",
                "--location=-1.286,36.817",
                "--date-from",
                "2020-01-01",
                "--date-to",
                "2020-12-31",
                "--workers",
                "3",
            ],
        ), patch.object(
            hazards,
            "calculate_hazards",
            return_value={},
        ) as hazards_mock, patch.object(hazards, "print_hazard_results"):
            rc = hazards.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, hazards_mock.call_args.kwargs["workers"])

    def test_station_compare_main_passes_workers(self):
        with patch.object(
            sys,
            "argv",
            [
                "compare.py",
                "--station-source",
                "ghcn_daily",
                "--station-lat",
                "-1.286",
                "--station-lon",
                "36.817",
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-10",
                "--grid-source",
                "agera_5",
                "--workers",
                "3",
            ],
        ), patch.object(
            station_compare,
            "compare_station_to_grids",
            return_value={"selection_mode": "auto", "station_source": "ghcn_daily", "grid_sources": ["agera_5"]},
        ) as compare_mock, patch.object(station_compare, "render_compare_report", return_value="ok"):
            rc = station_compare.main()

        self.assertEqual(0, rc)
        self.assertEqual(3, compare_mock.call_args.kwargs["workers"])

    def test_climatology_main_passes_workers(self):
        with patch.object(
            ltc,
            "_run_climatology_cli",
            return_value=0,
        ) as cli_mock:
            rc = ltc.main(
                [
                    "--location=-1.286,36.817",
                    "--start-year",
                    "1991",
                    "--end-year",
                    "2020",
                    "--source",
                    "agera_5",
                    "--workers",
                    "3",
                ]
            )

        self.assertEqual(0, rc)
        self.assertEqual(3, cli_mock.call_args.kwargs["workers"])


if __name__ == "__main__":
    unittest.main()
