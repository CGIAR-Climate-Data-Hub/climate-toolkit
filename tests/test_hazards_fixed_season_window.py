"""Year-crossing fixed-season inclusion for calculate_hazards (issue #175, part 2).

A fixed season belongs to the year it starts in and is kept only when its start
falls inside [date_from, date_to]. Previously a season was included or not
depending on how far date_to reached past 31 December, so a season whose start
fell after date_to could slip in silently. Now such seasons are skipped and
reported under 'skipped_seasons' instead of dropped (or included) silently.

The mocked season-generation returns a single season whose start is after
date_to, so it is skipped and no network / Earth Engine access happens.
"""

import unittest
from unittest.mock import patch

from climate_toolkit.calculate_hazards import hazards


def _run(date_from, date_to, onset, cessation):
    seasons = {
        int(onset[:4]): [{"onset": onset, "cessation": cessation, "length_days": 123}]
    }
    with patch.object(hazards, "resolve_thi_profile", return_value={"label": "test"}), \
         patch.object(hazards, "fetch_and_analyze_years_fixed",
                      return_value=(seasons, {int(onset[:4]): {}})):
        return hazards.calculate_hazards(
            "maize", (-0.3868, 37.6323), date_from, date_to,
            fixed_season="10-01:01-31", source="agera_5",
        )


class FixedSeasonWindowTests(unittest.TestCase):
    def test_season_starting_after_date_to_is_skipped_and_reported(self):
        # 2011 season starts 2011-10-01, after date_to 2011-06-30 -> must be skipped
        r = _run("2010-01-01", "2011-06-30", "2011-10-01", "2012-01-31")
        self.assertIn("skipped_seasons", r)
        self.assertEqual(1, len(r["skipped_seasons"]))
        self.assertEqual("2011-10-01", r["skipped_seasons"][0]["onset"])

    def test_skip_is_not_silent_when_nothing_is_left(self):
        # when every season is out of window, the error explains why (not silent)
        r = _run("2010-01-01", "2011-06-30", "2011-10-01", "2012-01-31")
        self.assertIn("error", r)
        self.assertIn("outside", r["error"])
        self.assertIn("2011-10-01", r["error"])

    def test_season_starting_before_date_from_is_skipped(self):
        # a season whose start precedes date_from is also outside the window
        r = _run("2010-06-01", "2010-12-31", "2010-03-01", "2010-06-30")
        self.assertEqual(1, len(r.get("skipped_seasons", [])))
        self.assertEqual("2010-03-01", r["skipped_seasons"][0]["onset"])


if __name__ == "__main__":
    unittest.main()
