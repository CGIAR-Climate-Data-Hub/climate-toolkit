"""Unit tests for the shared visualization foundation (``climate_toolkit.visualization``).

Covers the pure helpers — variable labels, treatment-name shortening, palette
sanity, and figure IO — that the ERA plot scripts (and future report modules)
build on.
"""

import os
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from climate_toolkit.visualization import (
    BAR,
    LINES,
    VARIABLE_LABELS,
    label_for,
    save_figure,
    shorten_treatment,
    use_headless,
    variety_transitions,
)


class LabelsTests(unittest.TestCase):
    def test_known_variable_maps_to_display_label(self):
        self.assertEqual(label_for("tk_NDWS"), "Water-stress days (NDWS)")
        self.assertEqual(label_for("tk_WRSI"), "Water-satisfaction (WRSI)")

    def test_unknown_variable_falls_back_to_raw_name(self):
        self.assertEqual(label_for("tk_not_a_real_metric"), "tk_not_a_real_metric")

    def test_all_five_toolkit_metrics_are_labelled(self):
        for key in ("tk_rain_total_mm", "tk_rainy_days", "tk_dry_days", "tk_NDWS", "tk_WRSI"):
            self.assertIn(key, VARIABLE_LABELS)


class ShortenTreatmentTests(unittest.TestCase):
    def test_short_label_is_unchanged(self):
        self.assertEqual(shorten_treatment("NT 100N"), "NT 100N")

    def test_long_label_is_ellipsized_to_n(self):
        out = shorten_treatment("a" * 40, n=10)
        self.assertEqual(len(out), 10)
        self.assertTrue(out.endswith("…"))

    def test_rotation_and_repeat_suffixes_are_dropped(self):
        self.assertEqual(shorten_treatment("Maize >> Bean rotation"), "Maize")
        self.assertEqual(shorten_treatment("NT 0N ***rep2"), "NT 0N")

    def test_non_string_input_is_coerced(self):
        self.assertEqual(shorten_treatment(123), "123")


class PaletteTests(unittest.TestCase):
    def test_bar_is_a_hex_colour(self):
        self.assertTrue(BAR.startswith("#") and len(BAR) == 7)

    def test_lines_is_a_nonempty_list_of_hex_colours(self):
        self.assertGreater(len(LINES), 0)
        for c in LINES:
            self.assertTrue(c.startswith("#") and len(c) == 7)


class VarietyTransitionsTests(unittest.TestCase):
    def test_single_variety_marks_only_the_first_year(self):
        # a site that never changed variety still gets one marker, at year 1
        df = pd.DataFrame({"year": [2005, 2006, 2007], "variety": ["RT 624"] * 3})
        self.assertEqual(variety_transitions(df), [(2005, "RT 624")])

    def test_changes_mark_the_first_year_and_each_switch(self):
        df = pd.DataFrame({"year": [2005, 2006, 2007, 2008],
                           "variety": ["A", "A", "B", "B"]})
        self.assertEqual(variety_transitions(df), [(2005, "A"), (2007, "B")])

    def test_missing_or_empty_variety_column_yields_no_markers(self):
        self.assertEqual(variety_transitions(pd.DataFrame({"year": [2005]})), [])
        df = pd.DataFrame({"year": [2005, 2006], "variety": [None, None]})
        self.assertEqual(variety_transitions(df), [])

    def test_dominant_variety_per_year_wins_ties_aside(self):
        # two rows say "A", one says "B" in 2005 -> the year's marker is "A"
        df = pd.DataFrame({"year": [2005, 2005, 2005], "variety": ["A", "A", "B"]})
        self.assertEqual(variety_transitions(df), [(2005, "A")])


class SaveFigureTests(unittest.TestCase):
    def test_save_creates_file_and_parent_dirs_and_returns_path(self):
        use_headless()
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "nested", "figure.png")  # parent dir does not exist yet
            returned = save_figure(fig, target)
            self.assertEqual(returned, target)
            self.assertTrue(os.path.exists(target))
            self.assertGreater(os.path.getsize(target), 0)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
