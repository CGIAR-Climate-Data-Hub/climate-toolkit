import unittest

import pandas as pd

from climate_tookit.climatology import (
    compute_daily_humidex,
    describe_human_heat_method,
    describe_human_heat_source_support,
    summarize_humidex_period,
)


class HumanHeatStressTests(unittest.TestCase):
    def test_compute_daily_humidex_uses_dewpoint_path_when_available(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "mean_temperature": [30.0, 30.0],
                "dewpoint_temperature": [24.0, 18.0],
            }
        )

        result = compute_daily_humidex(frame)

        self.assertIn("humidex", result.columns)
        self.assertGreater(result.loc[0, "humidex"], result.loc[1, "humidex"])
        self.assertEqual("dewpoint", result.attrs["human_heat_metadata"]["path"])

    def test_compute_daily_humidex_uses_relative_humidity_path(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "tmax": [32.0, 32.0],
                "tmin": [24.0, 24.0],
                "humidity": [80.0, 40.0],
            }
        )

        result = compute_daily_humidex(frame)

        self.assertAlmostEqual(28.0, result.loc[0, "temperature_c"], places=6)
        self.assertGreater(result.loc[0, "humidex"], result.loc[1, "humidex"])
        self.assertEqual("relative_humidity", result.attrs["human_heat_metadata"]["path"])
        self.assertEqual("derived_from_tmax_tmin", result.attrs["human_heat_metadata"]["temperature_source"])

    def test_compute_daily_humidex_auto_requires_moisture_input(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "tmax": [32.0],
                "tmin": [24.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "humidity or dewpoint inputs"):
            compute_daily_humidex(frame)

    def test_summarize_humidex_period_reports_mean_and_max(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
                "mean_temperature": [30.0, 31.0, 29.0],
                "humidity": [70.0, 75.0, 65.0],
            }
        )

        result = summarize_humidex_period(frame)

        self.assertIn("mean_humidex", result)
        self.assertIn("max_humidex", result)
        self.assertEqual("relative_humidity", result["method"])
        self.assertEqual("continuous_metric_only", result["phase1_scope"])

    def test_describe_human_heat_source_support_tracks_future_gap(self):
        support = describe_human_heat_source_support()

        self.assertIn("agera_5", support)
        self.assertIn("nex_gddp", support)
        self.assertIn("conditionally supported", support["nex_gddp"])
        self.assertIn("not supported", support["chirps_v3_daily_rnl"])

    def test_describe_human_heat_method_exposes_metric_choice(self):
        method = describe_human_heat_method()

        self.assertEqual("humidex", method["metric"])
        self.assertEqual("xclim", method["backend"])
        self.assertEqual("continuous_metric_only", method["phase1_scope"])
        self.assertIn("heat_index", method["candidate_review"])
        self.assertIn("utci", method["candidate_review"])
        self.assertIn("wbgt", method["candidate_review"])
        self.assertIn("nasa_power", method["source_support"])


if __name__ == "__main__":
    unittest.main()
