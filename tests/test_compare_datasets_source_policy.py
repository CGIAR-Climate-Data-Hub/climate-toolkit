import io
import json
import unittest
from unittest import mock
import pandas as pd

from climate_tookit.compare_datasets.compare_datasets import (
    _validate_source_selection,
    compare_sources,
    main,
    print_report,
)


class CompareDatasetsSourcePolicyTests(unittest.TestCase):
    @staticmethod
    def _fake_dataset():
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "precipitation": [1.0, 2.0],
                "max_temperature": [25.0, 26.0],
                "min_temperature": [15.0, 16.0],
            }
        )

    def test_validate_source_selection_rejects_unknown_source(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_source_selection(["bogus_source"])

        self.assertIn("Unknown source(s)", str(ctx.exception))

    def test_validate_source_selection_rejects_mixed_nex_and_historical_sources(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_source_selection(["era_5", "nex_gddp"])

        self.assertIn("nex_gddp must be run on its own", str(ctx.exception))

    def test_compare_sources_rejects_mixed_nex_and_other_sources(self):
        with self.assertRaises(ValueError) as ctx:
            compare_sources(
                sources=["nex_gddp", "chirps"],
                lat=-1.286,
                lon=36.817,
                start="2015-01-01",
                end="2015-01-10",
            )

        self.assertIn("nex_gddp must be run on its own", str(ctx.exception))

    def test_compare_sources_rejects_unknown_source(self):
        with self.assertRaises(ValueError) as ctx:
            compare_sources(
                sources=["bogus_source"],
                lat=-1.286,
                lon=36.817,
                start="2020-01-01",
                end="2020-01-10",
            )

        self.assertIn("Unknown source(s)", str(ctx.exception))

    def test_compare_sources_accepts_auto_source(self):
        fake_df = self._fake_dataset()
        with mock.patch(
            "climate_tookit.compare_datasets.compare_datasets._fetch_source",
            return_value=fake_df,
        ) as fetch_mock, mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.export_data",
        ):
            results = compare_sources(
                sources=["auto"],
                lat=-1.286,
                lon=36.817,
                start="2020-01-01",
                end="2020-01-02",
            )

        self.assertIn("auto", results)
        fetch_mock.assert_called_once()

    def test_compare_sources_accepts_paired_source_with_explicit_partners(self):
        fake_df = self._fake_dataset()
        with mock.patch(
            "climate_tookit.compare_datasets.compare_datasets._fetch_source",
            return_value=fake_df,
        ) as fetch_mock, mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.export_data",
        ):
            results = compare_sources(
                sources=["paired"],
                lat=-1.286,
                lon=36.817,
                start="2020-01-01",
                end="2020-01-02",
                precip_source="chirps_v3_daily_rnl",
                temp_source="agera_5",
            )

        self.assertIn("paired_chirps_v3_daily_rnl_plus_agera_5", results)
        fetch_mock.assert_called_once()

    def test_main_rejects_mixed_nex_and_other_sources(self):
        argv = [
            "compare_datasets.py",
            "--sources",
            "nex_gddp",
            "chirps",
            "--lat",
            "-1.286",
            "--lon",
            "36.817",
            "--start",
            "2015-01-01",
            "--end",
            "2015-01-10",
        ]

        with mock.patch("sys.argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)

    def test_print_report_keeps_tables_when_plot_step_fails(self):
        results = {"agera_5": self._fake_dataset()}

        with mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_annual_timeseries",
            side_effect=RuntimeError("plot boom"),
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_monthly_climatology",
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_multisource_annual",
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_multisource_monthly_climatology",
        ):
            report = print_report(results, output_dir="./outputs")

        self.assertIn("precipitation", report["annual_timeseries"])
        self.assertIsNotNone(report["plot_failures"])
        self.assertEqual(report["plot_failures"][0]["step"], "annual_timeseries")
        self.assertEqual(report["plot_failures"][0]["source"], "agera_5")

    def test_main_json_output_survives_plot_failure(self):
        fake_results = {"agera_5": self._fake_dataset()}
        argv = [
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
            "--format",
            "json",
        ]

        with mock.patch("sys.argv", argv), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.compare_sources",
            return_value=fake_results,
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_annual_timeseries",
            side_effect=RuntimeError("plot boom"),
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_monthly_climatology",
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_multisource_annual",
        ), mock.patch(
            "climate_tookit.compare_datasets.compare_datasets.plot_multisource_monthly_climatology",
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            exit_code = main()

        output = stdout.getvalue()
        json_start = output.rfind('{\n  "annual_timeseries"')
        self.assertNotEqual(json_start, -1)
        payload = json.loads(output[json_start:])
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["plot_failures"][0]["step"], "annual_timeseries")
        self.assertIn("datasets", payload)
        self.assertIn("agera_5", payload["datasets"])

    def test_main_rejects_paired_without_both_partner_sources(self):
        argv = [
            "compare_datasets.py",
            "--sources",
            "paired",
            "--lat",
            "-1.286",
            "--lon",
            "36.817",
            "--start",
            "2020-01-01",
            "--end",
            "2020-01-10",
            "--precip-source",
            "chirps_v3_daily_rnl",
        ]

        with mock.patch("sys.argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
