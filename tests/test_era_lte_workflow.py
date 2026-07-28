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

import os
import tempfile

from examples.era_lte_workflow import (
    has_season_windows,
    load_sites,
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


class EraSoftDateTests(unittest.TestCase):
    """ERA records season bounds as descriptive strings, not MM-DD.

    Conversion rules (confirmed with the ERA team): bare month -> 1st for a
    start / last day for an end; Early- -> 5th, Mid- -> 15th, Late- -> 25th.
    """

    def test_qualified_months(self):
        cases = {
            "Early-Mar": "03-05",
            "Mid-Mar": "03-15",
            "Late-Jun": "06-25",
            "Mid-May": "05-15",
            "Early-Nov": "11-05",
            "Late-Oct": "10-25",
            "mid-july": "07-15",   # case-insensitive
            "MID-MAR": "03-15",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_month_day(raw), expected)

    def test_bare_month_start_is_first_of_month(self):
        for raw, expected in {"Mar": "03-01", "Jun": "06-01", "July": "07-01"}.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_month_day(raw), expected)

    def test_bare_month_end_is_last_day_of_month(self):
        cases = {"July": "07-31", "Sep": "09-30", "Feb": "02-28", "Mar": "03-31"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_month_day(raw, is_end=True), expected)

    def test_qualifier_ignores_is_end(self):
        # Only bare month names depend on start/end context.
        self.assertEqual(parse_month_day("Late-Jun", is_end=True), "06-25")

    def test_numeric_forms_still_work(self):
        self.assertEqual(parse_month_day("03-01"), "03-01")
        self.assertEqual(parse_month_day("03-31", is_end=True), "03-31")

    def test_unknown_month_name_raises(self):
        for bad in ("Smarch", "Early-Smarch", "notamonth"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_month_day(bad)

    def test_era_rows_map_to_fixed_season(self):
        # Real shapes from the ERA Site.Out table.
        self.assertEqual(
            lte_to_fixed_season({"s1_start": "Mid-Mar", "s1_end": "Late-Jun"}),
            "03-15:06-25",
        )
        self.assertEqual(
            lte_to_fixed_season({"s1_start": "Mar", "s1_end": "July"}),
            "03-01:07-31",
        )
        # Year-crossing season (Late-Oct -> Late-Apr) passes straight through.
        self.assertEqual(
            lte_to_fixed_season({"s1_start": "Late-Oct", "s1_end": "Late-Apr"}),
            "10-25:04-25",
        )
        # Two seasons.
        self.assertEqual(
            lte_to_fixed_season({
                "s1_start": "Mid-Mar", "s1_end": "Mid-July",
                "s2_start": "Early-Nov", "s2_end": "Early-Apr",
            }),
            "03-15:07-15,11-05:04-05",
        )


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


class EraNativeColumnTests(unittest.TestCase):
    """The ERA `lte_summary` export (native Site.* column names) loads directly."""

    def test_lte_summary_columns_alias_and_map(self):
        csv = (
            "Site.ID,Site.LatD,Site.LonD,Study.Start,Study.End,"
            "Site.Start.S1,Site.End.S1,Site.MSP.S1,P.Product\n"
            "Nairobi,-1.286,36.817,2016,2020,03-01,05-31,320,maize\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv)
            path = f.name
        try:
            df = load_sites(path)
        finally:
            os.unlink(path)

        row = df.iloc[0].to_dict()
        self.assertEqual((row["lat"], row["lon"]), (-1.286, 36.817))
        self.assertEqual((row["start_year"], row["end_year"]), (2016, 2020))
        self.assertEqual(row["reported_rain_mm"], 320)
        self.assertEqual(row["crop_name"], "maize")
        self.assertTrue(has_season_windows(row))
        self.assertEqual(lte_to_fixed_season(row), "03-01:05-31")

    def test_duplicate_alias_sources_do_not_create_duplicate_columns(self):
        """An export carrying both `Latitude` and `Site.LatD` must still yield one `lat`."""
        csv = (
            "Site.ID,Latitude,Site.LatD,Longitude,Site.LonD,Study.Start,Study.End,"
            "Site.Start.S1,Site.End.S1\n"
            "Nairobi,-1.286,-1.286,36.817,36.817,2016,2020,Mid-Mar,Late-Jun\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv)
            path = f.name
        try:
            df = load_sites(path)
        finally:
            os.unlink(path)

        self.assertEqual(list(df.columns).count("lat"), 1)
        self.assertEqual(list(df.columns).count("lon"), 1)
        row = df.iloc[0].to_dict()
        self.assertEqual((row["lat"], row["lon"]), (-1.286, 36.817))
        self.assertEqual(lte_to_fixed_season(row), "03-15:06-25")


if __name__ == "__main__":
    unittest.main()
