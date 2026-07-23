"""Unit tests for the run_pipeline() end-to-end wrapper.

The building-block functions are mocked so these tests are fast, deterministic,
and credential-free — they verify orchestration (step order, batching, defaults,
error isolation), not the underlying analytics.
"""

import unittest
from unittest import mock

import pandas as pd

import climate_toolkit as ct
import climate_toolkit.pipeline as pipeline


def _fake_stats(*args, **kwargs):
    return {
        "season_statistics": [
            {
                "year": kwargs.get("end_year", 2020),
                "precipitation": {"total_mm": 300.0},
                "water_balance": {"WRSI": 60.0, "NDWS": 40},
            }
        ]
    }


def _fake_hazards(*args, **kwargs):
    return {"hazard_evaluation": {"NDWS": {"status": "low"}, "WRSI": {"status": "ok"}}}


def _patch_blocks(**overrides):
    """Patch all building blocks on the pipeline module with harmless fakes."""
    defaults = {
        "fetch_climate_data": mock.DEFAULT,
        "calculate_climatology": mock.DEFAULT,
        "analyze_climate_statistics": mock.DEFAULT,
        "evaluate_hazards": mock.DEFAULT,
        "compare_climate_sources": mock.DEFAULT,
        "compare_climate_periods": mock.DEFAULT,
    }
    defaults.update(overrides)
    return mock.patch.multiple(pipeline, **defaults)


class RunPipelineTests(unittest.TestCase):
    def test_exported_from_package(self):
        self.assertIn("run_pipeline", ct.__all__)
        self.assertTrue(callable(ct.run_pipeline))

    def test_single_site_happy_path(self):
        with _patch_blocks() as m:
            m["fetch_climate_data"].return_value = pd.DataFrame({"date": [1], "precip": [2]})
            m["calculate_climatology"].return_value = {"n_years": 30}
            m["analyze_climate_statistics"].side_effect = _fake_stats
            m["evaluate_hazards"].side_effect = _fake_hazards

            result = ct.run_pipeline(
                name="Nairobi", location_coord=(-1.286, 36.817),
                start_year=2019, end_year=2020, source="nasa_power",
                fixed_season="03-01:05-31", crop_name="maize", verbose=False,
            )

        self.assertEqual(len(result.site_results), 1)
        site = result.site_results[0]
        self.assertEqual(site.status, "completed")
        self.assertEqual(site.completed_steps, ["fetch", "climatology", "statistics", "hazards"])
        self.assertEqual(site.headline["last_season_rain_mm"], 300.0)
        self.assertEqual(len(result.summary), 1)
        self.assertEqual(result.metadata["n_failed"], 0)

    def test_climatology_baseline_defaults_to_1991_2020(self):
        with _patch_blocks() as m:
            m["analyze_climate_statistics"].side_effect = _fake_stats
            ct.run_pipeline(
                location_coord=(-1.286, 36.817), start_year=2019, end_year=2020,
                source="nasa_power", verbose=False,
            )
            _, kwargs = m["calculate_climatology"].call_args
        self.assertEqual((kwargs["start_year"], kwargs["end_year"]), (1991, 2020))

    def test_batch_via_sites_list(self):
        with _patch_blocks() as m:
            m["analyze_climate_statistics"].side_effect = _fake_stats
            result = ct.run_pipeline(
                sites=[
                    {"name": "A", "lat": -1.0, "lon": 36.0},
                    {"name": "B", "lat": -2.0, "lon": 37.0},
                ],
                start_year=2019, end_year=2020, source="nasa_power",
                run_climatology=False, verbose=False,
            )
        self.assertEqual(len(result.site_results), 2)
        self.assertEqual(list(result.summary["name"]), ["A", "B"])

    def test_compare_sources_path(self):
        with _patch_blocks() as m:
            m["analyze_climate_statistics"].side_effect = _fake_stats
            m["compare_climate_sources"].return_value = {"ok": True}
            result = ct.run_pipeline(
                location_coord=(-1.0, 36.0), start_year=2019, end_year=2020,
                source="nasa_power", run_climatology=False,
                run_compare_sources=True, compare_sources_list=["nasa_power", "agera_5"],
                verbose=False,
            )
        self.assertTrue(m["compare_climate_sources"].called)
        self.assertEqual(result.site_results[0].source_comparison, {"ok": True})
        self.assertIn("source_comparison", result.site_results[0].completed_steps)

    def test_error_isolation_one_site_fails(self):
        def stats_side_effect(*args, **kwargs):
            if kwargs.get("location_coord") == (-2.0, 37.0):
                raise RuntimeError("boom")
            return _fake_stats(*args, **kwargs)

        with _patch_blocks() as m:
            m["analyze_climate_statistics"].side_effect = stats_side_effect
            result = ct.run_pipeline(
                sites=[
                    {"name": "good", "lat": -1.0, "lon": 36.0},
                    {"name": "bad", "lat": -2.0, "lon": 37.0},
                ],
                start_year=2019, end_year=2020, source="nasa_power",
                run_climatology=False, verbose=False,
            )
        statuses = {s.name: s.status for s in result.site_results}
        self.assertEqual(statuses, {"good": "completed", "bad": "failed"})
        self.assertEqual(len(result.errors), 1)
        self.assertIn("boom", result.errors[0]["error"])

    def test_raise_on_error_propagates(self):
        with _patch_blocks() as m:
            m["analyze_climate_statistics"].side_effect = RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                ct.run_pipeline(
                    location_coord=(-1.0, 36.0), start_year=2019, end_year=2020,
                    source="nasa_power", run_climatology=False,
                    raise_on_error=True, verbose=False,
                )

    def test_requires_a_site_input(self):
        with self.assertRaises(ValueError):
            ct.run_pipeline(start_year=2019, end_year=2020, source="nasa_power", verbose=False)


if __name__ == "__main__":
    unittest.main()
