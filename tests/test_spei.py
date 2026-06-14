import unittest

import pandas as pd

from climate_tookit.climatology.spei import (
    compute_monthly_spei,
    prepare_monthly_climatic_water_balance,
)


class SpeiTests(unittest.TestCase):
    def test_prepare_monthly_climatic_water_balance_aggregates_daily_inputs(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2020-01-01", "2020-01-02", "2020-02-01", "2020-02-02"]
                ),
                "precipitation": [10.0, 5.0, 8.0, 2.0],
                "ET0_mm_day": [4.0, 4.0, 3.0, 3.0],
            }
        )

        monthly = prepare_monthly_climatic_water_balance(frame)

        self.assertEqual(2, len(monthly))
        self.assertEqual(15.0, monthly.loc[0, "precipitation_mm"])
        self.assertEqual(8.0, monthly.loc[0, "et0_mm"])
        self.assertEqual(7.0, monthly.loc[0, "water_balance_mm"])
        self.assertEqual("daily", monthly.attrs["spei_metadata"]["input_resolution"])

    def test_compute_monthly_spei_rolls_and_standardizes_by_calendar_month(self):
        dates = pd.date_range("2001-01-01", periods=120, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [100 + (d.month * 5) + (d.year - 2001) * 2 for d in dates],
                "et0_mm": [80 + d.month for d in dates],
            }
        )

        result = compute_monthly_spei(
            frame,
            scale_months=1,
            min_points_per_calendar_month=5,
        )

        january = result[result["month"] == 1]["spei"].dropna()
        july = result[result["month"] == 7]["spei"].dropna()

        self.assertEqual(10, len(january))
        self.assertAlmostEqual(0.0, float(january.mean()), places=6)
        self.assertAlmostEqual(0.0, float(july.mean()), places=6)
        self.assertTrue(result["spei"].notna().all())
        self.assertEqual(
            "empirical_normal_by_calendar_month",
            result.attrs["spei_metadata"]["standardization_method"],
        )

    def test_compute_monthly_spei_requires_enough_points_per_calendar_month(self):
        dates = pd.date_range("2020-01-01", periods=24, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [120.0] * len(dates),
                "et0_mm": [90.0] * len(dates),
            }
        )

        result = compute_monthly_spei(
            frame,
            scale_months=3,
            min_points_per_calendar_month=5,
        )

        self.assertTrue(result["spei"].isna().all())

    def test_prepare_monthly_climatic_water_balance_rejects_multi_site_frames(self):
        frame = pd.DataFrame(
            {
                "site": ["A", "B"],
                "date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
                "precipitation": [10.0, 12.0],
                "ET0_mm_day": [4.0, 4.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "single site per call"):
            prepare_monthly_climatic_water_balance(frame)


if __name__ == "__main__":
    unittest.main()
