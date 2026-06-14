import unittest

from analysis.report_auto_season_alignment import summarize_candidate


class AutoSeasonAlignmentReportTests(unittest.TestCase):
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
