"""End-to-end convenience wrapper: :func:`run_pipeline`.

Chains the toolkit's building blocks into a single call so workshop
participants and new users can run a full climate + crop-hazard workflow for one
or many sites without manually forwarding results between functions:

    fetch_climate_data
        -> long-term climatology (WMO 1991-2020 baseline by default)
        -> compare_climate_sources   (optional)
        -> analyze_climate_statistics
        -> evaluate_hazards          (when a crop is given)
        -> compare_climate_periods   (optional)

Each per-site step is wrapped so one failing site never aborts the batch; raw
intermediate results and compact headline metrics are both returned.

Example
-------
>>> import climate_toolkit as ct
>>> result = ct.run_pipeline(
...     name="Nairobi", location_coord=(-1.286, 36.817),
...     start_year=2019, end_year=2020, source="nasa_power",
...     fixed_season="03-01:05-31", crop_name="maize",
... )
>>> result.summary          # one headline row per site (pandas DataFrame)
>>> result.site_results[0].climate_statistics   # full nested result
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Canonical building blocks (imported here so tests can patch them on this
# module, and so the chain does not depend on the lazy top-level exports).
from .fetch_data.fetch_data import fetch_data as fetch_climate_data
from .climatology.long_term_climatology import calculate_climatology
from .compare_datasets.compare_datasets import compare_sources as compare_climate_sources
from .climate_statistics.statistics import analyze_climate_statistics
from .calculate_hazards.hazards import calculate_hazards as evaluate_hazards
from .compare_periods.periods import compare as compare_climate_periods

# WMO-recommended standard climate-normal baseline.
DEFAULT_CLIMATOLOGY_BASELINE: Tuple[int, int] = (1991, 2020)


@dataclass
class SitePipelineResult:
    """All outputs (and status) for a single site."""

    name: Optional[str]
    lat: float
    lon: float
    status: str = "queued"
    error: Optional[str] = None
    completed_steps: List[str] = field(default_factory=list)
    raw_fetch: Optional[pd.DataFrame] = None
    long_term_climatology: Optional[Dict[str, Any]] = None
    source_comparison: Optional[Any] = None
    climate_statistics: Optional[Dict[str, Any]] = None
    hazards: Optional[Dict[str, Any]] = None
    period_comparison: Optional[Dict[str, Any]] = None
    headline: Dict[str, Any] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Aggregated result across all sites."""

    site_results: List[SitePipelineResult]
    summary: pd.DataFrame
    metadata: Dict[str, Any]
    errors: List[Dict[str, Any]]


def _coerce_sites(
    location_coord: Optional[Tuple[float, float]],
    name: Optional[str],
    sites: Optional[List[Dict[str, Any]]],
    sites_csv: Optional[str | Path],
    site_table: Optional[pd.DataFrame],
) -> List[Dict[str, Any]]:
    """Normalize the various site inputs into a list of row dicts.

    Every row has at least ``name``, ``lat``, ``lon``; per-site overrides such
    as ``crop_name``, ``start_year``, ``end_year``, ``date_from``, ``date_to``
    are passed through when present.
    """
    if site_table is None and sites_csv is not None:
        site_table = pd.read_csv(sites_csv)
    if site_table is not None:
        sites = site_table.to_dict(orient="records")

    if sites:
        rows = []
        for i, s in enumerate(sites):
            row = dict(s)
            if "lat" not in row or "lon" not in row:
                raise ValueError(f"site {i} is missing 'lat'/'lon': {s!r}")
            row.setdefault("name", row.get("site_id") or f"site_{i + 1}")
            rows.append(row)
        return rows

    if location_coord is not None:
        return [{"name": name or "site_1", "lat": location_coord[0], "lon": location_coord[1]}]

    raise ValueError(
        "Provide one of: location_coord, sites, sites_csv, or site_table."
    )


def _timed(step_fn):
    start = time.perf_counter()
    result = step_fn()
    return result, round(time.perf_counter() - start, 2)


def _build_headline(site: SitePipelineResult, source: str) -> Dict[str, Any]:
    """Compact, first-glance metrics pulled defensively from the full results."""
    head: Dict[str, Any] = {
        "name": site.name,
        "lat": site.lat,
        "lon": site.lon,
        "status": site.status,
        "source": source,
    }
    stats = site.climate_statistics or {}
    seasons = stats.get("season_statistics") or []
    if seasons:
        head["n_seasons"] = len(seasons)
        last = seasons[-1]
        head["last_season_rain_mm"] = (last.get("precipitation") or {}).get("total_mm")
        head["last_season_WRSI"] = (last.get("water_balance") or {}).get("WRSI")
        head["last_season_NDWS"] = (last.get("water_balance") or {}).get("NDWS")
    ltm = site.long_term_climatology or {}
    if ltm:
        head["climatology_years"] = ltm.get("n_years") or ltm.get("years")
    hz = site.hazards or {}
    he = hz.get("hazard_evaluation") if isinstance(hz, dict) else None
    if isinstance(he, dict):
        head["hazard_statuses"] = {
            k: v.get("status") if isinstance(v, dict) else v
            for k, v in he.items()
            if k in {"NTx35", "NTx40", "NDD", "NDWS", "WRSI"}
        } or None
    return head


def run_pipeline(
    *,
    location_coord: Optional[Tuple[float, float]] = None,
    name: Optional[str] = None,
    sites: Optional[List[Dict[str, Any]]] = None,
    sites_csv: Optional[str | Path] = None,
    site_table: Optional[pd.DataFrame] = None,
    source: str = "nasa_power",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    fixed_season: Optional[str] = None,
    crop_name: Optional[str] = None,
    model: Optional[str] = None,
    scenario: Optional[str] = None,
    climatology_baseline: Tuple[int, int] = DEFAULT_CLIMATOLOGY_BASELINE,
    run_climatology: bool = True,
    run_compare_sources: bool = False,
    compare_sources_list: Optional[List[str]] = None,
    run_compare_periods: bool = False,
    baseline_start: Optional[int] = None,
    baseline_end: Optional[int] = None,
    focal_year: Optional[int] = None,
    output_dir: Optional[str] = None,
    ee_project_id: Optional[str] = None,
    workers: int = 1,
    verbose: bool = True,
    raise_on_error: bool = False,
) -> PipelineResult:
    """Run the end-to-end climate + crop-hazard workflow for one or many sites.

    See the module docstring for the step order. Returns a :class:`PipelineResult`
    with per-site :class:`SitePipelineResult` entries, a headline ``summary``
    DataFrame (one row per site), run ``metadata``, and a list of ``errors``.

    Parameters are grouped as: site inputs (``location_coord`` / ``sites`` /
    ``sites_csv`` / ``site_table``), the analysis window (``start_year`` /
    ``end_year`` or ``date_from`` / ``date_to``), configuration (``source``,
    ``fixed_season``, ``crop_name``, ``model``, ``scenario``), optional steps
    (``run_compare_sources``, ``run_compare_periods``), and controls
    (``workers``, ``verbose``, ``raise_on_error``).
    """
    rows = _coerce_sites(location_coord, name, sites, sites_csv, site_table)
    site_results: List[SitePipelineResult] = []
    errors: List[Dict[str, Any]] = []

    for row in rows:
        site = SitePipelineResult(name=row.get("name"), lat=float(row["lat"]), lon=float(row["lon"]))
        coord = (site.lat, site.lon)
        # Per-site overrides fall back to the call-level defaults.
        s_year = row.get("start_year", start_year)
        e_year = row.get("end_year", end_year)
        d_from = row.get("date_from", date_from) or (f"{s_year}-01-01" if s_year else None)
        d_to = row.get("date_to", date_to) or (f"{e_year}-12-31" if e_year else None)
        crop = row.get("crop_name", crop_name)

        if verbose:
            print(f"[{site.name}] starting pipeline ({coord})")

        try:
            # 1) Fetch daily climate data.
            if d_from and d_to:
                site.status = "fetching"
                df, dt = _timed(lambda: fetch_climate_data(
                    source=source, location_coord=coord,
                    date_from=date.fromisoformat(d_from), date_to=date.fromisoformat(d_to),
                    model=model, scenario=scenario, verbose=False,
                ))
                site.raw_fetch, site.timings["fetch"] = df, dt
                site.completed_steps.append("fetch")

            # 2) Long-term climatology (WMO baseline by default), surfaced early.
            if run_climatology:
                site.status = "climatology"
                cb0, cb1 = climatology_baseline
                clim, dt = _timed(lambda: calculate_climatology(
                    location_coord=coord, start_year=cb0, end_year=cb1,
                    source=source, model=model, scenario=scenario, verbose=False,
                ))
                site.long_term_climatology, site.timings["climatology"] = clim, dt
                site.completed_steps.append("climatology")

            # 3) Cross-source comparison (optional).
            if run_compare_sources and compare_sources_list:
                site.status = "source_comparison"
                cmp, dt = _timed(lambda: compare_climate_sources(
                    sources=compare_sources_list, lat=site.lat, lon=site.lon,
                    start=d_from, end=d_to, output_dir=output_dir or "./outputs",
                    nex_model=model, nex_scenario=scenario or "ssp245",
                ))
                site.source_comparison, site.timings["source_comparison"] = cmp, dt
                site.completed_steps.append("source_comparison")

            # 4) Seasonal statistics.
            if s_year and e_year:
                site.status = "analyzing_statistics"
                stats, dt = _timed(lambda: analyze_climate_statistics(
                    location_coord=coord, start_year=int(s_year), end_year=int(e_year),
                    source=source, fixed_season=fixed_season, crop_name=crop,
                    model=model, scenario=scenario, verbose=False,
                ))
                site.climate_statistics, site.timings["statistics"] = stats, dt
                site.completed_steps.append("statistics")

            # 5) Crop hazards (only when a crop is specified).
            if crop and d_from and d_to:
                site.status = "evaluating_hazards"
                hz, dt = _timed(lambda: evaluate_hazards(
                    crop_name=crop, location_coord=coord,
                    date_from=d_from, date_to=d_to, source=source,
                    fixed_season=fixed_season,
                ))
                site.hazards, site.timings["hazards"] = hz, dt
                site.completed_steps.append("hazards")

            # 6) Focal-year vs baseline (optional).
            if run_compare_periods and baseline_start and baseline_end and focal_year:
                site.status = "compare_periods"
                per, dt = _timed(lambda: compare_climate_periods(
                    location=coord, baseline_start=baseline_start, baseline_end=baseline_end,
                    focal_year=focal_year, source=source, fixed_season=fixed_season,
                    crop_name=crop,
                ))
                site.period_comparison, site.timings["period_comparison"] = per, dt
                site.completed_steps.append("period_comparison")

            site.status = "completed"
        except Exception as exc:  # one bad site must not abort the batch
            site.status = "failed"
            site.error = f"{type(exc).__name__}: {exc}"
            errors.append({"name": site.name, "lat": site.lat, "lon": site.lon, "error": site.error})
            if verbose:
                print(f"[{site.name}] FAILED: {site.error}")
            if raise_on_error:
                raise

        site.headline = _build_headline(site, source)
        site_results.append(site)

    summary = pd.DataFrame([s.headline for s in site_results])
    metadata = {
        "n_sites": len(site_results),
        "n_failed": len(errors),
        "source": source,
        "climatology_baseline": list(climatology_baseline),
        "steps": {
            "climatology": run_climatology,
            "compare_sources": run_compare_sources,
            "compare_periods": run_compare_periods,
        },
    }
    return PipelineResult(site_results=site_results, summary=summary, metadata=metadata, errors=errors)
