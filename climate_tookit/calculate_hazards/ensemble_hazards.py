"""
Ensemble of hazards.py across NEX-GDDP models x scenarios.
For each (model, scenario) combination, runs same hazard assessment that
hazards.py produces, but with NEX-GDDP daily data.

Scenario boundaries are preserved during aggregation. Within each scenario,
ensemble means come from projection-level season statistics, while hazard
statuses are aggregated from projection-level hazard evaluations rather than
re-derived from climate means.

Modes:
  - default        : auto-detect seasons per (model, scenario) using NEX-GDDP.
  - --fixed-season : single, two, or year-crossing windows applied to each year.
"""

import os
import sys
import json
import argparse
from collections import Counter, defaultdict
from datetime import datetime, date
from statistics import mean
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd

from climate_tookit.calculate_hazards.hazards import (
    CROP_THRESHOLDS,
    HAZARD_EVAL_SPECS,
    HAZARD_PRINT_ORDER,
    evaluate_threshold,
    evaluate_hazard_metrics,
    calculate_season_statistics,
    build_water_balance_methodology,
    load_custom_thresholds_file,
    add_et0,
    FULL_WINDOW_WATER_BALANCE,
    CROP_ACTIVE_WATER_BALANCE,
    WATER_BALANCE_WINDOW_CHOICES,
    DEFAULT_SOILCP,
    DEFAULT_SOILSAT,
    DEFAULT_SPINUP_DAYS,
    _apply_water_balance_window_mode,
    _normalize_water_balance_window_mode,
    resolve_thresholds,
    resolve_crop_water_balance_params,
    _shift_iso_date,
    _print_hazard_season_detection_summary,
)
from climate_tookit.fetch_data.preprocess_data.preprocess_data import preprocess_data
from climate_tookit.fetch_data.source_data.sources.utils.models import ClimateVariable
from climate_tookit.fetch_data.source_data.sources.nex_gddp import (
    AVAILABLE_MODELS as MODELS,
    default_ensemble_models_for_location,
)
from climate_tookit.season_analysis.seasons import (
    fetch_and_analyze_years,
    detect_onset_cessation,
)

SCENARIOS = ['ssp126', 'ssp245', 'ssp370', 'ssp585']

_VARS   = [ClimateVariable.precipitation,
           ClimateVariable.max_temperature,
           ClimateVariable.min_temperature]
_COLMAP = {'pr': 'precipitation', 'prcp': 'precipitation',
           'tasmax': 'max_temperature', 'tasmin': 'min_temperature'}

# Fixed-season parsing & expansion
def _parse_fixed(spec: str) -> List[Tuple[str, str]]:
    """'MM-DD:MM-DD[,MM-DD:MM-DD]' -> [(onset, cessation), ...]"""
    out = []
    for token in spec.split(','):
        token = token.strip()
        if not token:
            continue
        if ':' not in token:
            raise ValueError(f"fixed-season token missing ':' -- {token!r}")
        onset, cessation = (s.strip() for s in token.split(':', 1))
        datetime.strptime(onset,     '%m-%d')   # validate
        datetime.strptime(cessation, '%m-%d')
        out.append((onset, cessation))
    if not out:
        raise ValueError("empty fixed-season specification")
    return out

def _yearcross(o: str, c: str) -> bool:
    return (datetime.strptime(c, '%m-%d').replace(year=2001)
          < datetime.strptime(o, '%m-%d').replace(year=2001))

def _isleap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _iso(year: int, mmdd: str) -> str:
    m, d = (int(x) for x in mmdd.split('-'))
    if m == 2 and d == 29 and not _isleap(year):
        d = 28
    return f"{year:04d}-{m:02d}-{d:02d}"

def _expand_windows(sy: int, ey: int,
                    defs: List[Tuple[str, str]]) -> List[Dict]:
    out = []
    for y in range(sy, ey + 1):
        for i, (o, c) in enumerate(defs, 1):
            out.append({
                'start':         _iso(y, o),
                'end':           _iso(y + 1 if _yearcross(o, c) else y, c),
                'season_number': i,
                'year':          y,
                'total':         len(defs),
            })
    return out

def _fixed_windows_cross_year(defs: List[Tuple[str, str]]) -> bool:
    return any(_yearcross(onset, cessation) for onset, cessation in defs)

def _year_crossing_tail_end(end_year: int, defs: List[Tuple[str, str]]) -> str | None:
    crossings = [cessation for onset, cessation in defs if _yearcross(onset, cessation)]
    if not crossings:
        return None
    return max(_iso(end_year + 1, cessation) for cessation in crossings)

def _prefetch_year_crossing_tail(
    lat: float,
    lon: float,
    end_year: int,
    models: List[str],
    scenarios: List[str],
    defs: List[Tuple[str, str]],
) -> None:
    tail_end = _year_crossing_tail_end(end_year, defs)
    if tail_end is None:
        return
    tail_start = f"{end_year + 1}-01-01"
    print(
        f"  Prefetching next-year tail for year-crossing fixed windows: "
        f"{tail_start} -> {tail_end}"
    )
    for scenario in scenarios:
        for model in models:
            print(f"    tail prefetch [{scenario}] {model}")
            try:
                preprocess_data(
                    source='nex_gddp',
                    location_coord=(lat, lon),
                    variables=_VARS,
                    date_from=date.fromisoformat(tail_start),
                    date_to=date.fromisoformat(tail_end),
                    model=model,
                    scenario=scenario,
                )
                print(f"      tail cache ready {tail_start}->{tail_end}")
            except Exception as exc:
                print(f"      tail prefetch failed: {exc}")

# NEX-GDDP fetching & per-window assessment
def _fetch(lat: float, lon: float, start: str, end: str,
           model: str, scenario: str) -> pd.DataFrame:
    df = preprocess_data(
        source='nex_gddp',
        location_coord=(lat, lon),
        variables=_VARS,
        date_from=date.fromisoformat(start),
        date_to=date.fromisoformat(end),
        model=model, scenario=scenario,
    )
    if df is None or df.empty:
        raise RuntimeError(f"no data for {model}/{scenario} {start}->{end}")
    rename = {c: _COLMAP[c] for c in df.columns if c in _COLMAP}
    if rename:
        df = df.rename(columns=rename)

    # Attach Hargreaves ET0 so calculate_season_statistics can derive NDWS / NDWL0.
    if {'min_temperature', 'max_temperature', 'date'}.issubset(df.columns):
        view = df.rename(columns={'min_temperature': 'tmin',
                                  'max_temperature': 'tmax'})
        df['ET0_mm_day'] = add_et0(view, lat)['ET0_mm_day'].values
    return df

def _detect_windows(lat: float, lon: float, sy: int, ey: int,
                    model: str, scenario: str) -> List[Dict]:
    """Auto-detect via fetch_and_analyze_years with NEX-GDDP source."""
    try:
        seasons_dict, _ = fetch_and_analyze_years(
            lat, lon, start_year=sy, end_year=ey,
            source='nex_gddp', model=model, scenario=scenario,
        )
    except TypeError as e:
        raise RuntimeError(
            "fetch_and_analyze_years did not accept NEX-GDDP arguments. "
            "Either add a NEX-GDDP branch to seasons.py or use --fixed-season. "
            f"({e})"
        )
    out = []
    for y, seasons in sorted(seasons_dict.items()):
        for i, s in enumerate(seasons, 1):
            if not s.get('cessation'):
                continue
            out.append({
                'start':         pd.to_datetime(s['onset']).strftime('%Y-%m-%d'),
                'end':           pd.to_datetime(s['cessation']).strftime('%Y-%m-%d'),
                'season_number': i,
                'year':          y,
                'total':         len(seasons),
            })
    if not out:
        year_label = f"{sy}" if sy == ey else f"{sy}-{ey}"
        raise RuntimeError(
            "No onset-year seasons found in requested auto-detect range "
            f"{year_label} for model={model} scenario={scenario}. "
            "Season detection reassigns results to onset year, so narrow ranges "
            "can end up empty. Widen year range or use --fixed-season."
        )
    return out

def _evaluate(crop: str, lat: float, lon: float,
              w: Dict, model: str, scenario: str,
              thresholds: Dict[str, Dict[str, Tuple]],
              soilcp: float = DEFAULT_SOILCP,
              soilsat: float = DEFAULT_SOILSAT) -> Dict:
    """hazards.py-style assessment for a single window using NEX-GDDP."""
    crop_params = resolve_crop_water_balance_params(crop.capitalize())
    water_balance_window = _normalize_water_balance_window_mode(
        w.get("water_balance_window", FULL_WINDOW_WATER_BALANCE)
    )
    fetch_start = _shift_iso_date(w['start'], -DEFAULT_SPINUP_DAYS)
    df = _fetch(lat, lon, fetch_start, w['end'], model, scenario)
    soil_parameters = {
        "soilcp": soilcp,
        "soilsat": soilsat,
        "root_depth_m": crop_params.get("root_depth_m"),
    }
    season_info = {
        **w,
        "onset_date": w["start"],
        "cessation_date": w["end"],
        "fetch_start_date": fetch_start,
        "spinup_days": DEFAULT_SPINUP_DAYS,
        "method": "fixed_season" if w.get("fixed_season") else "rainfall_based",
        "source": "nex_gddp",
    }
    stats = calculate_season_statistics(
        df,
        soilcp=soilcp,
        soilsat=soilsat,
        kc=float(crop_params.get("kc_mid", 1.0)),
        kc_init=float(crop_params.get("kc_init", crop_params.get("kc_mid", 1.0))),
        kc_mid=float(crop_params.get("kc_mid", 1.0)),
        kc_end=float(crop_params.get("kc_end", crop_params.get("kc_mid", 1.0))),
        depletion_fraction_p=float(crop_params.get("depletion_fraction_p", 0.5)),
        analysis_start=w['start'],
        analysis_end=w['end'],
    )
    eto_seasons = []
    eto_detection_note = None
    if water_balance_window == CROP_ACTIVE_WATER_BALANCE and w.get("fixed_season"):
        window_df = df[
            (pd.to_datetime(df["date"]) >= pd.Timestamp(w["start"])) &
            (pd.to_datetime(df["date"]) <= pd.Timestamp(w["end"]))
        ].copy()
        if len(window_df) < 14:
            eto_detection_note = "ETO window too short for detection (<14 days)."
        else:
            try:
                eto_seasons = detect_onset_cessation(window_df)
                if not eto_seasons:
                    eto_detection_note = "No ETO sub-season detected within fixed window."
            except Exception as exc:
                eto_detection_note = str(exc)
                eto_seasons = []
    stats, count_window = _apply_water_balance_window_mode(
        stats,
        df,
        season_info,
        soil_parameters,
        crop_params,
        water_balance_window=water_balance_window,
        eto_seasons=eto_seasons,
        eto_detection_note=eto_detection_note,
    )
    hazards = evaluate_hazard_metrics(stats, thresholds)
    methodology = build_water_balance_methodology(
        season_info,
        soil_parameters,
        crop_params,
        count_window=count_window,
    )
    length = (
        datetime.fromisoformat(w['end'])
        - datetime.fromisoformat(w['start'])
    ).days + 1
    return {
        'season_info': {**season_info, 'length_days': length},
        'season_statistics': stats,
        'water_balance_methodology': methodology,
        'hazard_evaluation': hazards,
        'projection': {'model': model, 'scenario': scenario},
    }

# Aggregation -- ensemble means
_SCALAR_KEYS = ['total_precipitation_mm', 'mean_daily_precipitation_mm',
                'max_daily_precipitation_mm', 'rainy_days', 'dry_days',
                'mean_temperature_c', 'mean_tmax_c', 'mean_tmin_c',
                'max_temperature_c', 'min_temperature_c',
                # Canonical hazard variables added in hazards.py
                'max_tmax_c', 'min_tmin_c',
                'NDD', 'NTx35', 'NTx40', 'NDWS', 'NDWL0']

def _avg_stats(rs: List[Dict]) -> Dict:
    out = {}
    if not rs:
        return out
    for k in _SCALAR_KEYS:
        vs = [r['season_statistics'][k]
              for r in rs if k in r.get('season_statistics', {})]
        if vs:
            out[k] = round(mean(vs), 2)

    counts, max_l, mean_l = [], [], []
    bucket_sums: Dict[str, float] = defaultdict(float)
    for r in rs:
        ds = r.get('season_statistics', {}).get('dry_spell_statistics')
        if not ds:
            continue
        counts.append(ds['number_of_dry_spells'])
        max_l.append(ds['max_dry_spell_length_days'])
        if ds['number_of_dry_spells'] > 0:
            mean_l.append(ds['mean_dry_spell_length_days'])
        for bucket, n in (ds.get('length_distribution') or {}).items():
            bucket_sums[bucket] += n

    if counts:
        ds_out = {
            'number_of_dry_spells':       round(mean(counts), 2),
            'max_dry_spell_length_days':  round(mean(max_l), 2)  if max_l  else 0,
            'mean_dry_spell_length_days': round(mean(mean_l), 2) if mean_l else 0,
        }
        if bucket_sums:
            n_total = len(rs)
            ds_out['length_distribution'] = {
                b: round(total / n_total, 2) for b, total in bucket_sums.items()
            }
        out['dry_spell_statistics'] = ds_out
    return out

def _aggregate_hazard_statuses(bucket: List[Dict], agg: Dict) -> Dict:
    out: Dict[str, Dict] = {}
    specs = [spec for spec in HAZARD_EVAL_SPECS.values()]
    for spec in specs:
        hazard_key = spec['result_key']
        value_key = spec['value_key']
        agg_key = spec['stat_key']
        statuses = []
        for r in bucket:
            hazard = (r.get('hazard_evaluation') or {}).get(hazard_key) or {}
            status = hazard.get('status')
            if status:
                statuses.append(status)
        if not statuses:
            continue
        counts = Counter(statuses)
        dominant_status, dominant_count = sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
        n_status = len(statuses)
        status_counts = dict(sorted(counts.items()))
        out[hazard_key] = {
            value_key: agg.get(agg_key),
            'status': dominant_status if len(status_counts) == 1 else 'mixed',
            'dominant_status': dominant_status,
            'dominant_share': round(dominant_count / n_status, 3),
            'status_counts': status_counts,
            'status_shares': {
                status: round(count / n_status, 3)
                for status, count in status_counts.items()
            },
            'n_projections': n_status,
        }
    return out


def _auto_season_slot_warning(assessments: List[Dict]) -> Optional[str]:
    counts_by_scenario_year: Dict[str, Dict[int, int]] = defaultdict(dict)
    for assessment in assessments or []:
        scenario = assessment.get('scenario')
        year = assessment.get('year')
        total = assessment.get('total_seasons_per_year')
        if isinstance(scenario, str) and isinstance(year, int) and isinstance(total, int):
            counts_by_scenario_year[scenario][year] = total

    summaries: List[str] = []
    for scenario, year_counts in sorted(counts_by_scenario_year.items()):
        observed = set(year_counts.values())
        if len(observed) <= 1:
            continue
        summary = ", ".join(
            f"{year}:{count}" for year, count in sorted(year_counts.items())
        )
        summaries.append(f"{scenario} -> {summary}")

    if not summaries:
        return None
    return (
        "Auto-detected season counts differ across years within scenario, so "
        "scenario_ensembles by season_number would blend incomparable seasons. "
        f"Counts by scenario/year: {'; '.join(summaries)}. "
        "Use --fixed-season for stable ensemble season summaries."
    )


def _build_ensemble_hazard_season_detection(
    *,
    mode: str,
    warning: Optional[str],
    assessments: List[Dict],
) -> Dict[str, Any]:
    counts_by_scenario_year: Dict[str, Dict[str, int]] = defaultdict(dict)
    for assessment in assessments or []:
        scenario = assessment.get("scenario")
        year = assessment.get("year")
        total = assessment.get("total_seasons_per_year")
        if isinstance(scenario, str) and isinstance(year, int) and isinstance(total, int):
            counts_by_scenario_year[scenario][str(year)] = total

    if warning:
        return {
            "status": "prompt_required",
            "reasons": ["unstable_season_counts"],
            "human_review_recommended": True,
            "calendar_override_recommended": True,
            "guidance": [
                "Auto season detection is not stable enough for comparable ensemble hazard summaries. Use --fixed-season."
            ],
            "details": {
                "mode": mode,
                "counts_by_scenario_year": dict(counts_by_scenario_year),
                "warning": warning,
            },
        }

    if mode == "fixed_season":
        return {
            "status": "ok",
            "reasons": ["fixed_season_override"],
            "human_review_recommended": False,
            "calendar_override_recommended": False,
            "guidance": [],
            "details": {
                "mode": mode,
                "counts_by_scenario_year": dict(counts_by_scenario_year),
            },
        }

    return {
        "status": "ok",
        "reasons": [],
        "human_review_recommended": False,
        "calendar_override_recommended": False,
        "guidance": [],
        "details": {
            "mode": mode,
            "counts_by_scenario_year": dict(counts_by_scenario_year),
        },
    }

# Driver
def calculate_ensemble(crop: str, lat: float, lon: float,
                       start_year: int, end_year: int,
                       models: List[str], scenarios: List[str],
                       fixed_season: Optional[str] = None,
                       custom_thresholds: Optional[Dict[str, Dict[str, Tuple]]] = None,
                       soilcp: float = DEFAULT_SOILCP,
                       soilsat: float = DEFAULT_SOILSAT,
                       water_balance_window: str = FULL_WINDOW_WATER_BALANCE) -> Dict:
    water_balance_window = _normalize_water_balance_window_mode(water_balance_window)
    mode = 'fixed_season' if fixed_season else 'auto_detect'
    fixed_defs = _parse_fixed(fixed_season) if fixed_season else None
    fixed_w = (_expand_windows(start_year, end_year, fixed_defs)
               if fixed_defs else None)
    thresholds = resolve_thresholds(crop.capitalize(), custom_thresholds)

    print(f"\nNEX-GDDP ensemble: {crop} at ({lat:.4f}, {lon:.4f})  "
          f"{start_year}-{end_year}")
    print(f"  Mode: {mode}" + (f"  ({fixed_season})" if fixed_season else ""))
    print(f"  Models: {len(models)}   Scenarios: {len(scenarios)}\n")
    if fixed_defs and _fixed_windows_cross_year(fixed_defs):
        print(
            f"  ! Year-crossing fixed window detected. Final requested year {end_year} "
            f"needs following-year tail data ({end_year + 1}) to complete last season.\n"
        )
        _prefetch_year_crossing_tail(
            lat=lat,
            lon=lon,
            end_year=end_year,
            models=models,
            scenarios=scenarios,
            defs=fixed_defs,
        )

    results: List[Dict] = []
    for sc in scenarios:
        for i, m in enumerate(models, 1):
            print(f"  [{sc}] [{i}/{len(models)}] {m}")
            try:
                windows = (fixed_w if fixed_w is not None
                           else _detect_windows(lat, lon, start_year, end_year, m, sc))
            except Exception as e:
                print(f"      ! detection failed: {e}")
                continue
            for w in windows:
                window_payload = {
                    **w,
                    "fixed_season": bool(fixed_season),
                    "water_balance_window": water_balance_window,
                }
                tag = f"y{w['year']} s{w['season_number']}/{w['total']} {w['start']}->{w['end']}"
                try:
                    results.append(_evaluate(crop, lat, lon, window_payload, m, sc,
                                             thresholds=thresholds,
                                             soilcp=soilcp, soilsat=soilsat))
                    print(f"      {tag}  ✓")
                except Exception as e:
                    print(f"      {tag}  ✗ {e}")
    if not results:
        return {'error': 'No projections succeeded.'}

    # Bucket by (scenario, year, season_number) so SSPs never pool together.
    buckets: Dict[Tuple[str, int, int], List[Dict]] = defaultdict(list)
    for r in results:
        si = r['season_info']
        sc = r['projection']['scenario']
        buckets[(sc, si['year'], si['season_number'])].append(r)

    assessments = []
    for (sc, y, sn), bucket in sorted(buckets.items()):
        agg     = _avg_stats(bucket)
        onsets  = sorted(pd.to_datetime(r['season_info']['start']) for r in bucket)
        ends    = sorted(pd.to_datetime(r['season_info']['end'])   for r in bucket)
        lengths = [r['season_info']['length_days'] for r in bucket]
        total   = max(r['season_info']['total'] for r in bucket)
        projections = []
        for r in bucket:
            st = r.get('season_statistics', {})
            projections.append({
                'model':                  r['projection']['model'],
                'scenario':               r['projection']['scenario'],
                'total_precipitation_mm': st.get('total_precipitation_mm'),
                'rainy_days':             st.get('rainy_days'),
                'mean_temperature_c':     st.get('mean_temperature_c'),
                'mean_tmax_c':            st.get('mean_tmax_c'),
                'mean_tmin_c':            st.get('mean_tmin_c'),
                'max_tmax_c':             st.get('max_tmax_c'),
                'min_tmin_c':             st.get('min_tmin_c'),
                'NDD':                    st.get('NDD'),
                'NTx35':                  st.get('NTx35'),
                'NTx40':                  st.get('NTx40'),
                'NDWS':                   st.get('NDWS'),
                'NDWL0':                  st.get('NDWL0'),
            })
        assessments.append({
            'scenario':               sc,
            'year':                   y,
            'season_number':          sn,
            'total_seasons_per_year': total,
            'n_projections':          len(bucket),
            'window': {
                'start_median':     onsets[len(onsets) // 2].strftime('%Y-%m-%d'),
                'end_median':       ends[len(ends)     // 2].strftime('%Y-%m-%d'),
                'length_days_mean': round(mean(lengths), 1),
            },
            'projections':       projections,
            'water_balance_methodology': bucket[0].get('water_balance_methodology'),
            'season_statistics': agg,
            'hazard_evaluation': _aggregate_hazard_statuses(bucket, agg),
        })

    season_slot_warning = None
    if mode == 'auto_detect':
        season_slot_warning = _auto_season_slot_warning(assessments)
    season_detection = _build_ensemble_hazard_season_detection(
        mode=mode,
        warning=season_slot_warning,
        assessments=assessments,
    )

    scenario_ensembles = []
    if not season_slot_warning:
        summary_buckets: Dict[Tuple[str, int, int], List[Dict]] = defaultdict(list)
        for r in results:
            si = r['season_info']
            sc = r['projection']['scenario']
            summary_buckets[(sc, si['season_number'], si['total'])].append(r)

        for (sc, sn, total), bucket in sorted(summary_buckets.items()):
            agg = _avg_stats(bucket)
            scenario_ensembles.append({
                'scenario': sc,
                'season_number': sn,
                'total_seasons_per_year': total,
                'n_projections': len(bucket),
                'water_balance_methodology': bucket[0].get('water_balance_methodology'),
                'season_statistics': agg,
                'hazard_evaluation': _aggregate_hazard_statuses(bucket, agg),
            })

    overall_ensemble = None
    unique_season_slots = sorted(
        {(r['season_info']['season_number'], r['season_info']['total']) for r in results}
    )
    cross_scenario_rollup_disabled = len(scenarios) > 1
    cross_season_rollup_disabled = len(unique_season_slots) > 1
    if (not season_slot_warning
            and not cross_scenario_rollup_disabled
            and not cross_season_rollup_disabled):
        overall = _avg_stats(results)
        overall_ensemble = {
            'n_projections': len(results),
            'water_balance_methodology': results[0].get('water_balance_methodology'),
            'season_statistics': overall,
            'hazard_evaluation': _aggregate_hazard_statuses(results, overall),
            'scenario': scenarios[0] if scenarios else None,
            'scenarios': sorted({r['projection']['scenario'] for r in results}),
            'mixed_scenarios': False,
        }

    out = {
        'crop':              crop,
        'location':          {'latitude': lat, 'longitude': lon},
        'data_source':       'nex_gddp',
        'period':            {'start_year': start_year, 'end_year': end_year},
        'season_mode':       mode,
        'season_definition': fixed_season,
        'soil_water_balance': {
            'soilcp': soilcp,
            'soilsat': soilsat,
            'water_balance_window': water_balance_window,
        },
        'water_balance_methodology': results[0].get('water_balance_methodology'),
        'models':            models,
        'scenarios':         scenarios,
        'n_total_projections': len(results),
        'assessments':       assessments,
        'scenario_ensembles': scenario_ensembles,
        'overall_ensemble':   overall_ensemble,
        'season_detection':   season_detection,
    }
    warnings: List[str] = []
    if season_slot_warning:
        warnings.append(season_slot_warning)
        out['season_slot_warning'] = season_slot_warning
    if cross_scenario_rollup_disabled:
        warnings.append(
            'Cross-scenario pooled overall ensemble disabled. '
            'Interpret scenario_ensembles and scenario-tagged assessments separately.'
        )
    elif cross_season_rollup_disabled:
        warnings.append(
            'Cross-season pooled overall ensemble disabled. '
            'Interpret scenario_ensembles and assessments by season_number.'
        )
    if warnings:
        out['warning'] = " ".join(warnings)
    return out

# Pretty printer (mirrors hazards.py year/season blocks)
def _sym(status: str) -> str:
    if status == 'mixed':
        return '??'
    return 'OK' if 'no_stress' in status else '!!' if 'moderate' in status else 'XX'

def _fmt_status_counts(block: Dict) -> str:
    counts = block.get('status_counts') or {}
    if not counts:
        return 'n/a'
    return ', '.join(f"{status}={count}" for status, count in sorted(counts.items()))

def _bucket_key(b: str) -> int:
    try:
        return int(b.split('-')[0])
    except (ValueError, IndexError):
        return 999

def _fmt(v, nd=2):
    """Format a numeric value, or 'n/a' for None — used in per-projection tables."""
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "n/a"

def _hazard_spec_by_result_key(result_key: str) -> Optional[Dict[str, str]]:
    for spec in HAZARD_EVAL_SPECS.values():
        if spec['result_key'] == result_key:
            return spec
    return None

def _print_projection_breakdown(a: Dict) -> None:
    """
    Show each contributing (model, scenario) projection before the ensemble means,
    so the reader can see what feeds the averages for this year/season.
    """
    projections = a.get('projections') or []
    if not projections:
        return
    print(f"\n  Per-Projection Breakdown  ({len(projections)} projection(s) → ensemble mean)")
    print(f"  {'─'*66}")
    rows = []
    for p in projections:
        rows.append({
            'Model':    p.get('model'),
            'Scenario': p.get('scenario'),
            'Precip_mm': _fmt(p.get('total_precipitation_mm')),
            'Rainy_d':   _fmt(p.get('rainy_days')),
            'Tmean_c':   _fmt(p.get('mean_temperature_c')),
            'Tmax_c':    _fmt(p.get('mean_tmax_c')),
            'Tmin_c':    _fmt(p.get('mean_tmin_c')),
            'NTx35':     _fmt(p.get('NTx35'), 0),
            'NTx40':     _fmt(p.get('NTx40'), 0),
            'NDD':       _fmt(p.get('NDD'), 0),
            'NDWS':      _fmt(p.get('NDWS'), 0),
            'NDWL0':     _fmt(p.get('NDWL0'), 0),
        })
    s = a['season_statistics']
    rows.append({
        'Model':     f"ENSEMBLE (mean of {len(projections)})",
        'Scenario':  '',
        'Precip_mm': _fmt(s.get('total_precipitation_mm')),
        'Rainy_d':   _fmt(s.get('rainy_days')),
        'Tmean_c':   _fmt(s.get('mean_temperature_c')),
        'Tmax_c':    _fmt(s.get('mean_tmax_c')),
        'Tmin_c':    _fmt(s.get('mean_tmin_c')),
        'NTx35':     _fmt(s.get('NTx35')),
        'NTx40':     _fmt(s.get('NTx40')),
        'NDD':       _fmt(s.get('NDD')),
        'NDWS':      _fmt(s.get('NDWS')),
        'NDWL0':     _fmt(s.get('NDWL0')),
    })
    for line in pd.DataFrame(rows).to_string(index=False).splitlines():
        print(f"  {line}")

def _print_block(a: Dict, crop: str, lat: float, lon: float,
                 mode: str, n_models: int, n_scenarios: int) -> None:
    y, sn, t = a['year'], a['season_number'], a['total_seasons_per_year']
    label = f"Year {y}  -  Season {sn} of {t}" if t > 1 else f"Year {y}"
    scenario = a.get('scenario')

    print(f"\n{'─'*70}")
    print(f"  {label}  [{scenario}]   (ensemble of {a['n_projections']} projections)")
    print(f"\n{'='*70}")
    print(f"  CROP HAZARD ASSESSMENT (ENSEMBLE): {crop.upper()}")
    print(f"{'='*70}")
    print(f"  Location: {lat:.4f}, {lon:.4f}")

    w = a['window']
    print(f"\n  Season Information")
    print(f"  {'─'*66}")
    print(f"  Onset (median):  {w['start_median']:<20} End (median): {w['end_median']}")
    print(f"  Length (mean):   {w['length_days_mean']} days{'':10} Method: {mode}")
    print(f"  Source:          nex_gddp ({n_models} models × {n_scenarios} scenarios)")

    _print_projection_breakdown(a)

    s = a['season_statistics']
    if 'total_precipitation_mm' in s:
        print(f"\n  Precipitation Statistics  (ensemble means)")
        print(f"  {'─'*66}")
        print(f"  {'Metric':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        print(f"  {'Total':<32} {s['total_precipitation_mm']:>15.2f}  mm")
        print(f"  {'Daily Mean':<32} {s.get('mean_daily_precipitation_mm', 0):>15.2f}  mm")
        print(f"  {'Daily Maximum':<32} {s.get('max_daily_precipitation_mm', 0):>15.2f}  mm")
        print(f"  {'Rainy Days (>=1mm)':<32} {s.get('rainy_days', 0):>15.2f}  days")
        print(f"  {'Dry Days (<1mm)':<32} {s.get('dry_days', 0):>15.2f}  days")

    if 'dry_spell_statistics' in s:
        ds = s['dry_spell_statistics']
        print(f"\n  Dry Spell Statistics  (ensemble means; >=7 consecutive days <1mm)")
        print(f"  {'─'*66}")
        print(f"  {'Number of Dry Spells':<32} {ds['number_of_dry_spells']:>15.2f}  spells")
        print(f"  {'Max Dry Spell Length':<32} {ds['max_dry_spell_length_days']:>15.2f}  days")
        print(f"  {'Mean Dry Spell Length':<32} {ds['mean_dry_spell_length_days']:>15.2f}  days")

        if ds.get('length_distribution'):
            print(f"\n  Length Distribution  (mean spell count per bucket)")
            print(f"  {'─'*66}")
            for rng in sorted(ds['length_distribution'].keys(), key=_bucket_key):
                cnt = ds['length_distribution'][rng]
                print(f"  {rng:<15} days: {cnt:>6.2f} spell(s)")

    if 'mean_temperature_c' in s:
        print(f"\n  Temperature Statistics  (ensemble means)")
        print(f"  {'─'*66}")
        print(f"  {'Metric':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        print(f"  {'Mean Temperature':<32} {s['mean_temperature_c']:>15.2f}  deg C")
        print(f"  {'Mean Tmax':<32} {s.get('mean_tmax_c', 0):>15.2f}  deg C")
        print(f"  {'Mean Tmin':<32} {s.get('mean_tmin_c', 0):>15.2f}  deg C")
        print(f"  {'Max Tmax':<32} {s.get('max_tmax_c', s.get('max_temperature_c', 0)):>15.2f}  deg C")
        print(f"  {'Min Tmin':<32} {s.get('min_tmin_c', s.get('min_temperature_c', 0)):>15.2f}  deg C")

    # Hazard index counts (NTx35, NTx40, NDD, NDWS, NDWL0) -- ensemble means
    has_counts = any(k in s for k in ('NTx35', 'NTx40', 'NDD', 'NDWS', 'NDWL0', 'WRSI'))
    if has_counts:
        print(f"\n  Hazard Index Counts  (ensemble means)")
        print(f"  {'─'*66}")
        print(f"  {'Index':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        if 'WRSI' in s:
            print(f"  {'WRSI (seasonal satisfaction)':<32} {s['WRSI']:>15.2f}  %")
        if 'crop_water_requirement_mm' in s:
            print(f"  {'Crop Water Requirement':<32} {s['crop_water_requirement_mm']:>15.2f}  mm")
        if 'actual_crop_et_mm' in s:
            print(f"  {'Actual Crop ET':<32} {s['actual_crop_et_mm']:>15.2f}  mm")
        if 'NTx35' in s:
            print(f"  {'NTx35 (days Tmax > 35C)':<32} {s['NTx35']:>15.2f}  days")
        if 'NTx40' in s:
            print(f"  {'NTx40 (days Tmax > 40C)':<32} {s['NTx40']:>15.2f}  days")
        if 'NDD' in s:
            print(f"  {'NDD (dry days, <1mm)':<32} {s['NDD']:>15.2f}  days")
        if 'NDWS' in s:
            print(f"  {'NDWS (water-stress days)':<32} {s['NDWS']:>15.2f}  days")
        if 'NDWL0' in s:
            print(f"  {'NDWL0 (water-logging days)':<32} {s['NDWL0']:>15.2f}  days")
        if 'NDWS' in s or 'NDWL0' in s:
            print("  Note: NDWS/NDWL0 come from crop water-balance model, not raw precip-minus-ET0 counts.")
            methodology = a.get("water_balance_methodology") or {}
            count_window = methodology.get("count_window") or {}
            if count_window.get("applied_mode") == CROP_ACTIVE_WATER_BALANCE:
                print("  Count window: crop-active ETO sub-season(s) inside fixed window.")

    h = a['hazard_evaluation']
    print(f"\n  Hazard Assessment  (aggregated from projection statuses)")
    print(f"  {'─'*66}")
    print(f"  {'Indicator':<25} {'Value':>18}  Status")
    print(f"  {'─'*25} {'─'*18}  {'─'*20}")
    for result_key in HAZARD_PRINT_ORDER:
        if result_key not in h:
            continue
        spec = _hazard_spec_by_result_key(result_key)
        item = h[result_key]
        value = item.get(spec['value_key'])
        print(f"  {spec['label']:<25} {value:>16.2f} {spec['unit']:<4} "
              f"[{_sym(item['status'])}] {item['status'].replace('_', ' ').upper()}")
        print(f"  {'':<25} {'':>18}  distribution: {_fmt_status_counts(item)}")
    print(f"\n{'='*70}")

def _print_overall_summary(summary: Dict, multi_scenario: bool) -> None:
    scenario = summary.get('scenario')
    s = summary.get('season_statistics', {})
    h = summary.get('hazard_evaluation', {})
    print(f"\n{'─'*70}")
    if multi_scenario:
        slot = summary.get('season_number')
        total = summary.get('total_seasons_per_year')
        if slot and total and total > 1:
            print(f"  SCENARIO ENSEMBLE  [{scenario}]  season {slot}/{total}")
        else:
            print(f"  SCENARIO ENSEMBLE  [{scenario}]")
    else:
        print("  OVERALL ENSEMBLE")
    print(f"  n = {summary['n_projections']} projections")
    if summary.get('warning'):
        print(f"  Warning: {summary['warning']}")
    print(f"  {'─'*66}")
    print(f"  Precipitation (mean): {s.get('total_precipitation_mm', 0):.2f} mm per season")
    print(f"  Temperature   (mean): {s.get('mean_temperature_c', 0):.2f} deg C")
    if 'max_tmax_c' in s or 'min_tmin_c' in s:
        print(f"  Max Tmax / Min Tmin : {s.get('max_tmax_c', 0):.2f} / "
              f"{s.get('min_tmin_c', 0):.2f} deg C")
    if any(k in s for k in ('NTx35', 'NTx40', 'NDD', 'NDWS', 'NDWL0', 'WRSI')):
        parts = []
        if 'WRSI' in s: parts.append(f"WRSI={s['WRSI']:.2f}%")
        if 'NTx35' in s: parts.append(f"NTx35={s['NTx35']:.2f}")
        if 'NTx40' in s: parts.append(f"NTx40={s['NTx40']:.2f}")
        if 'NDD'   in s: parts.append(f"NDD={s['NDD']:.2f}")
        if 'NDWS'  in s: parts.append(f"NDWS={s['NDWS']:.2f}")
        if 'NDWL0' in s: parts.append(f"NDWL0={s['NDWL0']:.2f}")
        print(f"  Hazard indices      : {'  '.join(parts)}  (mean days per season)")
        methodology = summary.get("water_balance_methodology") or {}
        count_window = methodology.get("count_window") or {}
        if count_window.get("applied_mode") == CROP_ACTIVE_WATER_BALANCE:
            print("  Count window        : crop-active ETO sub-season(s) inside fixed window")
    if 'dry_spell_statistics' in s:
        ds = s['dry_spell_statistics']
        print(f"  Dry spells    (mean): {ds['number_of_dry_spells']:.2f} per season  "
              f"(max length {ds['max_dry_spell_length_days']:.2f} days)")
    for result_key in HAZARD_PRINT_ORDER:
        if result_key not in h:
            continue
        spec = _hazard_spec_by_result_key(result_key)
        print(f"  {spec['label']:<18} status: [{_sym(h[result_key]['status'])}] "
              f"{h[result_key]['status'].replace('_', ' ').upper()} "
              f"({_fmt_status_counts(h[result_key])})")

def print_results(r: Dict) -> None:
    if 'error' in r:
        print(f"\nError: {r['error']}")
        _print_hazard_season_detection_summary(r.get('season_detection'))
        return

    crop = r['crop']
    lat, lon = r['location']['latitude'], r['location']['longitude']
    mode = r['season_mode'] + (f" ({r['season_definition']})" if r.get('season_definition') else '')
    nm, ns = len(r['models']), len(r['scenarios'])

    print(f"\n{'='*70}")
    print(f"  ENSEMBLE HAZARD ASSESSMENT (NEX-GDDP)")
    print(f"{'='*70}")
    print(f"  Crop:              {crop}")
    print(f"  Location:          {lat:.4f}, {lon:.4f}")
    print(f"  Period:            {r['period']['start_year']} -> {r['period']['end_year']}")
    print(f"  Mode:              {mode}")
    print(f"  Models:            {nm}")
    print(f"  Scenarios:         {', '.join(r['scenarios'])}")
    print(f"  Total projections: {r['n_total_projections']}")
    _print_hazard_season_detection_summary(r.get('season_detection'))

    for a in r['assessments']:
        _print_block(a, crop, lat, lon, mode, nm, ns)

    summaries = r.get('scenario_ensembles') or []
    if len(summaries) > 1:
        print(f"\n{'─'*70}")
        print("  Scenario boundaries preserved in scenario_ensembles and assessments.")
        for summary in summaries:
            _print_overall_summary(summary, multi_scenario=True)
    if r.get('warning'):
        print(f"\n  Warning: {r['warning']}")
    if r.get('overall_ensemble'):
        _print_overall_summary(r['overall_ensemble'], multi_scenario=False)
    print(f"\n{'='*70}\n")

def main() -> int:
    p = argparse.ArgumentParser(
        description='Ensemble of hazards.py across NEX-GDDP models x scenarios.',
    )
    p.add_argument('crop', nargs='?', default='maize',
                   help='Crop name (default: maize). Same options as hazards.py.')
    p.add_argument('--list-models', action='store_true',
                   help='Print available models & scenarios, then exit.')
    p.add_argument('--location',     type=str, help='"lat,lon"')
    p.add_argument('--start-year',   type=int)
    p.add_argument('--end-year',     type=int)
    p.add_argument('--fixed-season', type=str, default=None,
                   metavar='MM-DD:MM-DD[,MM-DD:MM-DD]',
                   help="omit for auto-detect; otherwise single, two, or year-crossing windows")
    p.add_argument('--models',       type=str, default=None,
                   help='comma-separated GCMs (default: location-aware ensemble)')
    p.add_argument('--scenarios',    type=str, default=','.join(SCENARIOS),
                   help=f"comma-separated scenarios (default: {','.join(SCENARIOS)})")
    p.add_argument('--soilcp',  type=float, default=DEFAULT_SOILCP,
                   help=f'Soil available water capacity at field capacity, mm '
                        f'(water-balance NDWS/NDWL0; default: {DEFAULT_SOILCP})')
    p.add_argument('--soilsat', type=float, default=DEFAULT_SOILSAT,
                   help=f'Extra soil water from field capacity to saturation, mm '
                        f'(water-balance NDWL0; default: {DEFAULT_SOILSAT})')
    p.add_argument('--water-balance-window', type=str,
                   choices=list(WATER_BALANCE_WINDOW_CHOICES),
                   default=FULL_WINDOW_WATER_BALANCE,
                   help='NDWS/NDWL0 count window for fixed seasons: full_window or crop_active')
    p.add_argument('--thresholds-file', type=str, default=None,
                   help=('Optional JSON file overriding threshold bands by metric name. '
                         'Metrics omitted from file keep package defaults.'))
    p.add_argument('--format',       choices=['json', 'text'], default='text')
    p.add_argument('--output',       type=str, default=None,
                   help='write full result as JSON to this path')
    args = p.parse_args()

    if args.list_models:
        print("Models:");    [print(f"  {m}") for m in MODELS]
        print("\nScenarios:"); [print(f"  {s}") for s in SCENARIOS]
        return 0

    missing = [n for n, v in (('--location',  args.location),
                              ('--start-year', args.start_year),
                              ('--end-year',   args.end_year)) if v in (None, '')]
    if missing:
        p.error(f"missing required arguments: {', '.join(missing)}")

    lat, lon  = map(float, args.location.split(','))
    sub_models = [s.strip() for s in args.models.split(',') if s.strip()] if args.models else None
    models    = default_ensemble_models_for_location((lat, lon), models=sub_models)
    scenarios = [s.strip() for s in args.scenarios.split(',') if s.strip()]
    custom_thresholds = load_custom_thresholds_file(args.thresholds_file)

    result = calculate_ensemble(
        crop=args.crop,
        lat=lat, lon=lon,
        start_year=args.start_year, end_year=args.end_year,
        models=models, scenarios=scenarios,
        fixed_season=args.fixed_season,
        custom_thresholds=custom_thresholds,
        soilcp=args.soilcp, soilsat=args.soilsat,
        water_balance_window=args.water_balance_window,
    )

    if args.format == 'json':
        print(json.dumps(result, indent=2, default=str))
    else:
        print_results(result)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)) or '.', exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Saved to: {args.output}")
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
        
# NOTE: the 1st command in a section includes all models/scenarios while the 2nd allows selection  
   
# Fixed single season:
# python -m climate_tookit.calculate_hazards.ensemble_hazards millet --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "03-01:05-31" --scenarios ssp245,ssp585 --output ensemble_mam_all.json
# python -m climate_tookit.calculate_hazards.ensemble_hazards maize --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "03-01:05-31" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp585 --output ensemble_mam.json

# Fixed two seasons:
# python -m climate_tookit.calculate_hazards.ensemble_hazards rice --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "03-01:05-31,10-01:12-15" --scenarios ssp245,ssp585 --output ensemble_mam_ond_all.json
# python -m climate_tookit.calculate_hazards.ensemble_hazards beans --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "03-01:05-31,10-01:12-15" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp245,ssp585 --output ensemble_mam_ond.json

# Fixed year-crossing season:
# python -m climate_tookit.calculate_hazards.ensemble_hazards sorghum --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "11-01:02-28" --scenarios ssp245,ssp585 --output ensemble_njf_all.json
# python -m climate_tookit.calculate_hazards.ensemble_hazards cassava --location="-1.286,36.817" --start-year 2040 --end-year 2060 --fixed-season "11-01:02-28" --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp585 --output ensemble_njf.json

# List available NEX-GDDP models and scenarios:
# python -m climate_tookit.calculate_hazards.ensemble_hazards --list-models

# Auto-detect season (NEX-GDDP per (model, scenario), no flag) -- all models, pick scenarios:
# python -m climate_tookit.calculate_hazards.ensemble_hazards maize --location="-1.286,36.817" --start-year 2040 --end-year 2060 --scenarios ssp245,ssp585 --output ensemble_auto_all.json

# Auto-detect season -- custom subset:
# python -m climate_tookit.calculate_hazards.ensemble_hazards maize --location="-1.286,36.817" --start-year 2040 --end-year 2060 --models "ACCESS-CM2,EC-Earth3,MRI-ESM2-0" --scenarios ssp245,ssp585 --output ensemble_auto.json
