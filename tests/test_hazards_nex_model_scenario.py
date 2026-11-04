"""NEX-GDDP model/scenario surface for calculate_hazards (issue #175, part 1).

`calculate_hazards()` now accepts `model` / `scenario` and threads them to every
climate fetch, and defaults `scenario` to "historical" for NEX-GDDP windows that
end before 2015 (so pre-2015 hazard windows stop failing against the ssp245
source default). These tests lock that in without hitting Earth Engine.
"""

import sys
import unittest
from unittest.mock import patch

from climate_toolkit.calculate_hazards import hazards


class _FetchCaptured(Exception):
    """Raised by the mocked fetch so we stop as soon as it is called."""


def _run_fixed(date_from, date_to, **kwargs):
    """Call calculate_hazards far enough to reach the fixed-season prefetch.

    The prefetch is mocked to capture its kwargs and then abort, so no network
    or Earth Engine access happens.
    """
    captured = {}

    def _fake_fetch(*args, **kw):
        captured.update(kw)
        raise _FetchCaptured

    with patch.object(hazards, "resolve_thi_profile", return_value={"label": "test"}), \
         patch.object(hazards, "fetch_and_analyze_years_fixed", side_effect=_fake_fetch):
        try:
            hazards.calculate_hazards(
                "maize", (-0.776, 37.66), date_from, date_to,
                fixed_season="10-17:01-09", **kwargs,
            )
        except _FetchCaptured:
            pass
    return captured


class NexScenarioDefaultTests(unittest.TestCase):
    def test_pre_2015_window_defaults_scenario_to_historical(self):
        captured = _run_fixed("2005-01-01", "2006-12-31", source="nex_gddp")
        self.assertEqual("historical", captured.get("scenario"))

    def test_post_2015_window_leaves_scenario_unset(self):
        captured = _run_fixed("2018-01-01", "2020-12-31", source="nex_gddp")
        self.assertIsNone(captured.get("scenario"))

    def test_explicit_scenario_is_never_overridden(self):
        captured = _run_fixed("2005-01-01", "2006-12-31", source="nex_gddp",
                              scenario="ssp245")
        self.assertEqual("ssp245", captured.get("scenario"))

    def test_model_is_threaded_through(self):
        captured = _run_fixed("2005-01-01", "2006-12-31", source="nex_gddp",
                              model="GFDL-ESM4")
        self.assertEqual("GFDL-ESM4", captured.get("model"))

    def test_non_nex_source_is_untouched(self):
        # the historical default only applies to nex_gddp
        captured = _run_fixed("2005-01-01", "2006-12-31", source="era5_land")
        self.assertIsNone(captured.get("scenario"))


class HazardsCliModelScenarioTests(unittest.TestCase):
    def test_cli_passes_model_and_scenario(self):
        with patch.object(
            sys, "argv",
            [
                "hazards.py", "maize", "--location=-0.776,37.66",
                "--date-from", "2005-01-01", "--date-to", "2006-12-31",
                "--source", "nex_gddp",
                "--model", "GFDL-ESM4", "--scenario", "historical",
            ],
        ), patch.object(hazards, "calculate_hazards", return_value={}) as hz_mock, \
                patch.object(hazards, "print_hazard_results"):
            rc = hazards.main()
        self.assertEqual(0, rc)
        self.assertEqual("GFDL-ESM4", hz_mock.call_args.kwargs["model"])
        self.assertEqual("historical", hz_mock.call_args.kwargs["scenario"])


if __name__ == "__main__":
    unittest.main()
