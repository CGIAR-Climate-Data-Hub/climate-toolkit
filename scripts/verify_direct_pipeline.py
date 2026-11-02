"""Opt-in live verification of the complete credential-free historical pipeline.

Uses a deliberately short validation baseline, not a scientific climate normal.
The first run may reuse existing toolkit caches; the second forbids provider opens.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="outputs/direct_pipeline_verification")
    args = parser.parse_args()
    import climate_toolkit as ct
    from climate_toolkit.fetch_data import direct_cloud

    root = Path(args.output_dir)
    options = dict(
        name="Nairobi",
        location_coord=(-1.286, 36.817),
        source="paired",
        precip_source="chirps_v3_daily_rnl",
        temp_source="chirts_era5",
        start_year=2020,
        end_year=2020,
        climatology_baseline=(2019, 2020),
        fixed_season="03-01:05-31",
        crop_name="maize",
        run_compare_sources=True,
        compare_sources_list=["paired", "chirps_v3_daily_rnl", "chirts_era5"],
        run_compare_periods=True,
        baseline_start=2019,
        baseline_end=2019,
        focal_year=2020,
        output_dir=str(root),
        allow_gee=False,
        workers=2,
        verbose=False,
        raise_on_error=True,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden provider/authentication call during verification")

    with patch("ee.Initialize", forbidden), patch("ee.Authenticate", forbidden):
        start = time.monotonic()
        result = ct.run_pipeline(**options)
        first_seconds = time.monotonic() - start
        with patch.object(direct_cloud, "open_provider", forbidden):
            start = time.monotonic()
            warm = ct.run_pipeline(**options)
            warm_seconds = time.monotonic() - start
    site = result.site_results[0]
    assert not result.errors and not warm.errors
    assert site.raw_fetch.equals(warm.site_results[0].raw_fetch)
    expected = {"chirps_v3_daily_rnl", "chirts_era5"}
    for provenance in (
        site.raw_fetch.attrs["data_provenance"],
        site.long_term_climatology["data_provenance"],
        site.climate_statistics["data_provenance"],
        site.hazards["data_provenance"],
        site.period_comparison["data_provenance"]["baseline"],
        site.period_comparison["data_provenance"]["focal"],
    ):
        assert {entry["source"] for entry in provenance} == expected
    bundle = site.climate_statistics["human_heat_bundle"]
    assert bundle["temperature_source"] == "chirts_era5"
    assert all(
        bundle[key] is None
        for key in ("humidity_source", "dewpoint_source", "wind_source", "solar_source")
    )
    record = {
        "measured_utc": datetime.now(timezone.utc).isoformat(),
        "first_run_seconds": first_seconds,
        "warm_seconds": warm_seconds,
        "cache_note": "Existing toolkit cache may be reused; not a clean cold-cache benchmark.",
        "status": site.status,
        "steps": site.completed_steps,
        "rows": len(site.raw_fetch),
        "climatology_years": site.long_term_climatology["period"]["years_with_data"],
        "sources": sorted(expected),
        "provenance": site.raw_fetch.attrs["data_provenance"],
        "gee_calls": 0,
        "warm_provider_calls": 0,
        "cached_values_equal": True,
        "report_directory": str(root),
    }
    (root / "verification.json").write_text(json.dumps(record, indent=2))
    print(
        json.dumps({key: value for key, value in record.items() if key != "provenance"}, indent=2)
    )


if __name__ == "__main__":
    main()
