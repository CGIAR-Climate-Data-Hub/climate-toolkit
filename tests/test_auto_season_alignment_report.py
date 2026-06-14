import unittest

from analysis.report_auto_season_alignment import (
    overall_recommendation,
    parse_site,
    summarize_candidate,
)


class AutoSeasonAlignmentReportTests(unittest.TestCase):
    def test_parse_site_accepts_optional_region(self):
        site = parse_site("Kisangani,0.5153,25.1910,Humid Congo Basin")

        self.assertEqual("Kisangani", site.name)
        self.assertAlmostEqual(0.5153, site.lat)
        self.assertAlmostEqual(25.1910, site.lon)
        self.assertEqual("Humid Congo Basin", site.region)

    def test_overall_recommendation_handles_zero_season_sites(self):
        recommendation = overall_recommendation(
            [
                {
                    "candidate": "regime_onset_month",
                    "n_seasons": 0,
                    "collision_free": True,
                    "reused_key_fraction": 0.0,
                    "fragmentation_ratio": 0.0,
                }
            ]
        )

        self.assertIn("No detected seasons", recommendation)

    def test_regime_onset_month_summary_detects_reuse_without_collision(self):
        rows = [
            {
                "year": 2018,
                "season_number": 1,
                "regime": "unimodal",
                "season_identity": {
                    "onset_month": 3,
                    "cessation_month": 6,
                    "experimental_alignment_key": "regime:unimodal|onset_month:03",
                },
            },
            {
                "year": 2019,
                "season_number": 1,
                "regime": "unimodal",
                "season_identity": {
                    "onset_month": 3,
                    "cessation_month": 6,
                    "experimental_alignment_key": "regime:unimodal|onset_month:03",
                },
            },
            {
                "year": 2019,
                "season_number": 2,
                "regime": "bimodal",
                "season_identity": {
                    "onset_month": 10,
                    "cessation_month": 12,
                    "experimental_alignment_key": "regime:bimodal|onset_month:10",
                },
            },
        ]

        summary = summarize_candidate(rows, "regime_onset_month")

        self.assertTrue(summary["collision_free"])
        self.assertEqual(2, summary["n_distinct_keys"])
        self.assertGreater(summary["reused_key_fraction"], 0.6)


if __name__ == "__main__":
    unittest.main()
