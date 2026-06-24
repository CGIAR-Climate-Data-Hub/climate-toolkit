import unittest

import pandas as pd

from climate_tookit.climatology import compute_daily_vpd, summarize_vpd_period


class VpdTests(unittest.TestCase):
    def test_compute_daily_vpd_uses_relative_humidity_path(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "tmax": [30.0, 32.0],
                "tmin": [20.0, 22.0],
                "humidity": [50.0, 80.0],
            }
        )

        result = compute_daily_vpd(frame)

        self.assertIn("vpd_kpa", result.columns)
        self.assertAlmostEqual(25.0, result.loc[0, "temperature_c"], places=6)
        self.assertGreater(result.loc[0, "vpd_kpa"], result.loc[1, "vpd_kpa"])
        self.assertEqual("relative_humidity", result.attrs["vpd_metadata"]["path"])
        self.assertEqual("derived_from_tmax_tmin", result.attrs["vpd_metadata"]["temperature_source"])

    def test_compute_daily_vpd_uses_dewpoint_path(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "mean_temperature": [25.0, 25.0],
                "dewpoint_temperature": [25.0, 20.0],
            }
        )

        result = compute_daily_vpd(frame, method="dewpoint")

        self.assertAlmostEqual(0.0, result.loc[0, "vpd_kpa"], places=6)
        self.assertGreater(result.loc[1, "vpd_kpa"], 0.0)
        self.assertEqual("dewpoint", result.attrs["vpd_metadata"]["path"])

    def test_compute_daily_vpd_auto_requires_moisture_input(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "tmax": [32.0],
                "tmin": [20.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "humidity or dewpoint inputs"):
            compute_daily_vpd(frame)

    def test_summarize_vpd_period_counts_thresholds(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
                "tmax": [30.0, 34.0, 28.0],
                "tmin": [20.0, 24.0, 18.0],
                "humidity": [90.0, 35.0, 75.0],
            }
        )

        result = summarize_vpd_period(frame, thresholds_kpa=(1.0,))

        self.assertIn("mean_vpd_kpa", result)
        self.assertIn("max_vpd_kpa", result)
        self.assertEqual("relative_humidity", result["method"])
        self.assertIn("days_above_1p0_kpa", result)
        self.assertGreaterEqual(result["days_above_1p0_kpa"], 1)


if __name__ == "__main__":
    unittest.main()
