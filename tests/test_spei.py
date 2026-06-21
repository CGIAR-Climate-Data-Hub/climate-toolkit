import unittest

import pandas as pd

from climate_tookit.climatology.spei import (
    _cdf_generalized_logistic,
    _fit_generalized_logistic_ub_pwm,
    _ppf_generalized_logistic,
    compute_monthly_spi,
    compute_monthly_spei,
    prepare_monthly_climatic_water_balance,
    prepare_monthly_precipitation_totals,
)
from climate_tookit.climatology.xclim_reference import (
    XCLIM_AVAILABLE,
    compute_xclim_spei_reference,
    compute_xclim_spi_reference,
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

    def test_fit_generalized_logistic_ub_pwm_recovers_known_parameters(self):
        params = {"xi": -5.0, "alpha": 12.0, "kappa": 0.2}
        probs = [i / 51 for i in range(1, 50)]
        sample = pd.Series([_ppf_generalized_logistic(p, params) for p in probs])

        fitted = _fit_generalized_logistic_ub_pwm(sample)

        self.assertIsNotNone(fitted)
        self.assertAlmostEqual(params["xi"], fitted["xi"], delta=1.0)
        self.assertAlmostEqual(params["alpha"], fitted["alpha"], delta=1.2)
        self.assertAlmostEqual(params["kappa"], fitted["kappa"], delta=0.05)

    def test_cdf_generalized_logistic_inverts_quantiles(self):
        params = {"xi": 3.0, "alpha": 9.0, "kappa": -0.15}
        probs = [0.1, 0.25, 0.5, 0.75, 0.9]
        values = pd.Series([_ppf_generalized_logistic(p, params) for p in probs])

        cdf = _cdf_generalized_logistic(values, params)

        for observed, expected in zip(cdf.tolist(), probs):
            self.assertAlmostEqual(expected, observed, places=6)

    def test_compute_monthly_spei_defaults_to_standard_ub_pwm_fit(self):
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
        self.assertEqual(10, len(january))
        self.assertTrue(result["spei"].notna().all())
        self.assertEqual(
            "generalized_logistic_ub_pwm_by_calendar_month",
            result.attrs["spei_metadata"]["standardization_method"],
        )
        self.assertEqual("ub-pwm", result.attrs["spei_metadata"]["fit"])
        self.assertIsNotNone(result.attrs["spei_metadata"]["fit_parameters_by_month"][1])
        self.assertTrue(all(a < b for a, b in zip(january.tolist(), january.tolist()[1:])))

    def test_compute_monthly_spei_empirical_fit_is_explicit_fallback(self):
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
            fit="empirical",
        )

        self.assertEqual(
            "empirical_normal_by_calendar_month",
            result.attrs["spei_metadata"]["standardization_method"],
        )
        self.assertIsNone(result.attrs["spei_metadata"]["fit_parameters_by_month"][1])

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

    def test_compute_monthly_spei_uses_reference_period_for_fit_only(self):
        dates = pd.date_range("2001-01-01", periods=120, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [110 + d.month + (d.year - 2001) for d in dates],
                "et0_mm": [90 + d.month for d in dates],
            }
        )

        result = compute_monthly_spei(
            frame,
            scale_months=1,
            min_points_per_calendar_month=4,
            ref_start="2001-01-01",
            ref_end="2005-12-31",
        )

        metadata = result.attrs["spei_metadata"]
        self.assertEqual("2001-01-01", metadata["reference_period"]["start"])
        self.assertEqual("2005-12-01", metadata["reference_period"]["end"])
        self.assertEqual(10, len(result[result["month"] == 1]))
        self.assertTrue(result["spei"].iloc[-1] == result["spei"].iloc[-1])

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

    def test_prepare_monthly_precipitation_totals_aggregates_daily_inputs(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2020-01-01", "2020-01-02", "2020-02-01", "2020-02-02"]
                ),
                "precipitation": [10.0, 5.0, 8.0, 2.0],
            }
        )

        monthly = prepare_monthly_precipitation_totals(frame)

        self.assertEqual(2, len(monthly))
        self.assertEqual(15.0, monthly.loc[0, "precipitation_mm"])
        self.assertEqual("daily", monthly.attrs["spei_metadata"]["input_resolution"])

    def test_compute_monthly_spi_defaults_to_standard_ub_pwm_fit(self):
        dates = pd.date_range("2001-01-01", periods=120, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [100 + (d.month * 5) + (d.year - 2001) * 2 for d in dates],
            }
        )

        result = compute_monthly_spi(
            frame,
            scale_months=1,
            min_points_per_calendar_month=5,
        )

        january = result[result["month"] == 1]["spi"].dropna()
        self.assertEqual(10, len(january))
        self.assertTrue(result["spi"].notna().all())
        self.assertEqual(
            "generalized_logistic_ub_pwm_by_calendar_month",
            result.attrs["spei_metadata"]["standardization_method"],
        )
        self.assertEqual("SPI", result.attrs["spei_metadata"]["index_name"])
        self.assertEqual("ub-pwm", result.attrs["spei_metadata"]["fit"])
        self.assertIsNotNone(result.attrs["spei_metadata"]["fit_parameters_by_month"][1])
        self.assertTrue(all(a < b for a, b in zip(january.tolist(), january.tolist()[1:])))

    def test_compute_monthly_spi_empirical_fit_is_explicit_fallback(self):
        dates = pd.date_range("2001-01-01", periods=120, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [100 + (d.month * 5) + (d.year - 2001) * 2 for d in dates],
            }
        )

        result = compute_monthly_spi(
            frame,
            scale_months=1,
            min_points_per_calendar_month=5,
            fit="empirical",
        )

        self.assertEqual(
            "empirical_normal_by_calendar_month",
            result.attrs["spei_metadata"]["standardization_method"],
        )
        self.assertIsNone(result.attrs["spei_metadata"]["fit_parameters_by_month"][1])

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_compute_monthly_spi_tracks_xclim_fisk_reference(self):
        dates = pd.date_range("2000-01-01", periods=240, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [
                    80 + (d.month * 4) + ((d.year - 2000) % 7) * 3
                    for d in dates
                ],
            }
        )

        ours = compute_monthly_spi(
            frame,
            scale_months=3,
            min_points_per_calendar_month=10,
        )
        xclim_ref = compute_xclim_spi_reference(
            frame,
            scale_months=3,
        )
        merged = ours.merge(xclim_ref[["date", "spi_xclim"]], on="date", how="inner").dropna()

        self.assertGreater(len(merged), 100)
        self.assertGreater(merged["spi"].corr(merged["spi_xclim"]), 0.999)
        self.assertLess((merged["spi"] - merged["spi_xclim"]).abs().mean(), 0.05)

    @unittest.skipUnless(XCLIM_AVAILABLE, "xclim not installed")
    def test_compute_monthly_spei_tracks_xclim_fisk_reference(self):
        dates = pd.date_range("2000-01-01", periods=240, freq="MS")
        frame = pd.DataFrame(
            {
                "date": dates,
                "precipitation_mm": [
                    80 + (d.month * 4) + ((d.year - 2000) % 7) * 3
                    for d in dates
                ],
                "et0_mm": [60 + d.month for d in dates],
            }
        )

        ours = compute_monthly_spei(
            frame,
            scale_months=3,
            min_points_per_calendar_month=10,
        )
        xclim_ref = compute_xclim_spei_reference(
            frame,
            scale_months=3,
        )
        merged = ours.merge(xclim_ref[["date", "spei_xclim"]], on="date", how="inner").dropna()

        self.assertGreater(len(merged), 100)
        self.assertGreater(merged["spei"].corr(merged["spei_xclim"]), 0.999)
        self.assertLess((merged["spei"] - merged["spei_xclim"]).abs().mean(), 0.05)


if __name__ == "__main__":
    unittest.main()
