import unittest

from climate_tookit.season_analysis.season_identity import build_season_identity


class SeasonIdentityTests(unittest.TestCase):
    def test_build_season_identity_exposes_alignment_metadata(self):
        identity = build_season_identity(
            "2019-10-09",
            "2019-12-29",
            length_days=82,
            regime="erratic",
            season_number=2,
            total_seasons_per_year=2,
        )

        self.assertEqual("2019-10-09", identity["onset_date"])
        self.assertEqual("2019-12-29", identity["cessation_date"])
        self.assertEqual(10, identity["onset_month"])
        self.assertEqual(12, identity["cessation_month"])
        self.assertEqual("season_2_of_2", identity["slot_label"])
        self.assertEqual(
            "regime:erratic|onset_month:10",
            identity["experimental_alignment_key"],
        )
        self.assertIn("month_pair:10-12", identity["candidate_alignment_keys"])


if __name__ == "__main__":
    unittest.main()
