import unittest
from unittest import mock

import pandas as pd

from climate_tookit.climatology import (
    build_thi_hazard_thresholds,
    classify_thi_values,
    compute_daily_thi,
    describe_thi_method,
    describe_thi_source_support,
    infer_livestock_climate_profile,
    list_thi_livestock_profiles,
    resolve_thi_profile,
    summarize_thi_periods,
)


class LivestockThiTests(unittest.TestCase):
    def test_compute_daily_thi_derives_mean_temperature_from_tmax_tmin(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                "tmax": [30.0, 32.0],
                "tmin": [20.0, 22.0],
                "humidity": [50.0, 80.0],
            }
        )

        result = compute_daily_thi(frame)

        self.assertEqual(["date", "tmax", "tmin", "humidity", "temperature_c", "thi", "thi_class"], list(result.columns))
        self.assertAlmostEqual(25.0, result.loc[0, "temperature_c"], places=6)
        self.assertAlmostEqual(71.775, result.loc[0, "thi"], places=3)
        self.assertEqual("none", result.loc[0, "thi_class"])
        self.assertEqual("mild", result.loc[1, "thi_class"])
        self.assertEqual("derived_from_tmax_tmin", result.attrs["thi_metadata"]["temperature_source"])
        self.assertEqual("cattle_dairy", result.attrs["thi_metadata"]["livestock_type"])

    def test_compute_daily_thi_rejects_missing_humidity(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01"]),
                "tavg": [25.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "Missing required humidity column"):
            compute_daily_thi(frame)

    def test_classify_thi_values_uses_cattle_dairy_boundaries(self):
        values = pd.Series([72.0, 73.0, 79.0, 80.0, 89.0, 90.0])
        result = classify_thi_values(values)
        self.assertEqual(
            ["none", "mild", "mild", "moderate", "moderate", "severe"],
            result.tolist(),
        )

    def test_resolve_thi_profile_uses_tropical_highland_as_temperate_proxy(self):
        profile = resolve_thi_profile(
            livestock_type="cattle_dairy",
            climate_profile="auto",
            lat=-1.286,
            lon=36.817,
            elevation_m=1667.0,
        )

        self.assertEqual("temperate", profile["climate_profile_applied"])
        self.assertEqual("tropical_highland_proxy", profile["climate_profile_reason"])
        self.assertEqual(89.0, profile["thresholds"]["moderate_max"])

    def test_resolve_thi_profile_uses_tropical_extreme_adjustment(self):
        profile = resolve_thi_profile(
            livestock_type="pigs",
            climate_profile="tropical",
        )

        self.assertEqual("tropical", profile["climate_profile_applied"])
        self.assertEqual(92.0, profile["thresholds"]["moderate_max"])

    def test_build_thi_hazard_thresholds_tracks_profile_thresholds(self):
        hazard_thresholds = build_thi_hazard_thresholds(
            livestock_type="poultry_layers",
            climate_profile="temperate",
        )

        self.assertEqual((None, 71.0), hazard_thresholds["none"])
        self.assertEqual((71.0, 76.0), hazard_thresholds["mild"])
        self.assertEqual((76.0, 82.0), hazard_thresholds["moderate"])
        self.assertEqual((82.0, None), hazard_thresholds["severe"])

    def test_infer_livestock_climate_profile_falls_back_to_tropical_latitude(self):
        inferred = infer_livestock_climate_profile(
            lat=0.5,
            lon=25.1,
            climate_profile="auto",
        )

        self.assertEqual("tropical", inferred["applied"])
        self.assertEqual("tropical_latitude_band", inferred["reason"])

    def test_infer_livestock_climate_profile_uses_dem_fetch_for_highland_proxy(self):
        with mock.patch(
            "climate_tookit.weather_station.dem.fetch_anchor_elevation",
            return_value=1667.0,
        ):
            inferred = infer_livestock_climate_profile(
                lat=-1.286,
                lon=36.817,
                climate_profile="auto",
                auto_fetch_elevation=True,
            )

        self.assertEqual("temperate", inferred["applied"])
        self.assertEqual("tropical_highland_proxy", inferred["reason"])
        self.assertEqual(1667.0, inferred["elevation_m"])
        self.assertEqual("dem", inferred["elevation_source"])

    def test_list_thi_profiles_exposes_species_choices(self):
        profiles = list_thi_livestock_profiles()
        self.assertIn("cattle_dairy", profiles)
        self.assertIn("pigs", profiles)

    def test_summarize_thi_periods_counts_bands(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2020-01-01", "2020-01-02", "2020-01-03", "2021-01-01"]
                ),
                "thi": [70.0, 75.0, 91.0, 80.0],
            }
        )

        result = summarize_thi_periods(frame, freq="YS")

        self.assertEqual(2, len(result))
        row_2020 = result[result["period_start"] == "2020-01-01"].iloc[0]
        self.assertEqual(3, int(row_2020["days_total"]))
        self.assertEqual(1, int(row_2020["days_none"]))
        self.assertEqual(1, int(row_2020["days_mild"]))
        self.assertEqual(0, int(row_2020["days_moderate"]))
        self.assertEqual(1, int(row_2020["days_severe"]))
        self.assertEqual(2, int(row_2020["days_stress"]))

    def test_describe_thi_source_support_flags_future_path_gap(self):
        support = describe_thi_source_support()
        self.assertIn("agera_5", support)
        self.assertIn("nex_gddp", support)
        self.assertIn("conditionally supported", support["nex_gddp"])
        self.assertIn("does not define a humidity band", support["era_5"])

    def test_describe_thi_method_exposes_formula_profiles_and_support(self):
        method = describe_thi_method()
        self.assertEqual("livestock_thi", method["metric"])
        self.assertIn("0.0055*RH", method["formula"])
        self.assertEqual(
            "daily mean temperature plus daily relative humidity",
            method["default_daily_workflow"],
        )
        self.assertEqual(23.5, method["climate_profile_logic"]["tropics_latitude_deg"])
        self.assertIn("cattle_dairy", method["profiles"])
        self.assertEqual(
            92.0,
            method["profiles"]["pigs"]["thresholds_tropical"]["moderate_max"],
        )
        self.assertIn("nasa_power", method["source_support"])
        self.assertIn("Not default", method["method_rationale"]["max_temperature_screening_status"])
        self.assertIn(
            "Species-group operational defaults, not breed-resolved physiology.",
            method["interpretation_caveats"],
        )


if __name__ == "__main__":
    unittest.main()
