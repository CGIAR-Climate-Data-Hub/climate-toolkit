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
from unittest import mock

import pandas as pd

from examples.era_lte_workflow import (
    has_season_windows,
    load_sites,
    lte_to_fixed_season,
    normalize_fixed_season,
    parse_month_day,
    run_site,
    select_sites,
)


class PrebuiltFixedSeasonTests(unittest.TestCase):
    """Rwema's `unique_sites_for_toolkit.csv` ships a month-name fixed_season."""

    def test_month_name_windows(self):
        self.assertEqual(normalize_fixed_season("Feb:May,Jun:Sep"), "02-01:05-31,06-01:09-30")
        self.assertEqual(normalize_fixed_season("Nov:Mar"), "11-01:03-31")  # year-crossing
        self.assertEqual(normalize_fixed_season("March:Aug"), "03-01:08-31")  # full name

    def test_day_qualifiers_map_to_era_days(self):
        # Per the ERA team (#141): d- = Mid (15th), e- = Late (25th), y- = Early (5th).
        self.assertEqual(normalize_fixed_season("d-Mar:e-May"), "03-15:05-25")
        self.assertEqual(normalize_fixed_season("y-Feb:d-Aug"), "02-05:08-15")
        # Mixed with bare months and a leading '-' (-July -> plain July end).
        self.assertEqual(normalize_fixed_season("d-Mar:-July,Sep:d-Nov"), "03-15:07-31,09-01:11-15")
        self.assertEqual(normalize_fixed_season("March:y-Sep,Oct:y-Feb"), "03-01:09-05,10-01:02-05")

    def test_na_window_dropped(self):
        self.assertEqual(normalize_fixed_season("Jun:Sep,NA:NA"), "06-01:09-30")

    def test_row_prebuilt_fixed_season_wins(self):
        row = {"fixed_season": "Feb:May,Jun:Sep", "s1_start": "01-01", "s1_end": "02-01"}
        self.assertTrue(has_season_windows(row))
        self.assertEqual(lte_to_fixed_season(row), "02-01:05-31,06-01:09-30")

    def test_unusable_fixed_season_falls_back_to_windows(self):
        row = {"fixed_season": "NA:NA", "s1_start": "03-01", "s1_end": "05-31"}
        self.assertEqual(lte_to_fixed_season(row), "03-01:05-31")


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


class CompiledTableTests(unittest.TestCase):
    """The #141 `lte_summary` compiled table (treatment + yield) flows through."""

    def test_treatment_and_yield_alias_and_load(self):
        # A slice of the lte_summary schema: two treatment rows for one site.
        csv = (
            "Site.ID,Latitude,Longitude,Study.Start,Study.End,"
            "Site.Start.S1,Site.End.S1,Site.MSP.S1,P.Product,Treatment,Yield\n"
            "SITE1,-1.286,36.817,2016,2020,Mid-Mar,Late-Jun,320,maize,Control,1.2\n"
            "SITE1,-1.286,36.817,2016,2020,Mid-Mar,Late-Jun,320,maize,Mulch,2.8\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv)
            path = f.name
        try:
            df = load_sites(path)
        finally:
            os.unlink(path)

        self.assertEqual(list(df["treatment"]), ["Control", "Mulch"])
        self.assertEqual(list(df["reported_yield"]), [1.2, 2.8])
        self.assertEqual(list(df["crop_name"]), ["maize", "maize"])

    def test_context_fields_echoed_onto_output_rows(self):
        row = {
            "site_id": "SITE1",
            "lat": -1.286,
            "lon": 36.817,
            "start_year": 2019,
            "end_year": 2020,
            "s1_start": "03-01",
            "s1_end": "05-31",
            "reported_rain_mm": 320.0,
            "crop_name": "maize",
            "treatment": "Mulch",
            "reported_yield": 2.8,
        }
        fake = {
            "season_statistics": [
                {
                    "year": 2019,
                    "season_number": 1,
                    "length_days": 90,
                    "precipitation": {"total_mm": 300.0, "rainy_days": 40},
                    "water_balance": {"NDWS": 5, "WRSI": 0.9},
                }
            ]
        }
        with mock.patch(
            "examples.era_lte_workflow.analyze_climate_statistics", return_value=fake
        ):
            out = run_site(row, source="nasa_power")

        self.assertEqual(len(out), 1)
        rec = out[0]
        self.assertEqual(rec["treatment"], "Mulch")
        self.assertEqual(rec["reported_yield"], 2.8)
        self.assertEqual(rec["crop_name"], "maize")
        self.assertEqual(rec["fixed_season"], "03-01:05-31")
        # Comparison against ERA-reported rainfall still works alongside context.
        self.assertEqual(rec["reported_rain_mm"], 320.0)
        self.assertAlmostEqual(rec["rain_delta_mm"], -20.0)

    def test_extra_input_columns_are_captured_on_output(self):
        row = {
            "site_id": "SITE1",
            "lte_id": "LTE001",
            "code": "BC001",
            "lat": -1.0,
            "lon": 35.0,
            "start_year": 2019,
            "end_year": 2020,
            "outcome_year": 2019,
            "crop_name": "maize",
            "treatment": "Manure",
            "reported_yield": 3.4,
            "yield_error": 0.4,
            "planting_start": "Mid-Mar",
            "planting_end": "Late-Mar",
            "map_mm": 1100,
            "mat_c": 18.5,
        }
        fake = {
            "season_statistics": [
                {
                    "year": 2019,
                    "season_number": 1,
                    "length_days": 90,
                    "precipitation": {"total_mm": 300.0, "rainy_days": 40},
                    "water_balance": {"NDWS": 5, "WRSI": 0.9},
                }
            ]
        }
        with mock.patch(
            "examples.era_lte_workflow.analyze_climate_statistics", return_value=fake
        ):
            rec = run_site(row, source="nasa_power")[0]

        for field in ("lte_id", "code", "lat", "lon", "start_year", "end_year",
                      "outcome_year", "yield_error", "planting_start", "planting_end",
                      "map_mm", "mat_c"):
            self.assertIn(field, rec)
        self.assertEqual(rec["lte_id"], "LTE001")
        self.assertEqual(rec["map_mm"], 1100)
        # site_id leads the record; toolkit metrics still present.
        self.assertEqual(next(iter(rec)), "site_id")
        self.assertIn("tk_WRSI", rec)


class RealRegistryFormatTests(unittest.TestCase):
    """The real ERA registry is semicolon-delimited, cp1252, with messy headers."""

    def test_semicolon_cp1252_messy_header_loads(self):
        # Mirrors unique.ltes.csv: ';' sep, trailing-space headers, empty
        # trailing columns, and a cp1252 en-dash (0x96) in a text field.
        # b"\x96" is a raw cp1252 byte (en-dash) — the kind that breaks a naive
        # UTF-8 read, exactly as in the real unique.ltes.csv.
        csv = (
            b"LTE.ID;Site.ID;Code;Year.start ;Year.end ;Notes;Latitude;Longitude ;;\n"
            b"LTE0003;Adigudem;DK0054;2005;2011;multi\x96season;13.23333;39.53333;;\n"
        )
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as f:
            f.write(csv)
            path = f.name
        try:
            df = load_sites(path)
        finally:
            os.unlink(path)

        row = df.iloc[0].to_dict()
        self.assertEqual((row["lat"], row["lon"]), (13.23333, 39.53333))
        self.assertEqual((row["start_year"], row["end_year"]), (2005, 2011))
        self.assertEqual(row["site_id"], "Adigudem")
        self.assertEqual(row["lte_id"], "LTE0003")
        # No stray unnamed/empty columns survived the header tidy.
        self.assertFalse([c for c in df.columns if str(c).startswith("Unnamed")])

    def test_shipped_real_registry_loads(self):
        registry = os.path.join(REPO_ROOT, "examples", "data", "unique_ltes.csv")
        if not os.path.exists(registry):
            self.skipTest("shipped registry not present")
        df = load_sites(registry)
        self.assertGreater(len(df), 100)
        for col in ("site_id", "lat", "lon", "start_year", "end_year"):
            self.assertIn(col, df.columns)
        self.assertTrue(df["lat"].notna().all() and df["lon"].notna().all())


class FetchCacheTests(unittest.TestCase):
    """A shared cache fetches once per (location, period, season, source)."""

    def test_repeated_site_fetches_once(self):
        rows = [
            {"site_id": "S", "lat": 1.0, "lon": 2.0, "start_year": 2019, "end_year": 2020,
             "treatment": t}
            for t in ("Control", "Mulch", "Manure")  # same coords/period, 3 treatments
        ]
        fake = {"season_statistics": [
            {"year": 2019, "season_number": 1, "length_days": 90,
             "precipitation": {"total_mm": 300.0, "rainy_days": 40},
             "water_balance": {"NDWS": 5, "WRSI": 0.9}},
        ]}
        cache: dict = {}
        with mock.patch(
            "examples.era_lte_workflow.analyze_climate_statistics", return_value=fake
        ) as m:
            for r in rows:
                run_site(r, source="nasa_power", cache=cache)

        self.assertEqual(m.call_count, 1)   # fetched once, not three times
        self.assertEqual(len(cache), 1)

    def test_no_cache_still_works(self):
        row = {"site_id": "S", "lat": 1.0, "lon": 2.0, "start_year": 2019, "end_year": 2020}
        fake = {"season_statistics": [
            {"year": 2019, "season_number": 1, "length_days": 90,
             "precipitation": {"total_mm": 300.0, "rainy_days": 40},
             "water_balance": {"NDWS": 5, "WRSI": 0.9}},
        ]}
        with mock.patch(
            "examples.era_lte_workflow.analyze_climate_statistics", return_value=fake
        ):
            out = run_site(row, source="nasa_power")  # cache omitted
        self.assertEqual(len(out), 1)


class SiteOutExtractTests(unittest.TestCase):
    """The Site.Out extractor keeps only season+rainfall rows, toolkit-ready."""

    def test_extract_filters_and_loads(self):
        import importlib.util
        if importlib.util.find_spec("ijson") is None:
            self.skipTest("ijson not installed")
        import json as _json

        from examples.era_extract_site_out import extract

        data = {"Site.Out": [
            {"Site.ID": "A", "Site.LatD": 1.0, "Site.LonD": 2.0,
             "Site.Start.S1": "Mar", "Site.End.S1": "Jun", "Site.MSP.S1": 300},
            {"Site.ID": "B", "Site.LatD": 3.0, "Site.LonD": 4.0,  # no season/MSP -> skipped
             "Site.Start.S1": None, "Site.End.S1": None, "Site.MSP.S1": None},
            {"Site.ID": "A", "Site.LatD": 1.0, "Site.LonD": 2.0,  # dup site -> skipped
             "Site.Start.S1": "Mar", "Site.End.S1": "Jun", "Site.MSP.S1": 310},
        ]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as jf:
            _json.dump(data, jf)
            jpath = jf.name
        out = jpath + ".csv"
        try:
            n = extract(jpath, out, 1991, 2020)
            self.assertEqual(n, 1)  # only site A, once
            df = load_sites(out)
            row = df.iloc[0].to_dict()
            self.assertEqual((row["lat"], row["lon"]), (1.0, 2.0))
            self.assertEqual(row["reported_rain_mm"], 300)
            self.assertEqual((row["start_year"], row["end_year"]), (1991, 2020))
            self.assertEqual(lte_to_fixed_season(row), "03-01:06-30")
        finally:
            os.unlink(jpath)
            if os.path.exists(out):
                os.unlink(out)

    def test_with_yield_filters_and_normalizes_units(self):
        import importlib.util
        if importlib.util.find_spec("ijson") is None:
            self.skipTest("ijson not installed")
        import json as _json

        from examples.era_extract_site_out import extract

        data = {
            "Site.Out": [
                {"Site.ID": "A", "Site.LatD": 1.0, "Site.LonD": 2.0,
                 "Site.Start.S1": "Mar", "Site.End.S1": "Jun", "Site.MSP.S1": 300},
            ],
            "Data.Out": [
                # Crop Yield in kg/ha -> normalized to t/ha (3000 -> 3.0).
                {"Site.ID": "A", "T.Name": "Control", "Product.Simple": "Maize",
                 "Out.Subind": "Crop Yield", "Out.Unit": "kg/ha", "ED.Mean.T": 3000},
                # Same treatment, t/ha -> averaged with the above (5.0) -> 4.0.
                {"Site.ID": "A", "T.Name": "Control", "Product.Simple": "Maize",
                 "Out.Subind": "Crop Yield", "Out.Unit": "t/ha", "ED.Mean.T": 5.0},
                # Biomass Yield must be ignored.
                {"Site.ID": "A", "T.Name": "Control", "Product.Simple": "Maize",
                 "Out.Subind": "Biomass Yield", "Out.Unit": "t/ha", "ED.Mean.T": 20.0},
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as jf:
            _json.dump(data, jf)
            jpath = jf.name
        out = jpath + ".csv"
        try:
            extract(jpath, out, 1991, 2020, with_yield=True)
            df = load_sites(out)
            row = df.iloc[0].to_dict()
            self.assertEqual(row["treatment"], "Control")
            self.assertEqual(row["crop_name"], "Maize")
            # (3.0 t/ha + 5.0 t/ha) / 2 = 4.0; biomass excluded.
            self.assertAlmostEqual(row["reported_yield"], 4.0)
        finally:
            os.unlink(jpath)
            if os.path.exists(out):
                os.unlink(out)


class YieldUnitNormalizationTests(unittest.TestCase):
    """Rwema's expanded Yield is mixed-unit; the unit is in Out.Code.Joined."""

    def test_yield_normalized_to_t_ha(self):
        csv = (
            "Site.ID,Latitude,Longitude,Study.Start,Study.End,"
            "Site.Start.S1,Site.End.S1,P.Product,Yield,Out.Code.Joined\n"
            "A,-1.0,35.0,2000,2005,Mar,Jun,Maize,3.5,Crop Yield..t/ha\n"
            "B,-1.0,35.0,2000,2005,Mar,Jun,Maize,3500,Crop Yield..kg/ha\n"
            "C,-1.0,35.0,2000,2005,Mar,Jun,Maize,4.0,Crop Yield..Mg/ha..Mean\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv)
            path = f.name
        try:
            df = load_sites(path)
        finally:
            os.unlink(path)
        y = dict(zip(df["site_id"], df["reported_yield"]))
        self.assertAlmostEqual(y["A"], 3.5)     # t/ha unchanged
        self.assertAlmostEqual(y["B"], 3.5)     # kg/ha -> /1000
        self.assertAlmostEqual(y["C"], 4.0)     # Mg/ha == t/ha


class YieldAnalysisIdentifierTests(unittest.TestCase):
    """era_yield_analysis links study Code -> master LTE.ID via the registry."""

    def test_code_to_lte_maps_from_registry(self):
        from examples.era_yield_analysis import _code_to_lte
        m = _code_to_lte()
        self.assertIsInstance(m, dict)
        self.assertGreater(len(m), 100)  # the shipped registry has ~300 codes
        self.assertTrue(any(str(v).startswith("LTE") for v in list(m.values())[:30]))


class MissingInputGuardTests(unittest.TestCase):
    """A missing input CSV gives an actionable message, not a raw traceback."""

    def test_missing_file_raises_actionable_error(self):
        from examples.era_lte_workflow import _require_input
        with self.assertRaises(SystemExit) as cm:
            _require_input("/tmp/definitely_missing_era_input.csv")
        msg = str(cm.exception)
        self.assertIn("not found", msg)
        self.assertIn("lte_final.csv", msg)          # points to the public route
        self.assertIn("lte_summary_expanded.csv", msg)  # names the common trip-up

    def test_existing_file_passes(self):
        from examples.era_lte_workflow import _require_input
        _require_input(os.path.join(REPO_ROOT, "examples", "data", "unique_sites_for_toolkit.csv"))


class SelectSitesTests(unittest.TestCase):
    def _frame(self):
        return pd.DataFrame(
            {"site_id": ["A", "A", "B", "C"], "lat": [1, 1, 2, 3], "lon": [1, 1, 2, 3]}
        )

    def test_default_returns_all(self):
        self.assertEqual(len(select_sites(self._frame())), 4)

    def test_single_site(self):
        out = select_sites(self._frame(), site_ids=["B"])
        self.assertEqual(list(out["site_id"]), ["B"])

    def test_multiple_sites_repeated_and_comma(self):
        self.assertEqual(sorted(select_sites(self._frame(), site_ids=["A", "C"])["site_id"].unique()),
                         ["A", "C"])
        self.assertEqual(sorted(select_sites(self._frame(), site_ids=["A,C"])["site_id"].unique()),
                         ["A", "C"])

    def test_unknown_site_raises(self):
        with self.assertRaises(SystemExit):
            select_sites(self._frame(), site_ids=["Z"])

    def test_comma_in_real_site_name_is_not_split(self):
        # Real ERA Site.IDs contain commas — an exact match must win over split.
        frame = pd.DataFrame({
            "site_id": ["AfricaRice, Fanaye", "Kitale", "Tamale"],
            "lat": [1, 2, 3], "lon": [1, 2, 3],
        })
        out = select_sites(frame, site_ids=["AfricaRice, Fanaye"])
        self.assertEqual(list(out["site_id"]), ["AfricaRice, Fanaye"])
        # A non-site value still comma-splits as before.
        out2 = select_sites(frame, site_ids=["Kitale,Tamale"])
        self.assertEqual(sorted(out2["site_id"]), ["Kitale", "Tamale"])

    def test_limit_after_selection(self):
        self.assertEqual(len(select_sites(self._frame(), site_ids=["A"], limit=1)), 1)


if __name__ == "__main__":
    unittest.main()
