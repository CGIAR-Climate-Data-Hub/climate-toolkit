"""
NEX-GDDP Ensemble Period Comparison
Runs the same future-vs-baseline comparison shape as periods.compare(), once per NEX-GDDP CMIP6 model, then averages the per-model results into a single
ensemble comparison.
Difference from periods.compare(): future is a multi-year *period* (e.g. 2040-2060) rather than a single year. Both sides are annualised before the
diff, so 'future_avg' and 'baseline_avg' are per-year averages over their respective periods.

Both baseline and future data come from NEX-GDDP, so each model is compared against its own historical run (the standard model-bias-removing convention).

Output mirrors periods.compare()'s four-section shape, with each leaf replaced by ensemble means + model spread.
    
The ensemble result IS the architecture's "Baseline LTM vs Future LTM" comparison
(Δ = future_avg − baseline_avg = future − baseline). 
When --focal-year/--focal-source are supplied, the observed year is diffed against both ensemble LTMs, completing the
three season-summary comparisons (period concepts: historical=baseline LTM, future=projected LTM, focal=observed single year):
    baseline LTM vs future LTM  -> the ensemble result  (Baseline LTM vs Future LTM)
    focal vs baseline LTM        -> focal_vs_baseline    (Δ = focal − baseline_ltm)
    focal vs future LTM          -> focal_vs_future      (Δ = focal − future_ltm)
"""
import sys
import os
import math
import json
import logging
import argparse
import io
import statistics as pystat
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from datetime import datetime, date
from time import perf_counter
from typing import Dict, Any, Tuple, List, Optional

import pandas as pd

from climate_tookit.climate_statistics.statistics import analyze_climate_statistics
from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS as NEX_GDDP_MODELS,
    POLICY_PROFILE_CHOICES,
    POLICY_PROFILE_HELP,
    _validate_period_against_scenario,
    default_ensemble_models_for_location,
    policy_runtime_messages,
    resolve_ensemble_policy_for_location,
)
from climate_tookit.compare_periods.periods import (
    _annualize, _agg_seasons, _round,
    _diff_raw, _diff_block, _percent_change, _fmt_pct,
    _auto_season_count_guard,
    _compare_season_detection_summary,
    _compare_season_detection_guard,
    _diff_spei,
    _diff_spi,
    _filter_overall_statistics_for_period_compare,
    _seasonal_spei_period_block,
    _merge_seasonal_spei_into_summary,
    _merge_seasonal_spei_into_diff,
    _merge_period_methodology,
    _print_methodology_summary,
    _print_season_detection_summary,
    PRECIP_ONLY, SUPPORTED,
)
from climate_tookit.crop_calendar.ggcmi import CALENDAR_SYSTEM_CHOICES, resolve_calendar_preset

SSP_SCENARIOS: List[str] = ["ssp126", "ssp245", "ssp585", "historical"]
SCENARIO_ALIASES: Dict[str, str] = {
    "SSP1-2.6": "ssp126", "SSP2-4.5": "ssp245", "SSP5-8.5": "ssp585",
    "ssp126":   "ssp126", "ssp245":   "ssp245", "ssp585":   "ssp585",
    "historical": "historical",
}

def _normalize_scenario(s: str) -> Optional[str]:
    """Map any accepted alias to the canonical scenario string, else None."""
    return SCENARIO_ALIASES.get(s.strip()) if isinstance(s, str) else None

# helpers
def _is_num(x: Any) -> bool:
    return (isinstance(x, (int, float))
            and not isinstance(x, bool)
            and not (isinstance(x, float) and math.isnan(x)))

def _percentile(data: List[float], p: float) -> Optional[float]:
    if not data:
        return None
    s = sorted(data)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return round(s[lo], 2)
    return round(s[lo] + (idx - lo) * (s[hi] - s[lo]), 2)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{sec:02d}s"


def _round_if_num(value: Any, digits: int = 3) -> Optional[float]:
    return round(float(value), digits) if _is_num(value) else None


def _extract_stats_timing(stats: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    timing = (stats or {}).get("timing") or {}
    return {
        "fetch_seconds": _round_if_num(timing.get("fetch_seconds")),
        "prep_seconds": _round_if_num(timing.get("prep_seconds")),
        "season_detection_seconds": _round_if_num(timing.get("season_detection_seconds")),
        "season_reduction_seconds": _round_if_num(timing.get("season_reduction_seconds")),
        "season_reduction_core_seconds": _round_if_num(timing.get("season_reduction_core_seconds")),
        "season_reduction_raw_seconds": _round_if_num(timing.get("season_reduction_raw_seconds")),
        "season_reduction_overall_seconds": _round_if_num(timing.get("season_reduction_overall_seconds")),
        "season_reduction_eto_seconds": _round_if_num(timing.get("season_reduction_eto_seconds")),
        "spei_seconds": _round_if_num(timing.get("spei_seconds")),
        "total_seconds": _round_if_num(timing.get("total_seconds")),
    }


def _summarize_runtime_stage(values: List[float]) -> Dict[str, Optional[float]]:
    clean = [float(v) for v in values if _is_num(v)]
    if not clean:
        return {"mean_seconds": None, "median_seconds": None, "max_seconds": None}
    return {
        "mean_seconds": round(pystat.mean(clean), 3),
        "median_seconds": round(pystat.median(clean), 3),
        "max_seconds": round(max(clean), 3),
    }


def _build_runtime_summary(
    per_model: List[Dict[str, Any]],
    failed: List[Dict[str, str]],
    total_elapsed: float,
) -> Dict[str, Any]:
    model_totals = [r.get("_elapsed_seconds", 0.0) for r in per_model if _is_num(r.get("_elapsed_seconds"))]
    baseline_totals = [
        r.get("timing_breakdown", {}).get("baseline_total_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_totals = [
        r.get("timing_breakdown", {}).get("future_total_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    compare_totals = [
        r.get("timing_breakdown", {}).get("compare_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_fetch = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("fetch_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_fetch = [
        r.get("timing_breakdown", {}).get("future", {}).get("fetch_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_prep = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("prep_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_prep = [
        r.get("timing_breakdown", {}).get("future", {}).get("prep_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_detect = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_detection_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_detect = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_detection_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_reduce = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_reduction_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_reduce = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_reduction_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_reduce_core = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_reduction_core_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_reduce_core = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_reduction_core_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_reduce_raw = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_reduction_raw_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_reduce_raw = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_reduction_raw_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_reduce_overall = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_reduction_overall_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_reduce_overall = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_reduction_overall_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    baseline_reduce_eto = [
        r.get("timing_breakdown", {}).get("baseline", {}).get("season_reduction_eto_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]
    future_reduce_eto = [
        r.get("timing_breakdown", {}).get("future", {}).get("season_reduction_eto_seconds")
        for r in per_model
        if isinstance(r.get("timing_breakdown"), dict)
    ]

    slowest_models = [
        {
            "model": r.get("_model"),
            "total_seconds": round(float(r.get("_elapsed_seconds", 0.0)), 3),
            "baseline_total_seconds": _round_if_num((r.get("timing_breakdown") or {}).get("baseline_total_seconds")),
            "future_total_seconds": _round_if_num((r.get("timing_breakdown") or {}).get("future_total_seconds")),
            "compare_seconds": _round_if_num((r.get("timing_breakdown") or {}).get("compare_seconds")),
        }
        for r in sorted(
            [row for row in per_model if _is_num(row.get("_elapsed_seconds"))],
            key=lambda row: float(row.get("_elapsed_seconds", 0.0)),
            reverse=True,
        )[:3]
    ]
    return {
        "models_ok": len(per_model),
        "models_failed": len(failed),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "mean_model_seconds": round(pystat.mean(model_totals), 3) if model_totals else None,
        "median_model_seconds": round(pystat.median(model_totals), 3) if model_totals else None,
        "slowest_models": slowest_models,
        "stage_summary": {
            "baseline_total": _summarize_runtime_stage(baseline_totals),
            "future_total": _summarize_runtime_stage(future_totals),
            "compare": _summarize_runtime_stage(compare_totals),
            "baseline_fetch": _summarize_runtime_stage(baseline_fetch),
            "future_fetch": _summarize_runtime_stage(future_fetch),
            "baseline_prep": _summarize_runtime_stage(baseline_prep),
            "future_prep": _summarize_runtime_stage(future_prep),
            "baseline_detection": _summarize_runtime_stage(baseline_detect),
            "future_detection": _summarize_runtime_stage(future_detect),
            "baseline_reduction": _summarize_runtime_stage(baseline_reduce),
            "future_reduction": _summarize_runtime_stage(future_reduce),
            "baseline_reduction_core": _summarize_runtime_stage(baseline_reduce_core),
            "future_reduction_core": _summarize_runtime_stage(future_reduce_core),
            "baseline_reduction_raw": _summarize_runtime_stage(baseline_reduce_raw),
            "future_reduction_raw": _summarize_runtime_stage(future_reduce_raw),
            "baseline_reduction_overall": _summarize_runtime_stage(baseline_reduce_overall),
            "future_reduction_overall": _summarize_runtime_stage(future_reduce_overall),
            "baseline_reduction_eto": _summarize_runtime_stage(baseline_reduce_eto),
            "future_reduction_eto": _summarize_runtime_stage(future_reduce_eto),
        },
    }


def _format_stage_stat(stage_summary: Dict[str, Any], key: str) -> str:
    block = (stage_summary or {}).get(key) or {}
    mean_seconds = block.get("mean_seconds")
    if not _is_num(mean_seconds):
        return "n/a"
    return _format_elapsed(float(mean_seconds))


def _print_runtime_summary(runtime_summary: Optional[Dict[str, Any]]) -> None:
    if not isinstance(runtime_summary, dict):
        return
    stage_summary = runtime_summary.get("stage_summary") or {}
    slowest = runtime_summary.get("slowest_models") or []
    slowest_text = ", ".join(
        f"{row.get('model')}({_format_elapsed(float(row.get('total_seconds', 0.0)))})"
        for row in slowest
        if row.get("model") and _is_num(row.get("total_seconds"))
    ) or "n/a"
    print("\n--- Runtime Summary ---")
    print(
        "  Models      : "
        f"ok={runtime_summary.get('models_ok', 0)} | "
        f"failed={runtime_summary.get('models_failed', 0)}"
    )
    print(
        "  Model time  : "
        f"mean={_format_elapsed(float(runtime_summary['mean_model_seconds'])) if _is_num(runtime_summary.get('mean_model_seconds')) else 'n/a'} | "
        f"median={_format_elapsed(float(runtime_summary['median_model_seconds'])) if _is_num(runtime_summary.get('median_model_seconds')) else 'n/a'} | "
        f"total={_format_elapsed(float(runtime_summary['total_elapsed_seconds'])) if _is_num(runtime_summary.get('total_elapsed_seconds')) else 'n/a'}"
    )
    print(
        "  Stage means : "
        f"baseline={_format_stage_stat(stage_summary, 'baseline_total')} | "
        f"future={_format_stage_stat(stage_summary, 'future_total')} | "
        f"compare={_format_stage_stat(stage_summary, 'compare')}"
    )
    print(
        "  Fetch/Prep  : "
        f"baseline_fetch={_format_stage_stat(stage_summary, 'baseline_fetch')} | "
        f"future_fetch={_format_stage_stat(stage_summary, 'future_fetch')} | "
        f"baseline_prep={_format_stage_stat(stage_summary, 'baseline_prep')} | "
        f"future_prep={_format_stage_stat(stage_summary, 'future_prep')}"
    )
    print(
        "  Detect/Red. : "
        f"baseline_detect={_format_stage_stat(stage_summary, 'baseline_detection')} | "
        f"future_detect={_format_stage_stat(stage_summary, 'future_detection')} | "
        f"baseline_reduce={_format_stage_stat(stage_summary, 'baseline_reduction')} | "
        f"future_reduce={_format_stage_stat(stage_summary, 'future_reduction')}"
    )
    print(
        "  Reduce det. : "
        f"base_core={_format_stage_stat(stage_summary, 'baseline_reduction_core')} | "
        f"fut_core={_format_stage_stat(stage_summary, 'future_reduction_core')} | "
        f"base_raw={_format_stage_stat(stage_summary, 'baseline_reduction_raw')} | "
        f"fut_raw={_format_stage_stat(stage_summary, 'future_reduction_raw')} | "
        f"base_overall={_format_stage_stat(stage_summary, 'baseline_reduction_overall')} | "
        f"fut_overall={_format_stage_stat(stage_summary, 'future_reduction_overall')} | "
        f"base_eto={_format_stage_stat(stage_summary, 'baseline_reduction_eto')} | "
        f"fut_eto={_format_stage_stat(stage_summary, 'future_reduction_eto')}"
    )
    print(f"  Slowest     : {slowest_text}")


_COMPACT_COMPARE_STATS_KWARGS = {
    "include_season_raw_summary": False,
    "include_season_overall_statistics": False,
    "include_ltm_season_summary": False,
}


def _run_stats_call(
    *,
    diagnostic_verbose: bool,
    **kwargs: Any,
) -> Dict[str, Any]:
    kwargs.setdefault("verbose", diagnostic_verbose)
    if diagnostic_verbose:
        return analyze_climate_statistics(**kwargs)
    with redirect_stdout(io.StringIO()):
        return analyze_climate_statistics(**kwargs)


def _build_compare_one_model_task(
    *,
    location: Tuple[float, float],
    baseline_start: int,
    baseline_end: int,
    future_start: int,
    future_end: int,
    fixed_season: Optional[str],
    model: str,
    scenario: str,
    crop_name: Optional[str],
    calendar_source: Optional[str],
    calendar_system: str,
    diagnostic_verbose: bool,
    spei_scale_months: Optional[int],
    spei_fit: str,
    spei_ref_start: Optional[str],
    spei_ref_end: Optional[str],
    spi_scale_months: Optional[int],
    spi_fit: str,
    spi_ref_start: Optional[str],
    spi_ref_end: Optional[str],
    suppress_child_stdout: bool,
) -> Dict[str, Any]:
    return {
        "location": location,
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "future_start": future_start,
        "future_end": future_end,
        "fixed_season": fixed_season,
        "model": model,
        "scenario": scenario,
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
        "diagnostic_verbose": diagnostic_verbose,
        "spei_scale_months": spei_scale_months,
        "spei_fit": spei_fit,
        "spei_ref_start": spei_ref_start,
        "spei_ref_end": spei_ref_end,
        "spi_scale_months": spi_scale_months,
        "spi_fit": spi_fit,
        "spi_ref_start": spi_ref_start,
        "spi_ref_end": spi_ref_end,
        "suppress_child_stdout": suppress_child_stdout,
    }


def _run_compare_one_model_task(task: Dict[str, Any]) -> Dict[str, Any]:
    started = perf_counter()
    model = task["model"]
    suppress_child_stdout = bool(task.get("suppress_child_stdout", False))
    compare_kwargs = {k: v for k, v in task.items() if k != "suppress_child_stdout"}
    try:
        if suppress_child_stdout:
            with redirect_stdout(io.StringIO()):
                result = _compare_one_model(**compare_kwargs)
        else:
            result = _compare_one_model(**compare_kwargs)
        elapsed = perf_counter() - started
        if "error" in result:
            return {
                "model": model,
                "ok": False,
                "error": result["error"],
                "elapsed_seconds": round(elapsed, 3),
                "timing_breakdown": result.get("timing_breakdown"),
            }
        result["_model"] = model
        result["_elapsed_seconds"] = round(elapsed, 3)
        return {
            "model": model,
            "ok": True,
            "result": result,
            "elapsed_seconds": round(elapsed, 3),
            "timing_breakdown": result.get("timing_breakdown"),
        }
    except Exception as exc:
        elapsed = perf_counter() - started
        return {
            "model": model,
            "ok": False,
            "error": str(exc),
            "elapsed_seconds": round(elapsed, 3),
            "timing_breakdown": None,
        }


def _print_model_progress(
    *,
    done: int,
    total: int,
    model: str,
    outcome: Dict[str, Any],
    run_started: float,
) -> None:
    elapsed = perf_counter() - run_started
    avg = elapsed / done if done else 0.0
    eta = avg * max(total - done, 0)
    status = "ok" if outcome.get("ok") else "failed"
    timing = outcome.get("timing_breakdown") or {}
    baseline = timing.get("baseline_total_seconds")
    future = timing.get("future_total_seconds")
    compare = timing.get("compare_seconds")
    message = (
        f"  [{done:02d}/{total:02d}] {model} | {status} | "
        f"baseline={_format_elapsed(float(baseline)) if _is_num(baseline) else 'n/a'} | "
        f"future={_format_elapsed(float(future)) if _is_num(future) else 'n/a'} | "
        f"compare={_format_elapsed(float(compare)) if _is_num(compare) else 'n/a'} | "
        f"model={_format_elapsed(float(outcome.get('elapsed_seconds', 0.0)))} | "
        f"total={_format_elapsed(elapsed)} | eta={_format_elapsed(eta)}"
    )
    if not outcome.get("ok") and outcome.get("error"):
        message += f" | error={outcome['error']}"
    print(message, flush=True)


def _execute_model_tasks(
    *,
    tasks: List[Dict[str, Any]],
    model_workers: int,
    verbose: bool,
    diagnostic_verbose: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], int, float]:
    per_model: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []
    total = len(tasks)
    effective_workers = max(1, min(int(model_workers), total)) if total else 1
    run_started = perf_counter()

    if verbose:
        mode = "parallel" if effective_workers > 1 else "serial"
        worker_suffix = f" | workers={effective_workers}" if effective_workers > 1 else ""
        print(f"  Execution : {mode}{worker_suffix}")
        if effective_workers > 1 and diagnostic_verbose:
            print(
                "  Note      : parallel workers suppress nested per-model diagnostics; "
                "use --model-workers 1 for deep debugging."
            )

    if effective_workers == 1:
        for done, task in enumerate(tasks, 1):
            outcome = _run_compare_one_model_task(task)
            if outcome.get("ok"):
                per_model.append(outcome["result"])
            else:
                failed.append({"model": outcome["model"], "error": outcome["error"]})
            if verbose:
                _print_model_progress(
                    done=done,
                    total=total,
                    model=outcome["model"],
                    outcome=outcome,
                    run_started=run_started,
                )
        return per_model, failed, effective_workers, perf_counter() - run_started

    future_map = {}
    try:
        with ProcessPoolExecutor(max_workers=effective_workers) as executor:
            for task in tasks:
                future = executor.submit(_run_compare_one_model_task, task)
                future_map[future] = task["model"]
            for done, future in enumerate(as_completed(future_map), 1):
                model = future_map[future]
                try:
                    outcome = future.result()
                except Exception as exc:
                    outcome = {
                        "model": model,
                        "ok": False,
                        "error": str(exc),
                        "elapsed_seconds": 0.0,
                    }
                if outcome.get("ok"):
                    per_model.append(outcome["result"])
                else:
                    failed.append({"model": outcome["model"], "error": outcome["error"]})
                if verbose:
                    _print_model_progress(
                        done=done,
                        total=total,
                        model=model,
                        outcome=outcome,
                        run_started=run_started,
                    )
    except (OSError, PermissionError) as exc:
        if verbose:
            print(
                "  Warning   : parallel model workers unavailable in this environment "
                f"({exc}); falling back to serial execution."
            )
        per_model = []
        failed = []
        effective_workers = 1
        for done, task in enumerate(tasks, 1):
            outcome = _run_compare_one_model_task(task)
            if outcome.get("ok"):
                per_model.append(outcome["result"])
            else:
                failed.append({"model": outcome["model"], "error": outcome["error"]})
            if verbose:
                _print_model_progress(
                    done=done,
                    total=total,
                    model=outcome["model"],
                    outcome=outcome,
                    run_started=run_started,
                )
    return per_model, failed, effective_workers, perf_counter() - run_started

def _spread(values: List[float]) -> Dict[str, Any]:
    """Cross-model spread for one numeric vector."""
    clean = [float(v) for v in values if _is_num(v)]
    if not clean:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None,
                "p10": None, "p90": None, "p17": None, "p83": None}
    return {
        "n":    len(clean),
        "mean": round(pystat.mean(clean), 2),
        "std":  round(pystat.stdev(clean), 2) if len(clean) > 1 else 0.0,
        "min":  round(min(clean), 2),
        "max":  round(max(clean), 2),
        "p10":  _percentile(clean, 10),
        "p90":  _percentile(clean, 90),
        "p17":  _percentile(clean, 17),
        "p83":  _percentile(clean, 83),
    }

def _filter_models(location_coord: Tuple[float, float],
                   models: Optional[List[str]],
                   exclude_models: Optional[List[str]],
                   policy_profile: Optional[str] = None) -> List[str]:
    return default_ensemble_models_for_location(
        location_coord,
        models=models,
        exclude_models=exclude_models,
        policy_profile=policy_profile,
    )


def _resolve_models_and_policy(
    location_coord: Tuple[float, float],
    models: Optional[List[str]],
    exclude_models: Optional[List[str]],
    policy_profile: Optional[str] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    if policy_profile is None:
        active = _filter_models(location_coord, models, exclude_models)
    else:
        active = default_ensemble_models_for_location(
            location_coord,
            models=models,
            exclude_models=exclude_models,
            policy_profile=policy_profile,
        )
    policy = resolve_ensemble_policy_for_location(
        location_coord,
        models=models,
        exclude_models=exclude_models,
        policy_profile=policy_profile,
    )
    if list(policy.get("models", [])) == list(active):
        return active, policy

    notes = list(policy.get("notes") or [])
    notes.append(
        "Active model list adjusted after policy resolution by downstream filtering/override."
    )
    policy = {
        **policy,
        "models": list(active),
        "notes": notes,
    }
    return active, policy

def _validate_nex_periods(
    baseline_start: int,
    baseline_end: int,
    future_start: int,
    future_end: int,
    scenario: str,
) -> Optional[str]:
    """NEX-GDDP baseline-vs-future compare needs multi-year periods on both sides."""
    if baseline_end < baseline_start:
        return "baseline_end must be >= baseline_start"
    if future_end < future_start:
        return "future_end must be >= future_start"

    baseline_years = baseline_end - baseline_start + 1
    future_years = future_end - future_start + 1
    if baseline_years < 2 or future_years < 2:
        return (
            "NEX-GDDP baseline-vs-future comparison requires multi-year periods on both sides. "
            f"Got baseline={baseline_start}-{baseline_end} ({baseline_years} year(s)) and "
            f"future={future_start}-{future_end} ({future_years} year(s)). "
            "Single-year NEX-GDDP baseline/future comparisons are not allowed."
        )
    try:
        _validate_period_against_scenario(
            "historical",
            date(baseline_start, 1, 1),
            date(baseline_end, 12, 31),
        )
    except ValueError as exc:
        return (
            f"Invalid NEX-GDDP baseline period {baseline_start}-{baseline_end}: {exc} "
            "Use historical baseline years ending no later than 2014."
        )
    try:
        _validate_period_against_scenario(
            str(scenario),
            date(future_start, 1, 1),
            date(future_end, 12, 31),
        )
    except ValueError as exc:
        return (
            f"Invalid NEX-GDDP future period {future_start}-{future_end} for scenario={scenario}: {exc}"
        )
    return None


def _has_year_crossing_window(fixed_season: Optional[str]) -> bool:
    if not fixed_season:
        return False
    for raw in str(fixed_season).split(","):
        token = raw.strip()
        if not token:
            continue
        start_str, end_str = token.split(":")
        start_md = tuple(int(x) for x in start_str.split("-", 1))
        end_md = tuple(int(x) for x in end_str.split("-", 1))
        if end_md < start_md:
            return True
    return False

# Local replacement for periods._diff_annual: future is now a period, not a year.
def _diff_annual_period(future_ann:    Dict[str, Dict],
                        baseline_ann: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Diff annual_summary as period-vs-period (rather than year-vs-period).
    Returns the same 'annual_rain_mm' shape periods._diff_annual produces ({future, baseline_avg, diff, pct}) so the cross-model aggregator can stay
    unchanged. For humid status, single-year True/False doesn't apply, so we return raw counts of humid years and total years on each side; the
    aggregator sums them across models.
    """
    def _agg(ann_map: Dict[str, Dict]) -> Tuple[Optional[float], int, int]:
        rains = [v["annual_rain_mm"] for v in ann_map.values()
                 if v and _is_num(v.get("annual_rain_mm"))]
        humid = sum(1 for v in ann_map.values() if v and v.get("is_humid"))
        total = sum(1 for v in ann_map.values() if v)
        avg   = (sum(rains) / len(rains)) if rains else None
        return avg, humid, total

    f_avg, fhy, fht = _agg(future_ann)
    b_avg, bhy, bht = _agg(baseline_ann)

    out: Dict[str, Any] = {}
    if _is_num(f_avg) and _is_num(b_avg):
        d = f_avg - b_avg
        p = _percent_change(d, b_avg)
        out["annual_rain_mm"] = {
            "future":        round(f_avg, 1),
            "baseline_avg": round(b_avg, 1),
            "diff":         round(d, 1),
            "pct":          round(p, 2) if _is_num(p) else None,
        }
    out["humid_status"] = {
        "future_humid_count":    fhy,
        "future_humid_total":    fht,
        "baseline_humid_count": bhy,
        "baseline_humid_total": bht,
    }
    return out

# The architecture asks for three season-summary comparisons:
#   Baseline LTM vs Future LTM, Focal vs Baseline LTM, Focal vs Future LTM
def _diff_value_2level(a: Dict[str, Dict[str, Any]],
                       b: Dict[str, Dict[str, Any]],
                       a_lbl: str, b_lbl: str,
                       round_n: int = 2) -> Dict[str, Any]:
    """Diff two {outer: {inner: number}} blocks into {outer: {inner: {a_lbl, b_lbl, diff, pct}}}."""
    out: Dict[str, Any] = {}
    for outer, a_inner in (a or {}).items():
        b_inner = (b or {}).get(outer)
        if not (isinstance(a_inner, dict) and isinstance(b_inner, dict)):
            continue
        block: Dict[str, Any] = {}
        for inner, av in a_inner.items():
            bv = b_inner.get(inner)
            if not (_is_num(av) and _is_num(bv)):
                continue
            d = av - bv
            p = _percent_change(d, bv)
            block[inner] = {a_lbl: round(av, round_n), b_lbl: round(bv, round_n),
                            "diff": round(d, round_n),
                            "pct": round(p, 2) if _is_num(p) else None}
        if block:
            out[outer] = block
    return out

def _future_ltm_from_agg(agg: Dict[str, Any],
                         mean_key: str = "future_avg_ensemble_mean") -> Dict[str, Dict[str, float]]:
    """Pull the future-LTM ensemble means out of an aggregated 2-level block."""
    out: Dict[str, Dict[str, float]] = {}
    for outer, inner_dict in (agg or {}).items():
        if not isinstance(inner_dict, dict):
            continue
        block: Dict[str, float] = {}
        for inner, vals in inner_dict.items():
            if isinstance(vals, dict) and _is_num(vals.get(mean_key)):
                block[inner] = float(vals[mean_key])
        if block:
            out[outer] = block
    return out

def _build_focal_summary(location:     Tuple[float, float],
                          focal_year:  int,
                          focal_source: str,
                          fixed_season: Optional[str],
                          precip_source: Optional[str] = None,
                          temp_source: Optional[str] = None,
                          crop_name: Optional[str] = None,
                          calendar_source: Optional[str] = None,
                          calendar_system: str = "rf",
                          diagnostic_verbose: bool = False,
                          spei_scale_months: Optional[int] = None,
                          spei_fit: str = "ub-pwm",
                          spei_ref_start: Optional[str] = None,
                          spei_ref_end: Optional[str] = None,
                          spi_scale_months: Optional[int] = None,
                          spi_fit: str = "ub-pwm",
                          spi_ref_start: Optional[str] = None,
                          spi_ref_end: Optional[str] = None) -> Dict[str, Any]:
    """Fetch one observed year and reduce it to comparable season-summary values."""
    fs_kw = {"fixed_season": fixed_season} if fixed_season else {}
    paired_kw = {}
    if precip_source:
        paired_kw["precip_source"] = precip_source
    if temp_source:
        paired_kw["temp_source"] = temp_source
    calendar_kw = {
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
    }
    stats = _run_stats_call(
        diagnostic_verbose=diagnostic_verbose,
        location_coord=location,
        start_year=focal_year, end_year=focal_year,
        source=focal_source, **fs_kw, **paired_kw, **calendar_kw,
        include_period_raw_summary=False,
        **_COMPACT_COMPARE_STATS_KWARGS,
        spei_scale_months=spei_scale_months,
        spei_fit=spei_fit,
        spei_ref_start=spei_ref_start,
        spei_ref_end=spei_ref_end,
        spi_scale_months=spi_scale_months,
        spi_fit=spi_fit,
        spi_ref_start=spi_ref_start,
        spi_ref_end=spi_ref_end,
        verbose=diagnostic_verbose,
    )

    overall = _filter_overall_statistics_for_period_compare(
        _round(stats.get("overall_statistics", {}), 2)
    )

    seasons = _round(stats.get("season_statistics", []), 2)
    if fixed_season:
        grp: Dict[int, List[Dict]] = {}
        for s in seasons:
            grp.setdefault(s.get("season_number", 1), []).append(s)
        windows = []
        for sn in sorted(grp):
            agg = _agg_seasons(grp[sn])
            block = {c: agg[c] for c in ("precipitation", "temperature", "water_balance")
                     if isinstance(agg.get(c), dict)}
            windows.append({"season_number": sn, "block": block})
        season_summary: Dict[str, Any] = {"windows": windows}
    else:
        agg = _agg_seasons(seasons)
        block = {c: agg[c] for c in ("precipitation", "temperature", "water_balance")
                 if isinstance(agg.get(c), dict)}
        season_summary = {"block": block}
    season_summary = _merge_seasonal_spei_into_summary(
        season_summary,
        _seasonal_spei_period_block(stats.get("spei"), fixed_season),
    )

    ann = (stats.get("annual_summary", {}) or {}).get(str(focal_year), {}) or {}
    return {
        "focal_year":  focal_year,
        "source":       focal_source,
        "precip_source": precip_source,
        "temp_source": temp_source,
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
        "calendar_preset_used": stats.get("calendar_preset_used"),
        "calendar_preset": stats.get("calendar_preset"),
        "overall":      overall,
        "seasons":      season_summary,
        "spei":         stats.get("spei"),
        "spi":          stats.get("spi"),
        "annual_rain":  ann.get("annual_rain_mm"),
        "is_humid":     ann.get("is_humid"),
        "humid_test":   ann.get("humid_test"),
        "season_detection_status": stats.get("season_detection_status"),
        "season_detection_reasons": stats.get("season_detection_reasons"),
        "season_detection_guidance": stats.get("season_detection_guidance"),
        "season_detection": stats.get("season_detection"),
    }

def _season_block(seasons: List[Dict]) -> Dict[str, Any]:
    """Reduce a list of season rows to {cat: {metric: number}} for the comparable cats."""
    agg = _agg_seasons(seasons)
    return {c: agg[c] for c in ("precipitation", "temperature", "water_balance")
            if isinstance(agg.get(c), dict)}

def _mean_2level(maps: List[Dict[str, Dict[str, Any]]], round_n: int = 2) -> Dict[str, Any]:
    """Mean a list of {outer: {inner: number}} maps into {outer: {inner: mean}}."""
    pool: Dict[str, Dict[str, List[float]]] = {}
    for m in maps:
        for outer, inner in (m or {}).items():
            if not isinstance(inner, dict):
                continue
            for k, v in inner.items():
                if _is_num(v):
                    pool.setdefault(outer, {}).setdefault(k, []).append(float(v))
    return {o: {k: round(sum(vs) / len(vs), round_n) for k, vs in inner.items() if vs}
            for o, inner in pool.items()}


def _aggregate_methodology_side(summaries: List[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    clean = [summary for summary in summaries if isinstance(summary, dict)]
    if not clean:
        return None

    requested_modes = sorted({
        mode
        for summary in clean
        for mode in (summary.get("requested_modes") or [])
        if mode
    })
    applied_modes = sorted({
        mode
        for summary in clean
        for mode in (summary.get("applied_modes") or [])
        if mode
    })
    days_means = [
        summary.get("counted_days", {}).get("mean")
        for summary in clean
        if _is_num(summary.get("counted_days", {}).get("mean"))
    ]
    day_mins = [
        summary.get("counted_days", {}).get("min")
        for summary in clean
        if _is_num(summary.get("counted_days", {}).get("min"))
    ]
    day_maxs = [
        summary.get("counted_days", {}).get("max")
        for summary in clean
        if _is_num(summary.get("counted_days", {}).get("max"))
    ]
    warnings = []
    for summary in clean:
        for warning in summary.get("warnings") or []:
            if warning and warning not in warnings:
                warnings.append(warning)

    return {
        "requested_modes": requested_modes,
        "applied_modes": applied_modes,
        "counted_days": {
            "mean": round(sum(days_means) / len(days_means), 1) if days_means else None,
            "min": min(day_mins) if day_mins else None,
            "max": max(day_maxs) if day_maxs else None,
            "n": len(days_means),
        },
        "warnings": warnings,
    }


def _aggregate_period_methodology(
    summaries: List[Optional[Dict[str, Any]]],
    left_label: str,
    right_label: str,
) -> Optional[Dict[str, Any]]:
    clean = [summary for summary in summaries if isinstance(summary, dict)]
    if not clean:
        return None
    left = _aggregate_methodology_side([summary.get(left_label) for summary in clean])
    right = _aggregate_methodology_side([summary.get(right_label) for summary in clean])
    if not left and not right:
        return None
    return {
        left_label: left,
        right_label: right,
    }

def _build_focal_summary_nexgddp(location:     Tuple[float, float],
                                 focal_year:   int,
                                 fixed_season: Optional[str],
                                 scenario:     str,
                                 crop_name: Optional[str] = None,
                                 calendar_source: Optional[str] = None,
                                 calendar_system: str = "rf",
                                 models:         Optional[List[str]] = None,
                                 exclude_models: Optional[List[str]] = None,
                                 policy_profile: Optional[str] = None,
                                 verbose:        bool = True,
                                 diagnostic_verbose: bool = False,
                                 spei_scale_months: Optional[int] = None,
                                 spei_fit: str = "ub-pwm",
                                 spei_ref_start: Optional[str] = None,
                                 spei_ref_end: Optional[str] = None,
                                 spi_scale_months: Optional[int] = None,
                                 spi_fit: str = "ub-pwm",
                                 spi_ref_start: Optional[str] = None,
                                 spi_ref_end: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Build a single-year focal summary from the NEX-GDDP ensemble itself (mean across models), so the focal/baseline/future comparison is entirely NEX-GDDP-sourced.
    Scenario-dependent (the focal year inherits the same scenario as the LTMs).
    """
    canon  = _normalize_scenario(scenario) or scenario
    active, _ = _resolve_models_and_policy(location, models, exclude_models, policy_profile=policy_profile)
    fs_kw  = {"fixed_season": fixed_season} if fixed_season else {}
    calendar_kw = {
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
    }

    overalls:   List[Dict[str, Any]] = []
    win_blocks: Dict[int, List[Dict[str, Any]]] = {}
    lump_blocks: List[Dict[str, Any]] = []
    spei_blocks: List[Dict[str, Any]] = []
    spi_blocks: List[Dict[str, Any]] = []
    rains:      List[float] = []
    humid_count = humid_total = 0
    calendar_presets: List[Dict[str, Any]] = []

    for model in active:
        try:
            stats = _run_stats_call(
                diagnostic_verbose=diagnostic_verbose,
                location_coord=location,
                start_year=focal_year, end_year=focal_year,
                source="nex_gddp", model=model, scenario=canon, **fs_kw, **calendar_kw,
                include_period_raw_summary=False,
                **_COMPACT_COMPARE_STATS_KWARGS,
                spei_scale_months=spei_scale_months,
                spei_fit=spei_fit,
                spei_ref_start=spei_ref_start,
                spei_ref_end=spei_ref_end,
                spi_scale_months=spi_scale_months,
                spi_fit=spi_fit,
                spi_ref_start=spi_ref_start,
                spi_ref_end=spi_ref_end,
                verbose=diagnostic_verbose,
            )
        except Exception as exc:
            if verbose:
                print(f"    x  focal {model}: {exc}")
            continue

        overalls.append(
            _filter_overall_statistics_for_period_compare(
                _round(stats.get("overall_statistics", {}), 2)
            )
        )
        seasons = _round(stats.get("season_statistics", []), 2)
        spei_windows = _seasonal_spei_period_block(stats.get("spei"), fixed_season)
        spei_by_sn = {
            w.get("season_number", 1): w.get("block", {})
            for w in (spei_windows or {}).get("windows", [])
        }
        if fixed_season:
            grp: Dict[int, List[Dict]] = {}
            for s in seasons:
                grp.setdefault(s.get("season_number", 1), []).append(s)
            for sn, rows in grp.items():
                block = _season_block(rows)
                if spei_by_sn.get(sn):
                    block.update(spei_by_sn[sn])
                win_blocks.setdefault(sn, []).append(block)
        else:
            lump_blocks.append(_season_block(seasons))

        ann = (stats.get("annual_summary", {}) or {}).get(str(focal_year), {}) or {}
        if stats.get("spei"):
            spei_blocks.append(stats["spei"])
        if stats.get("spi"):
            spi_blocks.append(stats["spi"])
        if stats.get("calendar_preset"):
            calendar_presets.append(stats["calendar_preset"])
        if _is_num(ann.get("annual_rain_mm")):
            rains.append(float(ann["annual_rain_mm"]))
        if ann.get("is_humid") is not None:
            humid_total += 1
            if ann.get("is_humid"):
                humid_count += 1

    if not overalls:
        return None

    if fixed_season:
        season_summary: Dict[str, Any] = {
            "windows": [{"season_number": sn, "block": _mean_2level(win_blocks[sn])}
                        for sn in sorted(win_blocks)]
        }
    else:
        season_summary = {"block": _mean_2level(lump_blocks)}

    focal_spei = _aggregate_simple_spei_blocks(spei_blocks) if spei_blocks else None
    focal_spi = _aggregate_simple_spi_blocks(spi_blocks) if spi_blocks else None

    return {
        "focal_year":  focal_year,
        "source":      f"nex_gddp ensemble ({len(overalls)} models, {canon})",
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
        "calendar_preset_used": bool(calendar_presets),
        "calendar_preset": calendar_presets[0] if calendar_presets else None,
        "overall":     _mean_2level(overalls),
        "seasons":     season_summary,
        "spei":        focal_spei,
        "spi":         focal_spi,
        "annual_rain": round(sum(rains) / len(rains), 1) if rains else None,
        "is_humid":    (humid_count > humid_total / 2) if humid_total else None,
        "humid_test":  f"{humid_count}/{humid_total} models humid" if humid_total else None,
    }


def _aggregate_simple_spei_blocks(blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not blocks:
        return None
    monthly_pool: Dict[str, Dict[str, List[float]]] = {}
    for block in blocks:
        for row in block.get("monthly_series") or []:
            date_key = row.get("date")
            month = row.get("month")
            if not date_key:
                continue
            slot = monthly_pool.setdefault(date_key, {"month": [month], "spei": []})
            if _is_num(row.get("spei")):
                slot["spei"].append(float(row["spei"]))
    monthly_rows = []
    for date_key in sorted(monthly_pool):
        slot = monthly_pool[date_key]
        if not slot["spei"]:
            continue
        monthly_rows.append({
            "date": date_key,
            "month": int(slot["month"][0]) if slot["month"] and slot["month"][0] is not None else None,
            "spei": round(sum(slot["spei"]) / len(slot["spei"]), 3),
        })
    if not monthly_rows:
        return None
    valid = [row["spei"] for row in monthly_rows if _is_num(row.get("spei"))]
    return {
        "config": blocks[0].get("config", {}),
        "summary": {
            "n_months": len(monthly_rows),
            "n_valid_spei": len(valid),
        },
        "metadata": blocks[0].get("metadata", {}),
        "monthly_series": monthly_rows,
    }


def _aggregate_simple_spi_blocks(blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not blocks:
        return None
    monthly_pool: Dict[str, Dict[str, List[float]]] = {}
    for block in blocks:
        for row in block.get("monthly_series") or []:
            date_key = row.get("date")
            month = row.get("month")
            if not date_key:
                continue
            slot = monthly_pool.setdefault(date_key, {"month": [month], "spi": []})
            if _is_num(row.get("spi")):
                slot["spi"].append(float(row["spi"]))
    monthly_rows = []
    for date_key in sorted(monthly_pool):
        slot = monthly_pool[date_key]
        if not slot["spi"]:
            continue
        monthly_rows.append({
            "date": date_key,
            "month": int(slot["month"][0]) if slot["month"] and slot["month"][0] is not None else None,
            "spi": round(sum(slot["spi"]) / len(slot["spi"]), 3),
        })
    if not monthly_rows:
        return None
    valid = [row["spi"] for row in monthly_rows if _is_num(row.get("spi"))]
    return {
        "config": blocks[0].get("config", {}),
        "summary": {
            "n_months": len(monthly_rows),
            "n_valid_spi": len(valid),
        },
        "metadata": blocks[0].get("metadata", {}),
        "monthly_series": monthly_rows,
    }


def _aggregate_compare_season_detection(per_model: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    summaries = [
        r.get("season_detection")
        for r in per_model
        if isinstance(r, dict) and isinstance(r.get("season_detection"), dict)
    ]
    if not summaries:
        return None
    statuses = [summary.get("compare_status") for summary in summaries if summary.get("compare_status")]
    counts: Dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    guidance = list(dict.fromkeys([
        item
        for summary in summaries
        for item in (summary.get("guidance") or [])
    ]))
    if counts.get("prompt_required"):
        compare_status = "prompt_required"
    elif counts.get("warn"):
        compare_status = "warn"
    else:
        compare_status = "ok"
    return {
        "compare_status": compare_status,
        "counts_by_status": counts,
        "n_models": len(summaries),
        "human_review_recommended": compare_status in {"warn", "prompt_required"},
        "fixed_season_recommended": compare_status == "prompt_required",
        "guidance": guidance,
    }

def _diff_focal_vs_ltm(focal:   Dict[str, Any],
                        ensemble: Dict[str, Any],
                        mean_key: str,
                        ltm_label: str,
                        annual_rain_key: str,
                        humid_key: str) -> Dict[str, Any]:
    """
    Diff the observed focal year against one set of ensemble LTM means (focal - ltm). mean_key selects which LTM is pulled from the aggregated blocks:
        'future_avg_ensemble_mean'   -> Future LTM   (focal vs future)
        'baseline_avg_ensemble_mean' -> Baseline LTM (focal vs historical)
    """
    a_lbl, b_lbl = "focal", ltm_label

    ltm_overall = _filter_overall_statistics_for_period_compare(
        _future_ltm_from_agg(ensemble.get("overall_statistics", {}), mean_key)
    )
    overall_diff = _diff_value_2level(focal.get("overall", {}), ltm_overall, a_lbl, b_lbl)

    ens_season = ensemble.get("season_statistics") or {}
    act_season = focal.get("seasons") or {}
    season_diff: Optional[Dict[str, Any]] = None
    if "windows" in ens_season:
        act_by_sn = {w["season_number"]: w["block"]
                     for w in act_season.get("windows", [])}
        windows = []
        for w in ens_season.get("windows", []):
            sn         = w.get("season_number", 1)
            ltm_blk    = _future_ltm_from_agg(w.get("diff", {}), mean_key)
            focal_blk = act_by_sn.get(sn, {})
            windows.append({
                "window":        w.get("window"),
                "season_number": sn,
                "diff":          _diff_value_2level(focal_blk, ltm_blk, a_lbl, b_lbl),
            })
        season_diff = {"windows": windows}
    elif ens_season.get("diff"):
        ltm_blk = _future_ltm_from_agg(ens_season["diff"], mean_key)
        season_diff = {"diff": _diff_value_2level(act_season.get("block", {}),
                                                  ltm_blk, a_lbl, b_lbl)}

    annual: Dict[str, Any] = {}
    ra = (ensemble.get("annual_summary", {}) or {}).get(annual_rain_key, {}) or {}
    ltm_rain    = ra.get("mean")
    focal_rain = focal.get("annual_rain")
    if _is_num(focal_rain) and _is_num(ltm_rain):
        d = focal_rain - ltm_rain
        p = _percent_change(d, ltm_rain)
        annual["annual_rain_mm"] = {
            a_lbl: round(float(focal_rain), 1), b_lbl: round(float(ltm_rain), 1),
            "diff": round(d, 1), "pct": round(p, 2) if _is_num(p) else None,
        }
    annual["humid_status"] = {
        "focal_is_humid":   focal.get("is_humid"),
        "focal_humid_test": focal.get("humid_test"),
        "ltm_humid":         ensemble.get("annual_summary", {}).get(humid_key, "n/a"),
    }

    spei = _diff_spei(focal.get("spei"), ensemble.get("spei"))
    spi = _diff_spi(focal.get("spi"), ensemble.get("spi"))

    return {
        "focal_year":        focal["focal_year"],
        "focal_source":      focal["source"],
        "ltm_label":          ltm_label,
        "overall_statistics": overall_diff,
        "season_statistics":  season_diff,
        "annual_summary":     annual,
        "spei":               spei,
        "spi":                spi,
    }

def _diff_focal_vs_future(focal: Dict[str, Any],
                           ensemble: Dict[str, Any]) -> Dict[str, Any]:
    """Focal observed year vs Future LTM (Δ = focal - future_ltm)."""
    return _diff_focal_vs_ltm(focal, ensemble,
                               mean_key="future_avg_ensemble_mean",
                               ltm_label="future_ltm",
                               annual_rain_key="annual_rain_mm_future",
                               humid_key="humid_future")

def _diff_focal_vs_baseline(focal: Dict[str, Any],
                             ensemble: Dict[str, Any]) -> Dict[str, Any]:
    """Focal observed year vs Baseline (historical) LTM (Δ = focal - baseline_ltm)."""
    return _diff_focal_vs_ltm(focal, ensemble,
                               mean_key="baseline_avg_ensemble_mean",
                               ltm_label="baseline_ltm",
                               annual_rain_key="annual_rain_mm_baseline",
                               humid_key="humid_baseline")

# per-model comparison (replicates periods.compare with future as a period)
def _compare_one_model(
    location:       Tuple[float, float],
    baseline_start: int,
    baseline_end:   int,
    future_start:    int,
    future_end:      int,
    fixed_season:   Optional[str],
    model:          str,
    scenario:       str,
    crop_name: Optional[str] = None,
    calendar_source: Optional[str] = None,
    calendar_system: str = "rf",
    diagnostic_verbose: bool = False,
    spei_scale_months: Optional[int] = None,
    spei_fit: str = "ub-pwm",
    spei_ref_start: Optional[str] = None,
    spei_ref_end: Optional[str] = None,
    spi_scale_months: Optional[int] = None,
    spi_fit: str = "ub-pwm",
    spi_ref_start: Optional[str] = None,
    spi_ref_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Same logic as periods.compare(), but pinned to source='nex_gddp'. Baseline
    period always uses that model's historical run, while future period uses
    requested SSP scenario. Both sides are annualised so overall totals are
    comparable on a per-year basis.
    """
    period_error = _validate_nex_periods(
        baseline_start, baseline_end, future_start, future_end, scenario
    )
    if period_error:
        return {"error": period_error}

    n_base    = baseline_end - baseline_start + 1
    n_future   = future_end    - future_start    + 1
    drop_temp = "nex_gddp" in PRECIP_ONLY  # NEX-GDDP carries tas, so False
    fs_kw     = {"fixed_season": fixed_season} if fixed_season else {}
    calendar_kw = {
        "crop_name": crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
    }
    spei_kw = (
        {
            "spei_scale_months": spei_scale_months,
            "spei_fit": spei_fit,
            "spei_ref_start": spei_ref_start,
            "spei_ref_end": spei_ref_end,
        }
        if spei_scale_months is not None else {}
    )
    spi_kw = (
        {
            "spi_scale_months": spi_scale_months,
            "spi_fit": spi_fit,
            "spi_ref_start": spi_ref_start,
            "spi_ref_end": spi_ref_end,
        }
        if spi_scale_months is not None else {}
    )

    baseline_started = perf_counter()
    base = _run_stats_call(
        diagnostic_verbose=diagnostic_verbose,
        location_coord=location,
        start_year=baseline_start, end_year=baseline_end,
        source="nex_gddp",
        model=model, scenario="historical",
        **_COMPACT_COMPARE_STATS_KWARGS,
        **fs_kw, **calendar_kw, **spei_kw, **spi_kw,
    )
    baseline_elapsed = perf_counter() - baseline_started
    baseline_timing = _extract_stats_timing(base)
    if isinstance(base, dict) and base.get("error"):
        return {
            "error": (
                f"Baseline fetch/analysis failed for model={model} scenario=historical "
                f"({baseline_start}-{baseline_end}): {base['error']}"
            ),
            "timing_breakdown": {
                "baseline": baseline_timing,
                "future": {},
                "baseline_total_seconds": round(baseline_elapsed, 3),
                "future_total_seconds": None,
                "compare_seconds": None,
            },
        }
    future_started = perf_counter()
    future = _run_stats_call(
        diagnostic_verbose=diagnostic_verbose,
        location_coord=location,
        start_year=future_start, end_year=future_end,
        source="nex_gddp",
        model=model, scenario=scenario,
        **_COMPACT_COMPARE_STATS_KWARGS,
        **fs_kw, **calendar_kw, **spei_kw, **spi_kw,
    )
    future_elapsed = perf_counter() - future_started
    future_timing = _extract_stats_timing(future)
    if isinstance(future, dict) and future.get("error"):
        return {
            "error": (
                f"Future fetch/analysis failed for model={model} scenario={scenario} "
                f"({future_start}-{future_end}): {future['error']}"
            ),
            "timing_breakdown": {
                "baseline": baseline_timing,
                "future": future_timing,
                "baseline_total_seconds": round(baseline_elapsed, 3),
                "future_total_seconds": round(future_elapsed, 3),
                "compare_seconds": None,
            },
        }
    season_detection = _compare_season_detection_summary(
        base,
        future,
        fixed_season,
    )
    season_detection_error = _compare_season_detection_guard(season_detection)
    if season_detection_error:
        return {
            "error": season_detection_error,
            "season_detection": season_detection,
            "timing_breakdown": {
                "baseline": baseline_timing,
                "future": future_timing,
                "baseline_total_seconds": round(baseline_elapsed, 3),
                "future_total_seconds": round(future_elapsed, 3),
                "compare_seconds": None,
            },
        }
    compare_started = perf_counter()
    # 1. raw_climate_summary -- already period-wide means/min/max/std
    raw_diff = _diff_raw(future.get("raw_climate_summary", []),
                         base.get("raw_climate_summary",  []),
                         drop_temp)
    # 2. overall_statistics -- annualise BOTH sides
    base_overall = _filter_overall_statistics_for_period_compare(
        _annualize(_round(base.get("overall_statistics", {}), 2), n_base)
    )
    future_overall = _filter_overall_statistics_for_period_compare(
        _annualize(_round(future.get("overall_statistics", {}), 2), n_future)
    )
    overall_diff  = _diff_block(future_overall, base_overall,
                                "future_avg", "baseline_avg", drop_temp)
    # 3. season_statistics
    base_seasons  = _round(base.get("season_statistics",  []), 2)
    future_seasons = _round(future.get("season_statistics", []), 2)
    season_diff: Optional[Dict[str, Any]] = None
    if base_seasons or future_seasons:
        if not fixed_season:
            auto_guard_error = _auto_season_count_guard(base_seasons, future_seasons)
            if auto_guard_error:
                return {
                    "error": auto_guard_error,
                    "season_detection": season_detection,
                    "timing_breakdown": {
                        "baseline": baseline_timing,
                        "future": future_timing,
                        "baseline_total_seconds": round(baseline_elapsed, 3),
                        "future_total_seconds": round(future_elapsed, 3),
                        "compare_seconds": None,
                    },
                }
        if fixed_season:
            labels = [w.strip() for w in fixed_season.split(",")]
            base_grp:  Dict[int, List[Dict]] = {}
            future_grp: Dict[int, List[Dict]] = {}
            for s in base_seasons:
                base_grp.setdefault(s.get("season_number", 1), []).append(s)
            for s in future_seasons:
                future_grp.setdefault(s.get("season_number", 1), []).append(s)
            windows = []
            for sn in sorted(set(base_grp) | set(future_grp)):
                label = labels[sn - 1] if 0 < sn <= len(labels) else f"window_{sn}"
                fb = _agg_seasons(future_grp.get(sn, []))
                bb = _agg_seasons(base_grp.get(sn, []))
                windows.append({
                    "window":        label,
                    "season_number": sn,
                    "n_baseline":    bb["_n"],
                    "n_future":       fb["_n"],
                    "water_balance_methodology": _merge_period_methodology(
                        future_grp.get(sn, []),
                        base_grp.get(sn, []),
                        "future_avg",
                        "baseline_avg",
                    ),
                    "diff":          _diff_block(fb, bb, "future_avg", "baseline_avg",
                                                 drop_temp),
                })
            season_diff = {"windows": windows}
        else:
            fb = _agg_seasons(future_seasons)
            bb = _agg_seasons(base_seasons)
            season_diff = {
                "n_baseline": bb["_n"],
                "n_future":    fb["_n"],
                "water_balance_methodology": _merge_period_methodology(
                    future_seasons,
                    base_seasons,
                    "future_avg",
                    "baseline_avg",
                ),
                "diff":       _diff_block(fb, bb, "future_avg", "baseline_avg",
                                          drop_temp),
            }
    season_diff = _merge_seasonal_spei_into_diff(
        season_diff,
        _seasonal_spei_period_block(future.get("spei"), fixed_season),
        _seasonal_spei_period_block(base.get("spei"), fixed_season),
        "future_avg",
        "baseline_avg",
    )
    # 4. annual_summary -- future is now a period
    annual_diff = _diff_annual_period(future.get("annual_summary", {}),
                                      base.get("annual_summary",  {}))
    spei_diff = _diff_spei(
        future.get("spei"),
        base.get("spei"),
    )
    spi_diff = _diff_spi(
        future.get("spi"),
        base.get("spi"),
    )
    compare_elapsed = perf_counter() - compare_started
    return {
        "future_period":         f"{future_start}-{future_end}",
        "future_years":          n_future,
        "baseline_period":      f"{baseline_start}-{baseline_end}",
        "baseline_years":       n_base,
        "source":               "nex_gddp",
        "model":                model,
        "scenario":             scenario,
        "fixed_season":         fixed_season,
        "crop_name":            crop_name,
        "calendar_source":      calendar_source,
        "calendar_system":      calendar_system,
        "baseline_calendar_preset_used": bool(base.get("calendar_preset_used")),
        "baseline_calendar_preset": base.get("calendar_preset"),
        "future_calendar_preset_used": bool(future.get("calendar_preset_used")),
        "future_calendar_preset": future.get("calendar_preset"),
        "spei_scale_months":    spei_scale_months,
        "spi_scale_months":     spi_scale_months,
        "temperature_excluded": drop_temp,
        "season_detection":     season_detection,
        "raw_climate_summary":  raw_diff,
        "overall_statistics":   overall_diff,
        "season_statistics":    season_diff,
        "annual_summary":       annual_diff,
        "spei":                 spei_diff,
        "spi":                  spi_diff,
        "timing_breakdown": {
            "baseline": baseline_timing,
            "future": future_timing,
            "baseline_total_seconds": round(baseline_elapsed, 3),
            "future_total_seconds": round(future_elapsed, 3),
            "compare_seconds": round(compare_elapsed, 3),
        },
    }

# cross-model aggregation
def _aggregate_2level(per_model: List[Dict[str, Dict[str, Dict[str, Any]]]],
                      round_n: int = 2) -> Dict[str, Any]:
    """
    Pool {outer: {inner: {metric_name: number, ...}}} across models.

    Returns: {outer: {inner: {<metric>_ensemble_mean, model_spread}}}.
    Used for raw_climate_summary, overall_statistics, and each season window.
    """
    pool: Dict[str, Dict[str, Dict[str, List[float]]]] = {}
    for d in per_model:
        for outer, inner_dict in (d or {}).items():
            if not isinstance(inner_dict, dict):
                continue
            for inner, vals in inner_dict.items():
                if not isinstance(vals, dict):
                    continue
                slot = pool.setdefault(outer, {}).setdefault(inner, {})
                for k, v in vals.items():
                    if _is_num(v):
                        slot.setdefault(k, []).append(float(v))
    out: Dict[str, Any] = {}
    for outer, inner_dict in pool.items():
        out[outer] = {}
        for inner, vecs in inner_dict.items():
            entry: Dict[str, Any] = {
                f"{k}_ensemble_mean": round(pystat.mean(vs), round_n)
                for k, vs in vecs.items() if vs
            }
            entry["model_spread"] = {
                k: _spread(vs)
                for k, vs in vecs.items() if vs
            }
            out[outer][inner] = entry
    return out


def _fmt_likely_range(spread: Optional[Dict[str, Any]], precision: int = 2) -> str:
    if not isinstance(spread, dict):
        return "n/a"
    low = spread.get("p17")
    high = spread.get("p83")
    if not (_is_num(low) and _is_num(high)):
        return "n/a"
    return f"[{low:.{precision}f}, {high:.{precision}f}]"

def _aggregate_seasons(per_model: List[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Aggregate season_statistics across models (handles both lumped and windowed)."""
    samples = [s for s in per_model if isinstance(s, dict) and s]
    if not samples:
        return None

    if "windows" in samples[0]:
        win_pool: Dict[int, Dict[str, Any]] = {}
        for s in per_model:
            for w in (s or {}).get("windows", []) or []:
                sn = w.get("season_number", 1)
                bucket = win_pool.setdefault(
                    sn,
                    {"label": w.get("window"), "diffs": [], "methodologies": []},
                )
                bucket["diffs"].append(w.get("diff", {}))
                if w.get("water_balance_methodology"):
                    bucket["methodologies"].append(w.get("water_balance_methodology"))
        windows = []
        for sn in sorted(win_pool):
            windows.append({
                "window":        win_pool[sn]["label"],
                "season_number": sn,
                "n_models":      len(win_pool[sn]["diffs"]),
                "water_balance_methodology": _aggregate_period_methodology(
                    win_pool[sn]["methodologies"],
                    "future_avg",
                    "baseline_avg",
                ),
                "diff":          _aggregate_2level(win_pool[sn]["diffs"]),
            })
        return {"windows": windows}

    diffs = [(s or {}).get("diff", {}) for s in per_model if s]
    methodologies = [
        (s or {}).get("water_balance_methodology")
        for s in per_model if s
    ]
    return {
        "n_models": len(diffs),
        "water_balance_methodology": _aggregate_period_methodology(
            methodologies,
            "future_avg",
            "baseline_avg",
        ),
        "diff": _aggregate_2level(diffs),
    }

def _aggregate_annual(per_model: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Aggregate annual_summary across models (period future version)."""
    rains_future:    List[float] = []
    rains_baseline: List[float] = []
    rains_diff:     List[float] = []
    rains_pct:      List[float] = []
    fhy = fht = bhy = bht = 0  
    for ann in per_model:
        ann = ann or {}
        arm = ann.get("annual_rain_mm") or {}
        for vec, key in [(rains_future,    "future"),
                         (rains_baseline, "baseline_avg"),
                         (rains_diff,     "diff"),
                         (rains_pct,      "pct")]:
            v = arm.get(key)
            if _is_num(v):
                vec.append(float(v))
        hs = ann.get("humid_status") or {}
        if _is_num(hs.get("future_humid_count")):    fhy += int(hs["future_humid_count"])
        if _is_num(hs.get("future_humid_total")):    fht += int(hs["future_humid_total"])
        if _is_num(hs.get("baseline_humid_count")): bhy += int(hs["baseline_humid_count"])
        if _is_num(hs.get("baseline_humid_total")): bht += int(hs["baseline_humid_total"])

    out: Dict[str, Any] = {}
    if rains_future:    out["annual_rain_mm_future"]    = _spread(rains_future)
    if rains_baseline: out["annual_rain_mm_baseline"] = _spread(rains_baseline)
    if rains_diff:     out["annual_rain_mm_diff"]     = _spread(rains_diff)
    if rains_pct:      out["annual_rain_mm_pct"]      = _spread(rains_pct)
    out["humid_future"]    = (f"{fhy}/{fht} ({fhy / fht * 100:.1f}%)"
                             if fht else "n/a")
    out["humid_baseline"] = (f"{bhy}/{bht} ({bhy / bht * 100:.1f}%)"
                             if bht else "n/a")
    return out


def _aggregate_spei_diff(per_model: List[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    samples = [r.get("spei") for r in per_model if isinstance(r, dict) and r.get("spei")]
    if not samples:
        return None
    monthly_pool: Dict[str, Dict[str, List[float]]] = {}
    summary_pool: Dict[str, List[float]] = {}
    for sample in samples:
        for row in sample.get("monthly") or []:
            date_key = row.get("date")
            month = row.get("month")
            if not date_key:
                continue
            slot = monthly_pool.setdefault(date_key, {"month": [month]})
            for key in ("focal_spei", "baseline_avg_spei", "diff"):
                if _is_num(row.get(key)):
                    slot.setdefault(key, []).append(float(row[key]))
        summary = sample.get("summary") or {}
        for key in ("focal_avg_spei", "baseline_avg_spei", "diff"):
            if _is_num(summary.get(key)):
                summary_pool.setdefault(key, []).append(float(summary[key]))
    monthly_rows = []
    for date_key in sorted(monthly_pool):
        slot = monthly_pool[date_key]
        row = {
            "date": date_key,
            "month": int(slot["month"][0]) if slot["month"] and slot["month"][0] is not None else None,
        }
        for key in ("focal_spei", "baseline_avg_spei", "diff"):
            vals = slot.get(key) or []
            row[key] = round(sum(vals) / len(vals), 3) if vals else None
        row["pct"] = None
        monthly_rows.append(row)
    summary_out = None
    if summary_pool:
        summary_out = {
            key: round(sum(vals) / len(vals), 3)
            for key, vals in summary_pool.items() if vals
        }
    elif monthly_rows:
        focal_vals = [row["focal_spei"] for row in monthly_rows if _is_num(row.get("focal_spei"))]
        base_vals = [row["baseline_avg_spei"] for row in monthly_rows if _is_num(row.get("baseline_avg_spei"))]
        diff_vals = [row["diff"] for row in monthly_rows if _is_num(row.get("diff"))]
        if focal_vals and base_vals and diff_vals:
            summary_out = {
                "focal_avg_spei": round(sum(focal_vals) / len(focal_vals), 3),
                "baseline_avg_spei": round(sum(base_vals) / len(base_vals), 3),
                "diff": round(sum(diff_vals) / len(diff_vals), 3),
                "pct": None,
            }
    return {
        "summary": summary_out,
        "monthly": monthly_rows,
        "n_models": len(samples),
        "config": {"derived_from": "ensemble mean of per-model SPEI diffs"},
    }


def _aggregate_spi_diff(per_model: List[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    samples = [r.get("spi") for r in per_model if isinstance(r, dict) and r.get("spi")]
    if not samples:
        return None
    monthly_pool: Dict[str, Dict[str, List[float]]] = {}
    summary_pool: Dict[str, List[float]] = {}
    for sample in samples:
        for row in sample.get("monthly") or []:
            date_key = row.get("date")
            month = row.get("month")
            if not date_key:
                continue
            slot = monthly_pool.setdefault(date_key, {"month": [month]})
            for key in ("focal_spi", "baseline_avg_spi", "diff"):
                if _is_num(row.get(key)):
                    slot.setdefault(key, []).append(float(row[key]))
        summary = sample.get("summary") or {}
        for key in ("focal_avg_spi", "baseline_avg_spi", "diff"):
            if _is_num(summary.get(key)):
                summary_pool.setdefault(key, []).append(float(summary[key]))
    monthly_rows = []
    for date_key in sorted(monthly_pool):
        slot = monthly_pool[date_key]
        row = {
            "date": date_key,
            "month": int(slot["month"][0]) if slot["month"] and slot["month"][0] is not None else None,
        }
        for key in ("focal_spi", "baseline_avg_spi", "diff"):
            vals = slot.get(key) or []
            row[key] = round(sum(vals) / len(vals), 3) if vals else None
        row["pct"] = None
        monthly_rows.append(row)
    summary_out = None
    if summary_pool:
        summary_out = {
            key: round(sum(vals) / len(vals), 3)
            for key, vals in summary_pool.items() if vals
        }
    elif monthly_rows:
        focal_vals = [row["focal_spi"] for row in monthly_rows if _is_num(row.get("focal_spi"))]
        base_vals = [row["baseline_avg_spi"] for row in monthly_rows if _is_num(row.get("baseline_avg_spi"))]
        diff_vals = [row["diff"] for row in monthly_rows if _is_num(row.get("diff"))]
        if focal_vals and base_vals and diff_vals:
            summary_out = {
                "focal_avg_spi": round(sum(focal_vals) / len(focal_vals), 3),
                "baseline_avg_spi": round(sum(base_vals) / len(base_vals), 3),
                "diff": round(sum(diff_vals) / len(diff_vals), 3),
                "pct": None,
            }
    return {
        "summary": summary_out,
        "monthly": monthly_rows,
        "n_models": len(samples),
        "config": {"derived_from": "ensemble mean of per-model SPI diffs"},
    }

# main API
def ensemble_compare(
    location:       Tuple[float, float],
    baseline_start: int,
    baseline_end:   int,
    future_start:    int,
    future_end:      int,
    scenario:       str = "ssp245",
    fixed_season:   Optional[str] = None,
    crop_name: Optional[str] = None,
    calendar_source: Optional[str] = None,
    calendar_system: str = "rf",
    models:         Optional[List[str]] = None,
    exclude_models: Optional[List[str]] = None,
    policy_profile: Optional[str] = None,
    focal_summary: Optional[Dict[str, Any]] = None,
    verbose:        bool = True,
    diagnostic_verbose: bool = False,
    model_workers: int = 1,
    spei_scale_months: Optional[int] = None,
    spei_fit: str = "ub-pwm",
    spei_ref_start: Optional[str] = None,
    spei_ref_end: Optional[str] = None,
    spi_scale_months: Optional[int] = None,
    spi_fit: str = "ub-pwm",
    spi_ref_start: Optional[str] = None,
    spi_ref_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the future-period-vs-baseline-period comparison once per NEX-GDDP model, then average across models.
    All data (baseline + future) comes from NEX-GDDP, so each model is compared against its own historical run. Returns one ensemble-shaped result.
    """
    period_error = _validate_nex_periods(
        baseline_start, baseline_end, future_start, future_end, scenario
    )
    if period_error:
        return {"error": period_error}

    canon = _normalize_scenario(scenario)
    if not canon:
        return {"error": (f"scenario '{scenario}' not recognised. "
                          f"Accepted: {sorted(SCENARIO_ALIASES)}")}
    scenario = canon
    calendar_system = str(calendar_system).lower()
    if calendar_system not in CALENDAR_SYSTEM_CHOICES:
        return {
            "error": (
                f"Invalid calendar_system '{calendar_system}'. "
                f"Choose from {', '.join(CALENDAR_SYSTEM_CHOICES)}."
            )
        }
    if (
        not fixed_season
        and crop_name
        and calendar_source == "ggcmi"
        and baseline_end >= 2014
    ):
        try:
            preset = resolve_calendar_preset(
                location[0],
                location[1],
                crop_name,
                system=calendar_system,
            )
        except Exception as exc:
            return {"error": f"Calendar preset lookup failed: {exc}"}
        if _has_year_crossing_window(preset.get("fixed_season")):
            return {
                "error": (
                    "GGCMI preset for this crop/location is year-crossing "
                    f"({preset.get('fixed_season')}), so NEX-GDDP historical baseline "
                    f"{baseline_start}-{baseline_end} would need post-2014 tail data that "
                    "does not exist. Re-run with --baseline-end=2013, or provide a "
                    "non-year-crossing --fixed-season."
                ),
                "calendar_preset": preset,
            }

    active, ensemble_policy = _resolve_models_and_policy(location, models, exclude_models, policy_profile=policy_profile)
    if not active:
        return {"error": "No models selected after filtering."}

    if verbose:
        print(f"\n{'=' * 60}")
        print("NEX-GDDP Ensemble Comparison")
        print(f"  Location  : {location[0]}, {location[1]}")
        print(f"  Baseline  : {baseline_start}-{baseline_end}")
        print(f"  Future     : {future_start}-{future_end}")
        print(f"  Scenario  : {scenario}")
        print(f"  Policy    : {ensemble_policy.get('policy_id')}")
        if ensemble_policy.get("regional_context"):
            print(f"  Context   : {ensemble_policy.get('regional_context')}")
        for line in policy_runtime_messages(ensemble_policy):
            print(f"  Warning   : {line}")
        if fixed_season:
            print(f"  Seasons   : {fixed_season}")
        print(f"  Models    : {len(active)}")
        print(f"  Workload  : {len(active)} model(s) x 2 period(s)")
        print(f"{'=' * 60}")

    requested_model_workers = max(1, int(model_workers))
    tasks = [
        _build_compare_one_model_task(
            location=location,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            future_start=future_start,
            future_end=future_end,
            fixed_season=fixed_season,
            model=model,
            scenario=scenario,
            crop_name=crop_name,
            calendar_source=calendar_source,
            calendar_system=calendar_system,
            diagnostic_verbose=diagnostic_verbose,
            spei_scale_months=spei_scale_months,
            spei_fit=spei_fit,
            spei_ref_start=spei_ref_start,
            spei_ref_end=spei_ref_end,
            spi_scale_months=spi_scale_months,
            spi_fit=spi_fit,
            spi_ref_start=spi_ref_start,
            spi_ref_end=spi_ref_end,
            suppress_child_stdout=requested_model_workers > 1,
        )
        for model in active
    ]
    per_model, failed, effective_model_workers, total_elapsed = _execute_model_tasks(
        tasks=tasks,
        model_workers=requested_model_workers,
        verbose=verbose,
        diagnostic_verbose=diagnostic_verbose,
    )

    if not per_model:
        return {"error": "All models failed.", "failed_models": failed}

    runtime_summary = _build_runtime_summary(per_model, failed, total_elapsed)
    result = {
        "future_period":    f"{future_start}-{future_end}",
        "future_years":     future_end - future_start + 1,
        "baseline_period": f"{baseline_start}-{baseline_end}",
        "baseline_years":  baseline_end - baseline_start + 1,
        "scenario":        scenario,
        "fixed_season":    fixed_season,
        "crop_name":       crop_name,
        "calendar_source": calendar_source,
        "calendar_system": calendar_system,
        "models_used":     [r["_model"] for r in per_model],
        "models_failed":   failed,
        "n_models_ok":     len(per_model),
        "per_model_results": per_model,
        "raw_climate_summary": _aggregate_2level(
            [r.get("raw_climate_summary", {}) for r in per_model], round_n=3),
        "overall_statistics": _aggregate_2level(
            [
                _filter_overall_statistics_for_period_compare(
                    r.get("overall_statistics", {})
                )
                for r in per_model
            ]
        ),
        "season_statistics":   _aggregate_seasons(
            [r.get("season_statistics") for r in per_model]),
        "season_detection":    _aggregate_compare_season_detection(per_model),
        "annual_summary":      _aggregate_annual(
            [r.get("annual_summary") for r in per_model]),
        "spei":               _aggregate_spei_diff(per_model),
        "spi":                _aggregate_spi_diff(per_model),
        "metadata": {
            "location":      {"lat": location[0], "lon": location[1]},
            "source":        "NEX-GDDP-CMIP6",
            "ensemble_policy": ensemble_policy,
            "timing":        {
                "total_seconds": runtime_summary["total_elapsed_seconds"],
                "mean_model_seconds": runtime_summary["mean_model_seconds"],
                "median_model_seconds": runtime_summary["median_model_seconds"],
                "model_workers_requested": requested_model_workers,
                "model_workers_used": effective_model_workers,
                "runtime_summary": runtime_summary,
            },
            "analysis_date": datetime.now().isoformat(),
        },
    }

    if focal_summary:
        # Completes the architecture's three season-summary comparisons:
        result["focal_vs_baseline"] = _diff_focal_vs_baseline(focal_summary, result)
        result["focal_vs_future"]   = _diff_focal_vs_future(focal_summary, result)

    if verbose:
        print(
            f"\nCompleted ensemble comparison in {_format_elapsed(total_elapsed)} "
            f"(models_ok={len(per_model)}, models_failed={len(failed)})"
        )

    return result

# printing
def _print_2level(agg: Dict[str, Any],
                  outer_label: str = "Category",
                  inner_label: str = "Metric",
                  precision:   int = 2) -> None:
    """
    Print ensemble means in the same table shape periods.py prints, with columns matching the underlying diff keys (future_avg/baseline_avg/diff/pct
    -> future_avg/baseline_avg/Δ/Δ%). Model spread is kept in the JSON but suppressed here so the table mirrors periods.py.
    """
    if not agg:
        print("  (no comparable metrics)")
        return
    
    relabel = {"future_avg": "future_ltm", "baseline_avg": "baseline_ltm",
               "focal": "future_ltm", "baseline": "baseline_ltm"}
    rows = []
    for outer, inner_dict in agg.items():
        for inner, vals in inner_dict.items():
            row = {outer_label: outer, inner_label: inner}
            spread = vals.get("model_spread") or {}
            for k, v in vals.items():
                if k == "model_spread" or not _is_num(v):
                    continue
                short = k.replace("_ensemble_mean", "")
                if short == "diff":
                    row["Δ"]  = f"{v:+.{precision}f}"
                elif short == "pct":
                    row["Δ%"] = _fmt_pct(v)
                else:
                    row[relabel.get(short, short)] = f"{v:.{precision}f}"
            diff_spread = spread.get("diff")
            if isinstance(diff_spread, dict):
                if _is_num(diff_spread.get("std")):
                    row["σΔ"] = f"{diff_spread['std']:.{precision}f}"
                likely = _fmt_likely_range(diff_spread, precision=precision)
                if likely != "n/a":
                    row["Likely Δ"] = likely
            rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

def _print_diff_block(diff: Dict[str, Any],
                      outer_label: str = "Category",
                      inner_label: str = "Metric",
                      precision:   int = 2) -> None:
    """Print a plain {outer: {inner: {a_lbl, b_lbl, diff, pct}}} diff (Focal vs Future LTM)."""
    if not diff:
        print("  (no comparable metrics)")
        return
    rows = []
    for outer, inner_dict in diff.items():
        for inner, vals in inner_dict.items():
            row = {outer_label: outer, inner_label: inner}
            for k, v in vals.items():
                if not _is_num(v):
                    continue
                if k == "diff":
                    row["Δ"]  = f"{v:+.{precision}f}"
                elif k == "pct":
                    row["Δ%"] = _fmt_pct(v)
                else:
                    row[k] = f"{v:.{precision}f}"
            rows.append(row)
    print(pd.DataFrame(rows).to_string(index=False))

def _print_focal_vs_ltm(avl: Dict[str, Any]) -> None:
    yr       = avl.get("focal_year")
    src      = avl.get("focal_source")
    ltm_lbl  = avl.get("ltm_label", "ltm")
    title    = "FUTURE LTM" if ltm_lbl == "future_ltm" else "BASELINE LTM"
    print(f"\n{'=' * 60}")
    print(f"FOCAL {yr} ({src}) vs {title}   [Δ = focal - {ltm_lbl}]")
    print(f"{'=' * 60}")

    print(f"\n--- OVERALL STATISTICS (annualised) ---")
    _print_diff_block(avl.get("overall_statistics", {}))

    season = avl.get("season_statistics")
    if season:
        print(f"\n--- SEASON STATISTICS ---")
        if "windows" in season:
            for w in season["windows"]:
                print(f"\n  Window {w['window']} (season #{w['season_number']})")
                _print_methodology_summary(w.get("water_balance_methodology"))
                _print_diff_block(w["diff"])
        else:
            _print_methodology_summary(season.get("water_balance_methodology"))
            _print_diff_block(season["diff"])

    ann = avl.get("annual_summary", {}) or {}
    arm = ann.get("annual_rain_mm")
    print(f"\n--- ANNUAL SUMMARY ---")
    if arm:
        print(f"  Annual rainfall : focal={arm['focal']} mm | "
              f"{ltm_lbl}={arm[ltm_lbl]} mm | "
              f"Δ={arm['diff']:+.1f} ({_fmt_pct(arm.get('pct'))})")
    hs = ann.get("humid_status") or {}
    if hs:
        focal_state = ("humid" if hs.get("focal_is_humid") else
                        "not humid" if hs.get("focal_is_humid") is False else "n/a")
        print(f"  Humid status    : focal={focal_state} | "
              f"{ltm_lbl}={hs.get('ltm_humid', 'n/a')}")
        if hs.get("focal_humid_test"):
            print(f"                    test: {hs['focal_humid_test']}")

    spei = avl.get("spei")
    if spei:
        print(f"\n--- 5. SPEI (monthly/period summary, not seasonal) ---")
        summary = spei.get("summary") or {}
        if summary:
            print(
                f"  Mean SPEI       : focal={summary['focal_avg_spei']:.3f} | "
                f"{ltm_lbl}={summary['baseline_avg_spei']:.3f} | "
                f"Δ={summary['diff']:+.3f}"
            )
        monthly = spei.get("monthly") or []
        if monthly:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "focal_spei": f"{row['focal_spei']:.3f}" if _is_num(row.get("focal_spei")) else "n/a",
                    ltm_lbl: f"{row['baseline_avg_spei']:.3f}" if _is_num(row.get("baseline_avg_spei")) else "n/a",
                    "Δ": f"{row['diff']:+.3f}" if _is_num(row.get("diff")) else "n/a",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(pd.DataFrame(rows).to_string(index=False))
    spi = avl.get("spi")
    if spi:
        print(f"\n--- 6. SPI (monthly/period summary, not seasonal) ---")
        summary = spi.get("summary") or {}
        if summary:
            print(
                f"  Mean SPI        : focal={summary['focal_avg_spi']:.3f} | "
                f"{ltm_lbl}={summary['baseline_avg_spi']:.3f} | "
                f"Δ={summary['diff']:+.3f}"
            )
        monthly = spi.get("monthly") or []
        if monthly:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "focal_spi": f"{row['focal_spi']:.3f}" if _is_num(row.get("focal_spi")) else "n/a",
                    ltm_lbl: f"{row['baseline_avg_spi']:.3f}" if _is_num(row.get("baseline_avg_spi")) else "n/a",
                    "Δ": f"{row['diff']:+.3f}" if _is_num(row.get("diff")) else "n/a",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(pd.DataFrame(rows).to_string(index=False))

def _print_per_model_breakdown(per_model: List[Dict[str, Any]]) -> None:
    """
    Show each model's own future-vs-baseline diff before the ensemble means.
    Mirrors the ensemble sections (overall statistics + season statistics + annual rainfall) so the reader can see what each model contributes to the averages
    printed below — including what each model says about every fixed window/season.
    """
    if not per_model:
        return
    print(f"\n{'=' * 60}")
    print(f"PER-MODEL BREAKDOWN ({len(per_model)} model(s)) — feeds the ensemble means below")
    print(f"{'=' * 60}")
    for r in per_model:
        print(f"\n  Model: {r.get('_model')}")
        print(f"  --- Overall statistics (annualised) ---")
        _print_diff_block(r.get("overall_statistics", {}))

        season = r.get("season_statistics")
        if season:
            print(f"  --- Season statistics ---")
            if "windows" in season:
                for w in season.get("windows", []):
                    print(f"    Window {w.get('window')} (season #{w.get('season_number')}, "
                          f"n_baseline={w.get('n_baseline')}, n_future={w.get('n_future')})")
                    _print_methodology_summary(w.get("water_balance_methodology"))
                    _print_diff_block(w.get("diff", {}))
            elif season.get("diff"):
                print(f"    (n_baseline={season.get('n_baseline')}, "
                      f"n_future={season.get('n_future')})")
                _print_methodology_summary(season.get("water_balance_methodology"))
                _print_diff_block(season["diff"])

        arm = (r.get("annual_summary") or {}).get("annual_rain_mm") or {}
        if _is_num(arm.get("future")) and _is_num(arm.get("baseline_avg")):
            print(f"  Annual rainfall : future={arm['future']:.1f} mm | "
                  f"baseline={arm['baseline_avg']:.1f} mm | "
                  f"Δ={arm.get('diff', 0):+.1f} ({_fmt_pct(arm.get('pct'))})")

def print_report(r: Dict[str, Any], detailed: bool = True) -> None:
    if "error" in r:
        print(f"\nError: {r['error']}")
        _print_season_detection_summary(r.get("season_detection"))
        for f in r.get("failed_models", []):
            print(f"  - {f['model']}: {f['error']}")
        return

    n_total = r["n_models_ok"] + len(r["models_failed"])
    print(f"\n{'=' * 60}")
    print(f"ENSEMBLE: Baseline LTM {r['baseline_period']} vs Future LTM {r['future_period']}")
    print(f"{'=' * 60}")
    print(f"  Scenario : {r['scenario']}")
    print(f"  Models ok: {r['n_models_ok']}/{n_total}")
    print(f"  Δ        : future_ltm - baseline_ltm")
    print(f"  Uncertainty: σΔ=inter-model SD of Δ | Likely Δ=p17–p83 across models")
    if r.get("crop_name"):
        print(f"  Crop     : {r['crop_name']}")
    if r.get("calendar_source"):
        print(f"  Calendar : {r['calendar_source']} | system={r.get('calendar_system')}")
    if r["models_failed"]:
        print(f"  Failed   : {', '.join(f['model'] for f in r['models_failed'])}")
    _print_season_detection_summary(r.get("season_detection"))

    if detailed:
        _print_per_model_breakdown(r.get("per_model_results", []))

    if detailed:
        print(f"\n--- 1. RAW CLIMATE SUMMARY (ensemble) ---")
        _print_2level(r.get("raw_climate_summary", {}),
                      outer_label="Variable", inner_label="Stat", precision=3)

    print(f"\n--- 2. OVERALL STATISTICS (ensemble, both periods annualised) ---")
    _print_2level(r.get("overall_statistics", {}))

    season = r.get("season_statistics")
    if season:
        print(f"\n--- 3. SEASON STATISTICS  (Baseline LTM vs Future LTM) ---")
        if "windows" in season:
            for w in season["windows"]:
                print(f"\n  Window {w['window']} (season #{w['season_number']}, n_models={w['n_models']})")
                _print_methodology_summary(w.get("water_balance_methodology"))
                _print_2level(w["diff"])
        else:
            print(f"  (n_models={season['n_models']})")
            _print_methodology_summary(season.get("water_balance_methodology"))
            _print_2level(season["diff"])

    print(f"\n--- 4. ANNUAL SUMMARY (ensemble) ---")
    ann = r.get("annual_summary", {})
    foc = ann.get("annual_rain_mm_future")    or {}
    bas = ann.get("annual_rain_mm_baseline") or {}
    dif = ann.get("annual_rain_mm_diff")     or {}
    pct = ann.get("annual_rain_mm_pct")      or {}
    if _is_num(foc.get("mean")):
        parts = [f"future_ltm={foc['mean']:.1f} mm"]
        if _is_num(bas.get("mean")):
            parts.append(f"baseline_ltm={bas['mean']:.1f} mm")
        if _is_num(dif.get("mean")):
            tail = (f" ({_fmt_pct(pct.get('mean'))})"
                    if _is_num(pct.get("mean")) else "")
            parts.append(f"Δ={dif['mean']:+.1f}{tail}")
        print(f"  Annual rainfall  : {' | '.join(parts)}")
    print(f"  Humid (future)   : {ann.get('humid_future', 'n/a')}")
    print(f"  Humid (baseline) : {ann.get('humid_baseline', 'n/a')}")
    print()

    spei = r.get("spei")
    if spei:
        print(f"\n--- 5. SPEI (ensemble monthly/period summary, not seasonal) ---")
        summary = spei.get("summary") or {}
        if summary:
            print(
                f"  Mean SPEI       : future_ltm={summary.get('focal_avg_spei'):.3f} | "
                f"baseline_ltm={summary.get('baseline_avg_spei'):.3f} | "
                f"Δ={summary.get('diff'):+.3f}"
            )
        monthly = spei.get("monthly") or []
        if detailed and monthly:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "future_ltm_spei": f"{row['focal_spei']:.3f}" if _is_num(row.get("focal_spei")) else "n/a",
                    "baseline_ltm_spei": f"{row['baseline_avg_spei']:.3f}" if _is_num(row.get("baseline_avg_spei")) else "n/a",
                    "Δ": f"{row['diff']:+.3f}" if _is_num(row.get("diff")) else "n/a",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(pd.DataFrame(rows).to_string(index=False))
        print()
    spi = r.get("spi")
    if spi:
        print(f"\n--- 6. SPI (ensemble monthly/period summary, not seasonal) ---")
        summary = spi.get("summary") or {}
        if summary:
            print(
                f"  Mean SPI        : future_ltm={summary.get('focal_avg_spi'):.3f} | "
                f"baseline_ltm={summary.get('baseline_avg_spi'):.3f} | "
                f"Δ={summary.get('diff'):+.3f}"
            )
        monthly = spi.get("monthly") or []
        if detailed and monthly:
            rows = []
            for row in monthly:
                rows.append({
                    "date": row["date"],
                    "month": row["month"],
                    "future_ltm_spi": f"{row['focal_spi']:.3f}" if _is_num(row.get("focal_spi")) else "n/a",
                    "baseline_ltm_spi": f"{row['baseline_avg_spi']:.3f}" if _is_num(row.get("baseline_avg_spi")) else "n/a",
                    "Δ": f"{row['diff']:+.3f}" if _is_num(row.get("diff")) else "n/a",
                    "Δ%": _fmt_pct(row.get("pct")),
                })
            print(pd.DataFrame(rows).to_string(index=False))
        print()

    avb = r.get("focal_vs_baseline")
    if avb:
        _print_focal_vs_ltm(avb)
        print()
    avf = r.get("focal_vs_future")
    if avf:
        _print_focal_vs_ltm(avf)
        print()

    _print_runtime_summary((((r.get("metadata") or {}).get("timing") or {}).get("runtime_summary")))


def _annotate_cli_timing(
    result: Dict[str, Any],
    *,
    command_total_seconds: float,
    focal_prefetch_seconds: float = 0.0,
) -> Dict[str, Any]:
    """
    CLI output should expose whole-command wall-clock timing, not only the
    ensemble_compare() core loop. Preserve the lower-level timer separately.
    """
    meta = result.setdefault("metadata", {})
    timing = meta.setdefault("timing", {})
    if "ensemble_compare_seconds" not in timing and "total_seconds" in timing:
        timing["ensemble_compare_seconds"] = timing["total_seconds"]
    timing["focal_prefetch_seconds"] = round(focal_prefetch_seconds, 3)
    timing["total_seconds"] = round(command_total_seconds, 3)
    timing["command_total_seconds"] = round(command_total_seconds, 3)
    return result

# CLI
def main() -> int:
    if "--list-models" in sys.argv:
        print("Available NEX-GDDP-CMIP6 models:")
        for i, m in enumerate(NEX_GDDP_MODELS, 1):
            print(f"  {i:02d}. {m}")
        print("\nAvailable scenarios (canonical -> accepted aliases):")
        for canon in SSP_SCENARIOS:
            aliases = sorted(a for a, c in SCENARIO_ALIASES.items()
                             if c == canon and a != canon)
            extras = f"  (also: {', '.join(aliases)})" if aliases else ""
            print(f"  - {canon}{extras}")
        return 0

    p = argparse.ArgumentParser(
        description=(
            "Ensemble future-period-vs-baseline-period comparison across NEX-GDDP models. "
            "Requires multi-year baseline and future periods."
        ),
        formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--location",       required=True, help="lat,lon (e.g. -1.286,36.817)")
    p.add_argument("--baseline-start", type=int, required=True,
                   help="First year of baseline period (inclusive, multi-year only)")
    p.add_argument("--baseline-end",   type=int, required=True,
                   help="Last year of baseline period (inclusive, multi-year only)")
    p.add_argument("--future-start",    type=int, required=True,
                   help="First year of future period (inclusive, multi-year only)")
    p.add_argument("--future-end",      type=int, required=True,
                   help="Last year of future period (inclusive, multi-year only)")
    p.add_argument("--scenarios",      default="ssp245",
                   metavar="ssp245[,ssp585]",
                   help=("Comma-separated. Canonical: "
                         f"{', '.join(SSP_SCENARIOS)}.\n"
                         "Aliases also accepted: SSP1-2.6, SSP2-4.5, SSP5-8.5."))
    p.add_argument("--fixed-season",   default=None,
                   metavar="MM-DD:MM-DD[,MM-DD:MM-DD]",
                   help=("Optional. Same syntax as periods.py.\n"
                         "  Single        : '03-01:05-31'\n"
                         "  Two seasons   : '03-01:05-31,10-01:12-15'\n"
                         "  Year-crossing : '11-01:02-28'"))
    p.add_argument("--crop", default=None,
                   help="Optional crop used when requesting external calendar presets such as GGCMI.")
    p.add_argument("--calendar-source", choices=["ggcmi"], default=None,
                   help="Optional crop-calendar preset source to use if auto season detection is not reliable.")
    p.add_argument("--calendar-system", choices=list(CALENDAR_SYSTEM_CHOICES), default="rf",
                   help="Crop-calendar system when --calendar-source is used.")
    p.add_argument("--models",         help="Comma-separated subset of models")
    p.add_argument("--exclude-models", help="Comma-separated models to exclude")
    p.add_argument("--policy-profile", choices=POLICY_PROFILE_CHOICES, default="default",
                   help=POLICY_PROFILE_HELP)
    p.add_argument("--list-models",    action="store_true")
    p.add_argument("--focal-year",    type=int, default=None,
                   help="Optional. Single observed year to also compare against both the "
                        "baseline and future LTMs ('Focal vs Baseline/Future LTM').")
    p.add_argument("--focal-source",  default=None,
                   help=f"Source for --focal-year. Defaults to 'nex_gddp' (focal year "
                        f"drawn from the ensemble itself). External: "
                        f"{', '.join(sorted(SUPPORTED))}")
    p.add_argument("--focal-precip-source", default=None,
                   help="Required when --focal-source=paired. Example: chirps_v2 or chirps_v3_daily_rnl.")
    p.add_argument("--focal-temp-source", default=None,
                   help="Required when --focal-source=paired. Example: agera5 or era5.")
    p.add_argument("--output",         default=None, help="Save JSON result to this path")
    p.add_argument("--model-workers",  type=int, default=8,
                   help=("Parallel NEX-GDDP model workers for ensemble runs. "
                         "Practical guidance from local benchmarks: 8 = safe default, "
                         "12 = good for heavier jobs, 16 = aggressive upper practical setting. "
                         "Use 1 for serial deep debugging."))
    p.add_argument("--spei-scale-months", type=int, default=None,
                   help="Optional SPEI scale in months for baseline/future/focal comparisons.")
    p.add_argument("--spei-fit", choices=["ub-pwm", "empirical"], default="ub-pwm",
                   help="SPEI fitting method when --spei-scale-months is used.")
    p.add_argument("--spei-ref-start", default=None,
                   help="Optional SPEI reference-period start date.")
    p.add_argument("--spei-ref-end", default=None,
                   help="Optional SPEI reference-period end date.")
    p.add_argument("--spi-scale-months", type=int, default=None,
                   help="Optional SPI scale in months for baseline/future/focal comparisons.")
    p.add_argument("--spi-fit", choices=["ub-pwm", "empirical"], default="ub-pwm",
                   help="SPI fitting method when --spi-scale-months is used.")
    p.add_argument("--spi-ref-start", default=None,
                   help="Optional SPI reference-period start date.")
    p.add_argument("--spi-ref-end", default=None,
                   help="Optional SPI reference-period end date.")
    p.add_argument("--quiet",          action="store_true")
    p.add_argument("--verbose",        action="store_true",
                   help="Show detailed per-year season diagnostics and full per-model report.")
    args = p.parse_args()

    try:
        lat, lon = (float(x) for x in args.location.replace(" ", ",").split(","))
    except ValueError:
        print("Error: --location must be 'lat,lon'")
        return 1

    models  = [m.strip() for m in args.models.split(",")]         if args.models         else None
    exclude = [m.strip() for m in args.exclude_models.split(",")] if args.exclude_models else None

    # --focal-year with no --focal-source defaults to the NEX-GDDP ensemble itself, giving an all-NEX-GDDP focal/baseline/future comparison.
    if args.focal_year is not None and not args.focal_source:
        args.focal_source = "nex_gddp"
    focal_is_nexgddp = (args.focal_year is not None
                        and args.focal_source.lower() == "nex_gddp")
    if (args.focal_source and not focal_is_nexgddp
            and args.focal_source.lower() not in SUPPORTED):
        print(f"Error: --focal-source '{args.focal_source}' not supported. "
              f"Use 'nex_gddp' or one of: {', '.join(sorted(SUPPORTED))}")
        return 1
    if (args.focal_source and args.focal_source.lower() == "paired"
            and (not args.focal_precip_source or not args.focal_temp_source)):
        print("Error: --focal-source=paired requires both --focal-precip-source and --focal-temp-source.")
        return 1

    raw_scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    scenarios: List[str] = []
    invalid:   List[str] = []
    for s in raw_scenarios:
        canon = _normalize_scenario(s)
        if canon and canon not in scenarios:
            scenarios.append(canon)
        elif not canon:
            invalid.append(s)
    if invalid:
        print(f"Error: invalid scenario(s) {invalid}. "
              f"Accepted: {sorted(SCENARIO_ALIASES)}")
        return 1
    if not scenarios:
        print("Error: no scenarios provided.")
        return 1

    cli_started = perf_counter()
    focal_prefetch_seconds = 0.0

    # An external observed source (era_5, etc.) is scenario-independent, so the focal year is fetched once. A NEX-GDDP focal year inherits each scenario's run, so it is built per-scenario inside the loop below.
    focal_summary: Optional[Dict[str, Any]] = None
    if args.focal_year is not None and not focal_is_nexgddp:
        if not args.quiet:
            print(f"\nFetching focal year {args.focal_year} | "
                  f"source={args.focal_source}")
        focal_started = perf_counter()
        focal_summary = _build_focal_summary(
            location=(lat, lon),
            focal_year=args.focal_year,
            focal_source=args.focal_source,
            fixed_season=args.fixed_season,
            precip_source=args.focal_precip_source,
            temp_source=args.focal_temp_source,
            crop_name=args.crop,
            calendar_source=args.calendar_source,
            calendar_system=args.calendar_system,
            spei_scale_months=args.spei_scale_months,
            spei_fit=args.spei_fit,
            spei_ref_start=args.spei_ref_start,
            spei_ref_end=args.spei_ref_end,
            spi_scale_months=args.spi_scale_months,
            spi_fit=args.spi_fit,
            spi_ref_start=args.spi_ref_start,
            spi_ref_end=args.spi_ref_end,
            diagnostic_verbose=args.verbose,
        )
        focal_prefetch_seconds = perf_counter() - focal_started
        if (isinstance(focal_summary, dict)
                and not args.fixed_season
                and focal_summary.get("season_detection_status") == "prompt_required"):
            print(
                "Error: focal-year season detection not reliable enough for ensemble focal-vs-LTM comparison. "
                "Re-run with --fixed-season."
            )
            print(f"  Focal season detect : {focal_summary.get('season_detection_status')}")
            reasons = focal_summary.get("season_detection_reasons") or []
            if reasons:
                print(f"    reasons: {', '.join(reasons)}")
            guidance = focal_summary.get("season_detection_guidance") or []
            if guidance:
                print("    guidance:")
                for item in guidance:
                    print(f"      - {item}")
            return 1

    all_results: Dict[str, Any] = {}
    any_ok = False
    for scenario in scenarios:
        scenario_focal = focal_summary
        if focal_is_nexgddp:
            if not args.quiet:
                print(f"\nFetching focal year {args.focal_year} from NEX-GDDP "
                      f"ensemble | scenario={scenario}")
            scenario_focal = _build_focal_summary_nexgddp(
                location=(lat, lon),
                focal_year=args.focal_year,
                fixed_season=args.fixed_season,
                scenario=scenario,
                crop_name=args.crop,
                calendar_source=args.calendar_source,
                calendar_system=args.calendar_system,
                models=models,
                exclude_models=exclude,
                policy_profile=None if args.policy_profile == "default" else args.policy_profile,
                verbose=not args.quiet,
                diagnostic_verbose=args.verbose,
                spei_scale_months=args.spei_scale_months,
                spei_fit=args.spei_fit,
                spei_ref_start=args.spei_ref_start,
                spei_ref_end=args.spei_ref_end,
                spi_scale_months=args.spi_scale_months,
                spi_fit=args.spi_fit,
                spi_ref_start=args.spi_ref_start,
                spi_ref_end=args.spi_ref_end,
            )
        result = ensemble_compare(
            location=(lat, lon),
            baseline_start=args.baseline_start,
            baseline_end=args.baseline_end,
            future_start=args.future_start,
            future_end=args.future_end,
            scenario=scenario,
            fixed_season=args.fixed_season,
            crop_name=args.crop,
            calendar_source=args.calendar_source,
            calendar_system=args.calendar_system,
            models=models,
            exclude_models=exclude,
            policy_profile=None if args.policy_profile == "default" else args.policy_profile,
            focal_summary=scenario_focal,
            verbose=not args.quiet,
            diagnostic_verbose=args.verbose,
            model_workers=args.model_workers,
            spei_scale_months=args.spei_scale_months,
            spei_fit=args.spei_fit,
            spei_ref_start=args.spei_ref_start,
            spei_ref_end=args.spei_ref_end,
            spi_scale_months=args.spi_scale_months,
            spi_fit=args.spi_fit,
            spi_ref_start=args.spi_ref_start,
            spi_ref_end=args.spi_ref_end,
        )
        all_results[scenario] = result
        try:
            print_report(result, detailed=args.verbose)
        except TypeError:
            print_report(result)
        if "error" not in result:
            any_ok = True

    if not any_ok:
        return 1

    command_total_seconds = perf_counter() - cli_started
    for scenario, result in all_results.items():
        scenario_focal_seconds = 0.0
        if args.focal_year is not None:
            scenario_focal_seconds = focal_prefetch_seconds if not focal_is_nexgddp else 0.0
        all_results[scenario] = _annotate_cli_timing(
            result,
            command_total_seconds=command_total_seconds,
            focal_prefetch_seconds=scenario_focal_seconds,
        )

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
        # Single scenario -> bare result; multiple -> {scenario: result} map
        payload = all_results[scenarios[0]] if len(scenarios) == 1 else all_results
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"✓ Saved: {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

# NOTE: the 1st command in a section runs the documented NEX-GDDP model ensemble, the 2nd allows model selection.

# List available NEX-GDDP models and scenarios:
# python -m climate_tookit.compare_periods.ensemble_periods --list-models

# focal year from external observed source:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31" --scenarios ssp245 --focal-year 2019 --focal-source era_5 --output ensemble_mam_focal2019.json
# focal year from NEX-GDDP:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31" --scenarios ssp245 --focal-year 2019 --output ensemble_mam_focal2019.json

# Auto-detected season (no --fixed-season) -- all models, pick scenarios:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --scenarios ssp245,ssp585 --output ensemble_auto_all.json
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp245,ssp585 --output ensemble_auto.json

# Fixed single season:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31" --scenarios ssp245,ssp585 --output ensemble_mam_all.json
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp585 --output ensemble_mam.json

# Fixed two seasons:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31,10-01:12-15" --scenarios ssp245,ssp585 --output ensemble_mam_ond_all.json
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "03-01:05-31,10-01:12-15" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp245,ssp585 --output ensemble_mam_ond.json

# Fixed year-crossing season:
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "11-01:02-28" --scenarios ssp245,ssp585 --output ensemble_njf_all.json
# python -m climate_tookit.compare_periods.ensemble_periods --location="-1.286,36.817" --baseline-start 1991 --baseline-end 2020 --future-start 2040 --future-end 2060 --fixed-season "11-01:02-28" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp585 --output ensemble_njf.json
