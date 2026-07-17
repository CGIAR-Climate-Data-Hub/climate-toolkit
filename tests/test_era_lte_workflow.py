"""Unit tests for the ERA LTE workflow's season-window mapper.

Covers the credential-free core: translating ERA season boundaries into the
toolkit's ``fixed_season`` syntax. The actual ``analyze_climate_statistics``
calls are exercised elsewhere / by hand — these tests pin the pure translation.
"""

import os
import sys
import unittest
from datetime import date

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from examples.era_lte_workflow import (
    has_season_windows,
    lte_to_fixed_season,
    parse_month_day,
)


class ParseMonthDayTests(unittest.TestCase):
    def test_accepted_formats_normalize_to_mm_dd(self):
        cases = {
            "03-01": "03-01",
            "3-1": "03-01",
            "03/01": "03-01",
            "03.01": "03-01",
            "0301": "03-01",
            "12-31": "12-31",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_month_day(raw), expected)

    def test_date_like_object(self):
        self.assertEqual(parse_month_day(date(2020, 3, 1)), "03-01")

    def test_invalid_values_raise(self):
        for bad in ("13-01", "03-40", "abc", "", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_month_day(bad)


class LteToFixedSeasonTests(unittest.TestCase):
    def test_single_season(self):
        row = {"s1_start": "03-01", "s1_end": "05-31"}
        self.assertEqual(lte_to_fixed_season(row), "03-01:05-31")

    def test_two_seasons(self):
        row = {"s1_start": "03-01", "s1_end": "05-31", "s2_start": "10-01", "s2_end": "12-15"}
        self.assertEqual(lte_to_fixed_season(row), "03-01:05-31,10-01:12-15")

    def test_year_crossing_passes_through(self):
        # cessation month before onset month; the toolkit wraps to next year.
        row = {"s1_start": "10-01", "s1_end": "03-31"}
        self.assertEqual(lte_to_fixed_season(row), "10-01:03-31")

    def test_empty_s2_ignored(self):
        row = {"s1_start": "03-01", "s1_end": "05-31", "s2_start": "", "s2_end": ""}
        self.assertEqual(lte_to_fixed_season(row), "03-01:05-31")


class ModeSelectionTests(unittest.TestCase):
    def test_season_windows_present_enables_fixed_mode(self):
        self.assertTrue(has_season_windows({"s1_start": "03-01", "s1_end": "05-31"}))

    def test_registry_row_falls_back_to_auto(self):
        # ERA's shipped unique_ltes.csv has no season columns.
        for row in ({}, {"s1_start": "", "s1_end": ""}, {"s1_start": None, "s1_end": None}):
            with self.subTest(row=row):
                self.assertFalse(has_season_windows(row))


if __name__ == "__main__":
    unittest.main()
