"""
Calculate Hazards Module
Retrieves crop hazard indices at a specific location by:
1. Using season_analysis to detect growing seasons or accepting season dates
2. Calculating total precipitation and average temperature for the season
3. Evaluating crop-specific hazard thresholds
4. Analyzing dry spell patterns
5. Deriving soil-water diagnostics from an Atlas-inspired running soil water balance
   (ERATIO < 0.5 for NDWS; LOGGING > 0 for NDWL0; seasonal WRSI from AET:CWR)

Dependencies: pandas, season_analysis.seasons module
"""

import sys
import os
import logging
import shutil
import textwrap
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import json
import argparse
from climate_tookit._resources import load_json_resource
from climate_tookit.climatology import (
    DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    DEFAULT_LIVESTOCK_TYPE,
    build_thi_hazard_thresholds,
    compute_daily_thi,
    describe_thi_method,
    list_thi_livestock_profiles,
    resolve_thi_profile,
)
from climate_tookit.crop_calendar.registry import (
    normalize_crop_name,
    threshold_supported_crop_names,
)
from climate_tookit.crop_calendar.ggcmi import (
    CALENDAR_SYSTEM_CHOICES,
    resolve_calendar_preset,
)
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    normalize_climate_dataset_name,
    source_date_coverage_error,
)
from climate_tookit.season_analysis.season_identity import build_season_identity

TERMINAL_TABLE_HEADER_ALIASES = {
    "Metric": "metric",
    "baseline_ltm": "base",
}

CROP_WATER_BALANCE_PARAMS_PACKAGE = "climate_tookit.calculate_hazards"
CROP_WATER_BALANCE_PARAMS_RESOURCE = "crop_water_balance_params.json"

DEFAULT_SPINUP_DAYS = 60
DEFAULT_DEPLETION_FRACTION_P = 0.5
DEFAULT_KC_PARAMS = {
    "kc_init": 0.7,
    "kc_mid": 1.0,
    "kc_end": 0.8,
    "root_depth_m": 1.0,
    "depletion_fraction_p": DEFAULT_DEPLETION_FRACTION_P,
    "source_doc": "generic fallback",
}

from climate_tookit.season_analysis.seasons import (
    PAIRED_SOURCE_SENTINEL,
    PRECIP_ONLY_SOURCES,
    TEMP_ONLY_SOURCES,
    get_climate_data,
    add_et0,
    detect_onset_cessation,
    fetch_and_analyze_years,
    fetch_and_analyze_years_fixed,
    fetch_master_range_with_tail,
    analyze_years_auto_on_prefetched_df,
    analyze_years_fixed_on_prefetched_df,
    parse_fixed_seasons,
)

# Crop thresholds
CROP_THRESHOLDS = {
    'Beans':      {
        'Total Precip': {'no_stress': (500, 2000),  'moderate_stress_low': (300, 500),   'moderate_stress_up': (2000, 4300), 'severe_stress_low': (None, 300),   'severe_stress_up': (4300, None)},
        'TAVG':         {'no_stress': (18, 30),     'moderate_stress_low': (7, 18),      'moderate_stress_up': (30, 32),    'severe_stress_low': (None, 7),     'severe_stress_up': (32, None)},
    },
    'Maize':      {
        'Total Precip': {'no_stress': (500, 1200),  'moderate_stress_low': (400, 500),   'moderate_stress_up': (1200, 1800),'severe_stress_low': (None, 400),   'severe_stress_up': (1800, None)},
        'TAVG':         {'no_stress': (18, 32),     'moderate_stress_low': (14, 18),     'moderate_stress_up': (32, 40),    'severe_stress_low': (None, 14),    'severe_stress_up': (40, None)},
    },
    'Millet':     {
        'Total Precip': {'no_stress': (300, 600),   'moderate_stress_low': (200, 300),   'moderate_stress_up': (600, 1700), 'severe_stress_low': (None, 200),   'severe_stress_up': (1700, None)},
        'TAVG':         {'no_stress': (16, 32),     'moderate_stress_low': (12, 16),     'moderate_stress_up': (32, 40),    'severe_stress_low': (None, 12),    'severe_stress_up': (40, None)},
    },
    'Groundnuts': {
        'Total Precip': {'no_stress': (400, 1100),  'moderate_stress_low': (200, 400),   'moderate_stress_up': (1100, 1900),'severe_stress_low': (None, 200),   'severe_stress_up': (1900, None)},
        'TAVG':         {'no_stress': (22, 28),     'moderate_stress_low': (18, 22),     'moderate_stress_up': (28, 30),    'severe_stress_low': (None, 18),    'severe_stress_up': (30, None)},
    },
    'Sorghum':    {
        'Total Precip': {'no_stress': (400, 900),   'moderate_stress_low': (150, 400),   'moderate_stress_up': (900, 1400), 'severe_stress_low': (None, 150),   'severe_stress_up': (1400, None)},
        'TAVG':         {'no_stress': (21, 32),     'moderate_stress_low': (8, 21),      'moderate_stress_up': (32, 40),    'severe_stress_low': (None, 8),     'severe_stress_up': (40, None)},
    },
    'Cassava':    {
        'Total Precip': {'no_stress': (1400, 1800), 'moderate_stress_low': (500, 1400),  'moderate_stress_up': (1800, 5000),'severe_stress_low': (None, 500),   'severe_stress_up': (5000, None)},
        'TAVG':         {'no_stress': (20, 29),     'moderate_stress_low': (10, 20),     'moderate_stress_up': (29, 35),    'severe_stress_low': (None, 10),    'severe_stress_up': (35, None)},
    },
    'Rice':       {
        'Total Precip': {'no_stress': (1500, 2000), 'moderate_stress_low': (1000, 1500), 'moderate_stress_up': (2000, 4000),'severe_stress_low': (None, 1000),  'severe_stress_up': (4000, None)},
        'TAVG':         {'no_stress': (20, 30),     'moderate_stress_low': (10, 20),     'moderate_stress_up': (30, 36),    'severe_stress_low': (None, 10),    'severe_stress_up': (36, None)},
    },
}

# Starter crop water-balance defaults.
# Source basis:
# - FAO-56 Crop evapotranspiration guidance for Kc / rooting-depth methodology
# - conservative agronomic defaults for these crop classes pending crop-by-crop
#   line-level FAO/AquaCrop validation in package docs
# Atlas-inspired starter hazard-index thresholds.
ATLAS_HAZARD_INDEX_THRESHOLDS = {
    'THI': build_thi_hazard_thresholds(
        livestock_type=DEFAULT_LIVESTOCK_TYPE,
        climate_profile='temperate',
    ),
    'NDD': {
        'no_stress': (None, 15),
        'moderate_stress': (15, 20),
        'severe_stress': (20, 25),
        'extreme_stress': (25, None),
    },
    'NTx35': {
        'no_stress': (None, 10),
        'moderate_stress': (10, 20),
        'severe_stress': (20, 25),
        'extreme_stress': (25, None),
    },
    'NTx40': {
        'no_stress': (None, 1),
        'moderate_stress': (1, 5),
        'severe_stress': (5, 10),
        'extreme_stress': (10, None),
    },
    'NDWS': {
        'no_stress': (None, 15),
        'moderate_stress': (15, 20),
        'severe_stress': (20, 25),
        'extreme_stress': (25, None),
    },
    'NDWL0': {
        'no_stress': (None, 2),
        'moderate_stress': (2, 5),
        'severe_stress': (5, 8),
        'extreme_stress': (8, None),
    },
}

HAZARD_EVAL_SPECS = {
    'Total Precip': {
        'result_key': 'precipitation',
        'stat_key': 'total_precipitation_mm',
        'value_key': 'value_mm',
        'label': 'Precipitation',
        'unit': 'mm',
    },
    'TAVG': {
        'result_key': 'temperature',
        'stat_key': 'mean_temperature_c',
        'value_key': 'value_c',
        'label': 'Temperature',
        'unit': 'degC',
    },
    'THI': {
        'result_key': 'THI',
        'stat_key': 'mean_thi',
        'value_key': 'value_thi',
        'label': 'THI',
        'unit': 'index',
    },
    'NDD': {
        'result_key': 'NDD',
        'stat_key': 'NDD',
        'value_key': 'value_days',
        'label': 'NDD',
        'unit': 'days',
    },
    'NTx35': {
        'result_key': 'NTx35',
        'stat_key': 'NTx35',
        'value_key': 'value_days',
        'label': 'NTx35',
        'unit': 'days',
    },
    'NTx40': {
        'result_key': 'NTx40',
        'stat_key': 'NTx40',
        'value_key': 'value_days',
        'label': 'NTx40',
        'unit': 'days',
    },
    'NDWS': {
        'result_key': 'NDWS',
        'stat_key': 'NDWS',
        'value_key': 'value_days',
        'label': 'NDWS',
        'unit': 'days',
    },
    'NDWL0': {
        'result_key': 'NDWL0',
        'stat_key': 'NDWL0',
        'value_key': 'value_days',
        'label': 'NDWL0',
        'unit': 'days',
    },
}

HAZARD_PRINT_ORDER = ['precipitation', 'temperature', 'THI', 'NDD', 'NTx35', 'NTx40', 'NDWS', 'NDWL0']

FULL_WINDOW_WATER_BALANCE = "full_window"
CROP_ACTIVE_WATER_BALANCE = "crop_active"
WATER_BALANCE_WINDOW_CHOICES = (
    FULL_WINDOW_WATER_BALANCE,
    CROP_ACTIVE_WATER_BALANCE,
)

COMPARISON_METRIC_SPECS = [
    ('total_precipitation_mm', 'total_mm', 'Total Precipitation', 'mm'),
    ('mean_temperature_c', 'mean_tavg', 'TAVG', 'deg C'),
    ('min_tmin_c', 'min_tmin', 'Min Tmin', 'deg C'),
    ('max_tmax_c', 'max_tmax', 'Max Tmax', 'deg C'),
    ('mean_thi', 'mean_thi', 'Mean THI', 'index'),
    ('max_thi', 'max_thi', 'Max THI', 'index'),
    ('thi_stress_days', 'thi_stress_days', 'THI Stress Days', 'days'),
    ('crop_water_requirement_mm', 'crop_water_requirement_mm', 'Crop Water Requirement', 'mm'),
    ('actual_crop_et_mm', 'actual_crop_et_mm', 'Actual Crop ET', 'mm'),
    ('WRSI', 'wrsi', 'WRSI', '%'),
    ('NTx35', 'NTx35', 'NTx35', 'days'),
    ('NTx40', 'NTx40', 'NTx40', 'days'),
    ('NDD', 'NDD', 'NDD', 'days'),
    ('NDWS', 'NDWS', 'NDWS', 'days'),
    ('NDWL0', 'NDWL0', 'NDWL0', 'days'),
    ('number_of_dry_spells', 'dry_spell_count', 'Dry Spells', 'spells'),
    ('max_dry_spell_length_days', 'dry_spell_max', 'Max Dry Spell Length', 'days'),
    ('mean_dry_spell_length_days', 'dry_spell_mean', 'Mean Dry Spell Length', 'days'),
]

def _merge_threshold_groups(base: Dict[str, Dict[str, Tuple]], override: Dict[str, Dict[str, Tuple]]) -> Dict[str, Dict[str, Tuple]]:
    merged = deepcopy(base)
    for metric, bands in (override or {}).items():
        merged[metric] = deepcopy(bands)
    return merged

def _thi_profile_label(profile: Optional[Dict[str, Any]]) -> str:
    if not profile:
        return "THI"
    label = (
        profile.get("label")
        or profile.get("thi_livestock_label")
        or profile.get("livestock_label")
        or profile.get("thi_livestock_type")
        or profile.get("livestock_type")
        or "THI"
    )
    climate = profile.get("climate_profile_applied") or profile.get("thi_climate_profile")
    if climate:
        return f"THI ({label}; {climate})"
    return f"THI ({label})"


def _thi_profile_context_line(profile: Optional[Dict[str, Any]]) -> Optional[str]:
    if not profile:
        return None
    livestock_type = (
        profile.get("livestock_type")
        or profile.get("thi_livestock_type")
    )
    applied = profile.get("climate_profile_applied") or profile.get("thi_climate_profile")
    requested = profile.get("climate_profile_requested")
    parts = []
    if livestock_type:
        parts.append(f"type={livestock_type}")
    if applied:
        parts.append(f"climate={applied}")
    if requested and requested != applied:
        parts.append(f"requested={requested}")
    elevation_m = profile.get("elevation_m")
    elevation_source = profile.get("elevation_source")
    if elevation_m is not None:
        if elevation_source:
            parts.append(f"elevation={float(elevation_m):.0f} m ({elevation_source})")
        else:
            parts.append(f"elevation={float(elevation_m):.0f} m")
    if not parts:
        return None
    return " | ".join(parts)


def _thi_method_line(profile: Optional[Dict[str, Any]] = None) -> str:
    threshold_source = describe_thi_method().get("threshold_reference")
    note = "operational defaults | mean-temp+RH THI"
    if threshold_source:
        return f"{note} | thresholds={threshold_source}"
    return note


def resolve_thresholds(
    crop_name: str,
    custom_thresholds: Optional[Dict[str, Dict[str, Tuple]]] = None,
    *,
    livestock_type: str = DEFAULT_LIVESTOCK_TYPE,
    livestock_climate_profile: str = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    livestock_elevation_override_m: Optional[float] = None,
) -> Dict[str, Dict[str, Tuple]]:
    thresholds = _merge_threshold_groups(CROP_THRESHOLDS.get(crop_name, {}), ATLAS_HAZARD_INDEX_THRESHOLDS)
    thresholds["THI"] = build_thi_hazard_thresholds(
        livestock_type=livestock_type,
        climate_profile=livestock_climate_profile,
        lat=lat,
        lon=lon,
        elevation_m=livestock_elevation_override_m,
        auto_fetch_elevation=True,
    )
    if custom_thresholds:
        thresholds = _merge_threshold_groups(thresholds, custom_thresholds)
    return thresholds

def load_custom_thresholds_file(path: Optional[str]) -> Optional[Dict[str, Dict[str, Tuple]]]:
    if not path:
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Threshold override file must contain a JSON object keyed by metric name.")
    return data


@lru_cache(maxsize=4)
def load_crop_water_balance_params(path: str | Path | None = None) -> Dict[str, Dict[str, Any]]:
    if path is None:
        data = load_json_resource(
            CROP_WATER_BALANCE_PARAMS_PACKAGE,
            CROP_WATER_BALANCE_PARAMS_RESOURCE,
        )
    else:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Crop water-balance params file must contain a JSON object keyed by crop name.")
    return data


def resolve_crop_water_balance_params(
    crop_name: str,
    params_path: str | Path | None = None,
) -> Dict[str, Any]:
    params = load_crop_water_balance_params(params_path).get(crop_name)
    if not params:
        fallback = deepcopy(DEFAULT_KC_PARAMS)
        fallback["warning"] = (
            f"No crop water-balance params found for {crop_name}; using generic defaults."
        )
        return fallback
    return deepcopy(params)

def _percent_change(diff: float, baseline: float) -> float:
    return (diff / abs(baseline) * 100.0) if baseline != 0 else 0.0


def _season_counts_by_year(seasons: List[Dict[str, Any]]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for season in seasons or []:
        year = season.get("year")
        if isinstance(year, int):
            counts[year] = counts.get(year, 0) + 1
    return counts


def _normalize_water_balance_window_mode(mode: Optional[str]) -> str:
    normalized = (mode or FULL_WINDOW_WATER_BALANCE).strip().lower()
    if normalized not in WATER_BALANCE_WINDOW_CHOICES:
        raise ValueError(
            "water_balance_window must be one of "
            f"{', '.join(WATER_BALANCE_WINDOW_CHOICES)}"
        )
    return normalized


def _inclusive_day_count(start_date: Optional[str], end_date: Optional[str]) -> Optional[int]:
    if not start_date or not end_date:
        return None
    return (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1


def _valid_eto_subseasons(eto_seasons: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    valid: List[Dict[str, Any]] = []
    for season in eto_seasons or []:
        onset = season.get("onset")
        cessation = season.get("cessation")
        if onset is None or cessation is None:
            continue
        valid.append(season)
    return valid


def _apply_water_balance_window_mode(
    base_stats: Dict[str, Any],
    df: pd.DataFrame,
    season_info: Dict[str, Any],
    soil_parameters: Dict[str, Any],
    crop_water_balance: Dict[str, Any],
    thi_profile: Optional[Dict[str, Any]] = None,
    water_balance_window: str = FULL_WINDOW_WATER_BALANCE,
    eto_seasons: Optional[List[Dict[str, Any]]] = None,
    eto_detection_note: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    requested_mode = _normalize_water_balance_window_mode(water_balance_window)
    full_window_days = _inclusive_day_count(
        season_info.get("onset_date"),
        season_info.get("cessation_date"),
    )
    metadata = {
        "requested_window_mode": requested_mode,
        "applied_window_mode": FULL_WINDOW_WATER_BALANCE,
        "counted_days": full_window_days,
        "counted_subseasons": 0,
        "fallback_reason": None,
        "warnings": [],
    }
    if "NDWS" not in base_stats and "NDWL0" not in base_stats:
        metadata["applied_window_mode"] = "unavailable"
        metadata["counted_days"] = None
        metadata["warnings"].append(
            "NDWS/NDWL0 unavailable because precipitation or ET0 inputs were missing."
        )
        return base_stats, metadata
    if season_info.get("method") != "fixed_season" or requested_mode == FULL_WINDOW_WATER_BALANCE:
        return base_stats, metadata

    valid_subseasons = _valid_eto_subseasons(eto_seasons)
    if not valid_subseasons:
        metadata["fallback_reason"] = (
            eto_detection_note or "No closed ETO sub-season detected within fixed window."
        )
        metadata["warnings"].append(
            "Requested crop-active NDWS window, but "
            f"{metadata['fallback_reason']} "
            "Falling back to full fixed window."
        )
        return base_stats, metadata

    ndws_total = 0
    ndwl0_total = 0
    counted_days = 0
    for sub_season in valid_subseasons:
        sub_stats = calculate_season_statistics(
            df,
            soilcp=soil_parameters["soilcp"],
            soilsat=soil_parameters["soilsat"],
            kc=float(crop_water_balance.get("kc_mid", 1.0)),
            kc_init=float(crop_water_balance.get("kc_init", crop_water_balance.get("kc_mid", 1.0))),
            kc_mid=float(crop_water_balance.get("kc_mid", 1.0)),
            kc_end=float(crop_water_balance.get("kc_end", crop_water_balance.get("kc_mid", 1.0))),
            depletion_fraction_p=float(
                crop_water_balance.get("depletion_fraction_p", DEFAULT_DEPLETION_FRACTION_P)
            ),
            analysis_start=pd.to_datetime(sub_season["onset"]).strftime("%Y-%m-%d"),
            analysis_end=pd.to_datetime(sub_season["cessation"]).strftime("%Y-%m-%d"),
            thi_profile=thi_profile,
        )
        ndws_total += int(sub_stats.get("NDWS", 0))
        ndwl0_total += int(sub_stats.get("NDWL0", 0))
        counted_days += int(
            _inclusive_day_count(
                pd.to_datetime(sub_season["onset"]).strftime("%Y-%m-%d"),
                pd.to_datetime(sub_season["cessation"]).strftime("%Y-%m-%d"),
            )
            or 0
        )

    adjusted = dict(base_stats)
    adjusted["NDWS"] = ndws_total
    adjusted["NDWL0"] = ndwl0_total
    metadata["applied_window_mode"] = CROP_ACTIVE_WATER_BALANCE
    metadata["counted_days"] = counted_days
    metadata["counted_subseasons"] = len(valid_subseasons)
    return adjusted, metadata


def build_water_balance_methodology(
    season_info: Dict[str, Any],
    soil_parameters: Dict[str, Any],
    crop_water_balance: Dict[str, Any],
    count_window: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    count_window = count_window or {
        "requested_window_mode": FULL_WINDOW_WATER_BALANCE,
        "applied_window_mode": FULL_WINDOW_WATER_BALANCE,
        "counted_days": _inclusive_day_count(
            season_info.get("onset_date"),
            season_info.get("cessation_date"),
        ),
        "counted_subseasons": 0,
        "fallback_reason": None,
        "warnings": [],
    }
    notes = [
        "NDWS counts days where ERATIO < 0.5 after running the crop root-zone water balance.",
        "NDWL0 counts days where LOGGING > 0 after the same balance.",
        "WRSI is calculated as seasonal actual crop ET divided by seasonal crop water requirement, expressed as a percentage.",
        "These are crop-water-balance diagnostics, not a simple daily precipitation minus ET0 threshold.",
        "ET0 is derived with the season_analysis Hargreaves implementation when not already present.",
        "Hazard day-count bands are Atlas-inspired starter thresholds, not peer-reviewed validation targets.",
    ]
    if season_info.get("method") == "fixed_season":
        if count_window.get("applied_window_mode") == CROP_ACTIVE_WATER_BALANCE:
            notes.append(
                "Fixed-season mode counted NDWS and NDWL0 only within detected ETO sub-seasons inside the user-defined window."
            )
        else:
            notes.append(
                "Fixed-season mode counts NDWS and NDWL0 only inside the user-defined window. "
                "Broad or misaligned windows can inflate counts by including shoulder months."
            )

    warnings_list = [
        crop_water_balance.get("warning"),
        soil_parameters.get("warning"),
        soil_parameters.get("root_depth_warning"),
        count_window.get("fallback_reason"),
        *(count_window.get("warnings") or []),
    ]
    return {
        "ndws_definition": "Days with ERATIO < 0.5",
        "ndwl0_definition": "Days with LOGGING > 0",
        "wrsi_definition": "100 * seasonal actual crop ET / seasonal crop water requirement",
        "et0_method": "Hargreaves reference ET0",
        "analysis_method": season_info.get("method", "unknown"),
        "analysis_window": {
            "onset_date": season_info.get("onset_date"),
            "cessation_date": season_info.get("cessation_date"),
            "spinup_days": season_info.get("spinup_days"),
        },
        "soil_parameters": {
            "soilcp_mm": soil_parameters.get("soilcp"),
            "soilsat_mm": soil_parameters.get("soilsat"),
            "root_depth_m": soil_parameters.get("root_depth_m"),
        },
        "count_window": {
            "requested_mode": count_window.get("requested_window_mode"),
            "applied_mode": count_window.get("applied_window_mode"),
            "counted_days": count_window.get("counted_days"),
            "counted_subseasons": count_window.get("counted_subseasons"),
        },
        "crop_parameters": {
            "kc_init": crop_water_balance.get("kc_init"),
            "kc_mid": crop_water_balance.get("kc_mid"),
            "kc_end": crop_water_balance.get("kc_end"),
            "depletion_fraction_p": crop_water_balance.get("depletion_fraction_p"),
            "source_doc": crop_water_balance.get("source_doc"),
        },
        "threshold_source": "Atlas-inspired provisional day-count bands",
        "notes": notes,
        "warnings": [item for item in warnings_list if item],
    }


def _auto_ltm_guard_message(assessments: List[Dict[str, Any]]) -> Optional[str]:
    counts: Dict[int, int] = {}
    for assessment in assessments:
        info = assessment.get("season_info") or {}
        if info.get("method") != "rainfall_based":
            continue
        year = info.get("year")
        if isinstance(year, int):
            counts[year] = counts.get(year, 0) + 1
    observed_counts = set(counts.values())
    if len(observed_counts) <= 1:
        return None
    summary = ", ".join(f"{year}:{count}" for year, count in sorted(counts.items())) or "none"
    return (
        "Auto-detected season counts differ across years, so baseline_ltm by season_number "
        "would blend incomparable seasons. "
        f"Counts by year: {summary}. "
        "Use --fixed-season for a stable multi-year hazards baseline."
    )


def _hazard_season_detection_summary(
    *,
    status: str,
    reasons: List[str],
    guidance: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    guidance = guidance or []
    details = details or {}
    return {
        "status": status,
        "reasons": list(dict.fromkeys(reasons)),
        "human_review_recommended": status in {"warn", "prompt_required"},
        "calendar_override_recommended": status == "prompt_required",
        "guidance": list(dict.fromkeys(guidance)),
        "details": details,
    }


def _build_hazard_season_detection_from_assessments(
    assessments: List[Dict[str, Any]],
    *,
    warning: Optional[str] = None,
) -> Dict[str, Any]:
    methods = {
        (assessment.get("season_info") or {}).get("method")
        for assessment in assessments or []
        if (assessment.get("season_info") or {}).get("method")
    }
    counts_by_year: Dict[str, int] = {}
    for assessment in assessments or []:
        info = assessment.get("season_info") or {}
        year = info.get("year")
        if isinstance(year, int):
            key = str(year)
            counts_by_year[key] = counts_by_year.get(key, 0) + 1
    calendar_preset = next(
        (
            (assessment.get("season_info") or {}).get("calendar_preset")
            for assessment in assessments or []
            if (assessment.get("season_info") or {}).get("calendar_preset_fallback")
        ),
        None,
    )

    if warning:
        return _hazard_season_detection_summary(
            status="prompt_required",
            reasons=["unstable_season_counts"],
            guidance=[
                "Auto season detection is not stable enough for a comparable hazards baseline. Use --fixed-season."
            ],
            details={
                "methods": sorted(method for method in methods if method),
                "counts_by_year": counts_by_year,
                "warning": warning,
            },
        )

    if calendar_preset:
        return _hazard_season_detection_summary(
            status="ok",
            reasons=["calendar_preset_fallback_applied", "fixed_season_override"],
            guidance=[],
            details={
                "methods": sorted(method for method in methods if method),
                "counts_by_year": counts_by_year,
                "calendar_preset": calendar_preset,
            },
        )
    if "fixed_season" in methods:
        return _hazard_season_detection_summary(
            status="ok",
            reasons=["fixed_season_override"],
            guidance=[],
            details={"methods": sorted(method for method in methods if method)},
        )
    if "user_provided" in methods:
        return _hazard_season_detection_summary(
            status="ok",
            reasons=["user_provided_dates"],
            guidance=[],
            details={"methods": sorted(method for method in methods if method)},
        )
    return _hazard_season_detection_summary(
        status="ok",
        reasons=[],
        guidance=[],
        details={
            "methods": sorted(method for method in methods if method),
            "counts_by_year": counts_by_year,
        },
    )


def _build_hazard_season_detection_error(
    *,
    reason: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    guidance_map = {
        "season_detection_failed": [
            "Review source data and detection prerequisites, then retry. If seasonal interpretation is still needed, use --fixed-season or retry with --calendar-source ggcmi."
        ],
        "no_seasons_detected_all_years": [
            "Auto season detection did not find usable seasons. Provide --season-start/--season-end, use --fixed-season, or retry with --calendar-source ggcmi."
        ],
    }
    return _hazard_season_detection_summary(
        status="prompt_required",
        reasons=[reason],
        guidance=guidance_map.get(reason, []),
        details={"message": message, **(details or {})},
    )


def _print_hazard_season_detection_summary(summary: Optional[Dict[str, Any]]) -> None:
    if not summary:
        return
    status = summary.get("status")
    reasons = summary.get("reasons") or []
    guidance = summary.get("guidance") or []
    if not status or (status == "ok" and not reasons and not guidance):
        return
    print(f"  Season detect : {status}")
    if reasons:
        print(f"    reasons: {', '.join(reasons)}")
    preset = (summary.get("details") or {}).get("calendar_preset")
    if preset:
        print(
            "    calendar: "
            f"{preset.get('calendar_source')} | "
            f"crop={preset.get('crop_name')} | "
            f"system={preset.get('calendar_system')} | "
            f"fixed={preset.get('fixed_season')}"
        )
    if guidance:
        print("    guidance:")
        for item in guidance:
            _print_wrapped("- ", str(item), indent="      ")


def _terminal_width(default: int = 120) -> int:
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except OSError:
        return default


def _short_cell(value: Any, max_len: int = 16) -> Any:
    if value is None or pd.isna(value):
        return "n/a"
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _compact_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy().fillna("n/a").rename(columns=TERMINAL_TABLE_HEADER_ALIASES)
    rendered = display.to_string(index=False)
    if max((len(line) for line in rendered.splitlines()), default=0) <= _terminal_width():
        return display
    for column in display.columns:
        if display[column].dtype == object:
            display[column] = display[column].map(_short_cell)
    return display


def _print_wrapped(prefix: str, text: str, *, indent: str = "") -> None:
    print(
        textwrap.fill(
            text,
            width=max(72, _terminal_width() - len(prefix) - len(indent)),
            initial_indent=indent + prefix,
            subsequent_indent=indent + (" " * len(prefix)),
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def _resolve_calendar_preset_request(
    *,
    lat: float,
    lon: float,
    crop_name: Optional[str],
    calendar_source: Optional[str],
    calendar_system: str,
) -> Optional[Dict[str, Any]]:
    if not crop_name or not calendar_source:
        return None
    source = str(calendar_source).lower()
    if source != "ggcmi":
        raise ValueError(
            f"Unsupported calendar source: {calendar_source}. Available: ggcmi"
        )
    return resolve_calendar_preset(lat, lon, crop_name, system=calendar_system)


def _validate_source_window(source: str, end_year: int) -> None:
    source_lc = (source or 'auto').lower()
    if source_lc in {'chirps_v3_daily_rnl', 'imerg', 'tamsat'}:
        raise ValueError(
            f"{source_lc} is precipitation-only and is not yet supported directly by "
            "calculate_hazards. Use --source auto for the default "
            "chirps_v3_daily_rnl + agera_5 path, or use agera_5 / era_5 directly for now."
        )
    if source_lc in {'chirps+chirts', 'chirps_v2+chirts'} and end_year > 2016:
        raise ValueError(
            "chirps_v2+chirts is unavailable for this window because CHIRTS daily "
            "temperature currently ends in 2016. Use agera_5, era_5, or "
            "--source auto (default CHIRPS v3 Daily RNL + AgERA5) for newer periods."
        )


def _validate_paired_sources(
    precip_source: Optional[str],
    temp_source: Optional[str],
    end_year: int,
) -> None:
    precip_lc = normalize_climate_dataset_name(precip_source)
    temp_lc = normalize_climate_dataset_name(temp_source)
    if bool(precip_lc) != bool(temp_lc):
        raise ValueError("Provide both --precip-source and --temp-source together with --source paired.")
    if not precip_lc and not temp_lc:
        raise ValueError("source='paired' requires both --precip-source and --temp-source.")
    if precip_lc in TEMP_ONLY_SOURCES:
        raise ValueError(f"precip_source '{precip_source}' is temperature-only.")
    if temp_lc in PRECIP_ONLY_SOURCES:
        raise ValueError(f"temp_source '{temp_source}' is precipitation-only.")
    if temp_lc == 'chirts' and end_year > 2016:
        raise ValueError(
            "Temperature partner chirts is unavailable for this window because "
            "CHIRTS daily coverage ends in 2016."
        )


def _validate_source_coverage(source: str, start_date: str, end_date: str) -> None:
    coverage_error = source_date_coverage_error(
        source,
        date.fromisoformat(start_date),
        date.fromisoformat(end_date),
    )
    if coverage_error:
        raise ValueError(coverage_error)


def _validate_paired_coverage(
    precip_source: Optional[str],
    temp_source: Optional[str],
    start_date: str,
    end_date: str,
) -> None:
    precip_lc = normalize_climate_dataset_name(precip_source)
    temp_lc = normalize_climate_dataset_name(temp_source)
    if precip_lc:
        _validate_source_coverage(precip_lc, start_date, end_date)
    if temp_lc:
        _validate_source_coverage(temp_lc, start_date, end_date)


def _validate_request_coverage(
    source: str,
    start_date: str,
    end_date: str,
    precip_source: Optional[str] = None,
    temp_source: Optional[str] = None,
) -> None:
    source_lc = normalize_climate_dataset_name(source) or source
    if source_lc == PAIRED_SOURCE_SENTINEL:
        _validate_paired_coverage(precip_source, temp_source, start_date, end_date)
        return
    if source_lc in {"auto", "chirps+chirts", "chirps_v2+chirts"}:
        return
    _validate_source_coverage(source_lc, start_date, end_date)


def _fixed_window_dates_for_year(
    year: int,
    season_def: Dict[str, Any],
) -> Tuple[str, str]:
    onset_mm, onset_dd = season_def["onset_md"]
    cess_mm, cess_dd = season_def["cessation_md"]
    cessation_year = year + 1 if (cess_mm, cess_dd) < (onset_mm, onset_dd) else year
    onset_date = date(year, onset_mm, onset_dd).isoformat()
    cessation_date = date(cessation_year, cess_mm, cess_dd).isoformat()
    return onset_date, cessation_date


def _extract_detection_errors(annual_dict: Dict[int, Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for annual_info in (annual_dict or {}).values():
        if not isinstance(annual_info, dict):
            continue
        message = annual_info.get('error')
        if message and message not in errors:
            errors.append(message)
    return errors


def _shift_iso_date(date_str: str, days: int) -> str:
    return (datetime.fromisoformat(date_str) + timedelta(days=days)).strftime("%Y-%m-%d")


def _attach_season_identity(season_info: Dict[str, Any]) -> Dict[str, Any]:
    season_info = dict(season_info)
    onset = season_info.get("onset_date")
    cessation = season_info.get("cessation_date")
    if onset and cessation:
        season_info["season_identity"] = build_season_identity(
            onset,
            cessation,
            length_days=season_info.get("length_days"),
            regime=season_info.get("regime"),
            season_number=season_info.get("season_number"),
            total_seasons_per_year=season_info.get("total_seasons_per_year"),
        )
    return season_info


def _prefetched_window_covers(
    df: Optional[pd.DataFrame],
    required_start: str,
    required_end: str,
) -> bool:
    if df is None or df.empty or "date" not in df.columns:
        return False
    dates = pd.to_datetime(df["date"])
    return dates.min() <= pd.Timestamp(required_start) and dates.max() >= pd.Timestamp(required_end)


def _slice_prefetched_window(
    df: Optional[pd.DataFrame],
    required_start: str,
    required_end: str,
) -> Optional[pd.DataFrame]:
    if not _prefetched_window_covers(df, required_start, required_end):
        return None
    sliced = df.copy()
    sliced["date"] = pd.to_datetime(sliced["date"])
    return (
        sliced[
            (sliced["date"] >= pd.Timestamp(required_start)) &
            (sliced["date"] <= pd.Timestamp(required_end))
        ]
        .copy()
        .reset_index(drop=True)
    )


def _allocate_stage_lengths(total_days: int) -> Tuple[int, int, int, int]:
    if total_days <= 0:
        return (0, 0, 0, 0)
    weights = (0.2, 0.3, 0.3, 0.2)
    raw = [total_days * weight for weight in weights]
    counts = [int(value) for value in raw]
    remaining = total_days - sum(counts)
    remainders = sorted(
        enumerate(value - int(value) for value in raw),
        key=lambda item: item[1],
        reverse=True,
    )
    for idx, _ in remainders[:remaining]:
        counts[idx] += 1
    return tuple(counts)


def _build_daily_kc_series(
    total_days: int,
    *,
    kc_init: float,
    kc_mid: float,
    kc_end: float,
) -> List[float]:
    if total_days <= 0:
        return []
    if total_days == 1:
        return [float(kc_mid)]

    init_days, dev_days, mid_days, late_days = _allocate_stage_lengths(total_days)
    values: List[float] = []
    values.extend([float(kc_init)] * init_days)
    if dev_days > 0:
        values.extend(
            float(kc_init + (kc_mid - kc_init) * ((idx + 1) / dev_days))
            for idx in range(dev_days)
        )
    values.extend([float(kc_mid)] * mid_days)
    if late_days > 0:
        values.extend(
            float(kc_mid + (kc_end - kc_mid) * ((idx + 1) / late_days))
            for idx in range(late_days)
        )
    if len(values) < total_days:
        values.extend([float(kc_end)] * (total_days - len(values)))
    return values[:total_days]


def _build_aligned_kc_series(
    dates: pd.Series,
    *,
    analysis_start: Optional[str],
    analysis_end: Optional[str],
    default_kc: float,
    kc_init: Optional[float],
    kc_mid: Optional[float],
    kc_end: Optional[float],
    preseason_kc: float = 0.0,
) -> List[float]:
    if kc_init is None and kc_mid is None and kc_end is None:
        return [float(default_kc)] * len(dates)

    start_ts = pd.Timestamp(analysis_start) if analysis_start else None
    end_ts = pd.Timestamp(analysis_end) if analysis_end else None
    if start_ts is None and end_ts is None:
        return _build_daily_kc_series(
            len(dates),
            kc_init=float(default_kc if kc_init is None else kc_init),
            kc_mid=float(default_kc if kc_mid is None else kc_mid),
            kc_end=float(default_kc if kc_end is None else kc_end),
        )

    if start_ts is None:
        start_ts = dates.min()
    if end_ts is None:
        end_ts = dates.max()

    in_window = (dates >= start_ts) & (dates <= end_ts)
    window_len = int(in_window.sum())
    window_series = _build_daily_kc_series(
        window_len,
        kc_init=float(default_kc if kc_init is None else kc_init),
        kc_mid=float(default_kc if kc_mid is None else kc_mid),
        kc_end=float(default_kc if kc_end is None else kc_end),
    )

    kc_series = [float(preseason_kc)] * len(dates)
    window_idx = 0
    for idx, inside in enumerate(in_window.to_list()):
        if inside:
            kc_series[idx] = window_series[window_idx]
            window_idx += 1
    return kc_series


def _soil_grid_date_anchor() -> Tuple[str, str]:
    # soil_grid is static, but the fetch layer still expects a valid date window
    return ("2000-01-01", "2000-01-01")


class _TemporaryLoggerLevel:
    def __init__(self, logger_name: str, level: int):
        self._logger = logging.getLogger(logger_name)
        self._level = level
        self._original = self._logger.level

    def __enter__(self):
        self._logger.setLevel(self._level)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._logger.setLevel(self._original)
        return False


def _normalize_percent_like(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    if numeric <= 0:
        return None
    if numeric <= 1:
        return numeric
    if numeric <= 100:
        return numeric / 100.0
    if numeric <= 1000:
        return numeric / 1000.0
    return None


def _normalize_bulk_density_like(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    if numeric <= 0:
        return None
    if numeric <= 3.0:
        return numeric
    if numeric <= 30.0:
        return numeric / 10.0
    if numeric <= 300.0:
        return numeric / 100.0
    if numeric <= 3000.0:
        return numeric / 1000.0
    return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalize_root_depth_like(value: Any) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    if numeric <= 0:
        return None
    if numeric <= 5:
        return numeric
    if numeric <= 300:
        return numeric / 100.0
    if numeric <= 3000:
        return numeric / 1000.0
    return None


def _normalize_coarse_fragments_like(value: Any) -> Optional[float]:
    return _normalize_percent_like(value)


@lru_cache(maxsize=128)
def _fetch_soil_grid_snapshot(lat: float, lon: float) -> Dict[str, Any]:
    from climate_tookit.fetch_data.fetch_data import fetch_data
    from climate_tookit.fetch_data.source_data.sources.utils.models import SoilVariable

    start_date, end_date = _soil_grid_date_anchor()
    with _TemporaryLoggerLevel(
        "climate_tookit.fetch_data.source_data.sources.gee",
        logging.CRITICAL,
    ):
        soil_df = fetch_data(
            source="soil_grid",
            location_coord=(lat, lon),
            variables=[
                SoilVariable.bulk_density,
                SoilVariable.coarse_fragments,
                SoilVariable.field_capacity,
                SoilVariable.wilting_point,
                SoilVariable.clay_content,
                SoilVariable.sand_content,
                SoilVariable.organic_carbon,
            ],
            date_from=date.fromisoformat(start_date),
            date_to=date.fromisoformat(end_date),
            stage="transformed",
            verbose=False,
        )
    if soil_df is None or soil_df.empty:
        return {}
    return soil_df.iloc[0].to_dict()


@lru_cache(maxsize=128)
def _fetch_hwsd_snapshot(lat: float, lon: float) -> Dict[str, Any]:
    from climate_tookit.fetch_data.fetch_data import fetch_data
    from climate_tookit.fetch_data.source_data.sources.utils.models import SoilVariable

    start_date, end_date = _soil_grid_date_anchor()
    with _TemporaryLoggerLevel(
        "climate_tookit.fetch_data.source_data.sources.gee",
        logging.CRITICAL,
    ):
        hwsd_df = fetch_data(
            source="hwsd",
            location_coord=(lat, lon),
            variables=[
                SoilVariable.root_depth,
                SoilVariable.available_water_capacity,
                SoilVariable.drainage,
                SoilVariable.bulk_density,
            ],
            date_from=date.fromisoformat(start_date),
            date_to=date.fromisoformat(end_date),
            stage="transformed",
            verbose=False,
        )
    if hwsd_df is None or hwsd_df.empty:
        return {}
    return hwsd_df.iloc[0].to_dict()


def _derive_soil_storage_params_from_row(
    row: Dict[str, Any],
    *,
    root_depth_row: Optional[Dict[str, Any]] = None,
    crop_root_depth_m: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    field_capacity = _normalize_percent_like(row.get("soil_field_capacity"))
    wilting_point = _normalize_percent_like(row.get("soil_wilting_point"))
    bulk_density = _normalize_bulk_density_like(row.get("soil_bulk_density"))
    coarse_fragments = _normalize_coarse_fragments_like(row.get("soil_coarse_fragments"))
    clay_content = _normalize_percent_like(row.get("soil_clay_content"))
    sand_content = _normalize_percent_like(row.get("soil_sand_content"))
    organic_carbon = _normalize_percent_like(row.get("soil_organic_carbon"))
    site_root_depth = _normalize_root_depth_like((root_depth_row or {}).get("soil_root_depth"))
    available_water_capacity = _coerce_optional_float(
        (root_depth_row or {}).get("soil_available_water_capacity")
    )
    drainage = _coerce_optional_float((root_depth_row or {}).get("soil_drainage"))
    field_capacity_source = "soil_grid" if field_capacity is not None else "texture_pedotransfer"
    wilting_point_source = "soil_grid" if wilting_point is not None else "field_capacity_ratio"

    if field_capacity is None:
        texture_bonus = 0.0
        if clay_content is not None:
            texture_bonus += 0.20 * clay_content
        if sand_content is not None:
            texture_bonus -= 0.10 * sand_content
        if organic_carbon is not None:
            texture_bonus += 0.10 * organic_carbon
        field_capacity = min(max(0.10 + texture_bonus, 0.05), 0.60)
    if wilting_point is None and field_capacity is not None:
        wilting_point = min(max(field_capacity * 0.4, 0.02), field_capacity - 0.01)

    porosity = None
    if bulk_density is not None:
        porosity = min(max(1.0 - (bulk_density / 2.65), 0.20), 0.70)

    saturation_excess = None
    if porosity is not None and field_capacity is not None:
        saturation_excess = max(porosity - field_capacity, 0.05)
    elif field_capacity is not None:
        saturation_excess = max(0.45 - field_capacity, 0.05)

    if field_capacity is None or saturation_excess is None:
        return None

    crop_root_depth = _coerce_optional_float(crop_root_depth_m)
    if site_root_depth is not None and crop_root_depth is not None:
        effective_root_depth = min(site_root_depth, crop_root_depth)
        root_depth_source = "min(crop_default,hwsd)"
    elif site_root_depth is not None:
        effective_root_depth = site_root_depth
        root_depth_source = "hwsd"
    elif crop_root_depth is not None:
        effective_root_depth = crop_root_depth
        root_depth_source = "crop_default"
    else:
        effective_root_depth = 1.0
        root_depth_source = "default_1m"

    root_depth_factor = min(max(effective_root_depth, 0.25), 2.0)
    coarse_fragment_factor = 1.0 - min(max(coarse_fragments or 0.0, 0.0), 0.9)

    taw_mm = None
    if field_capacity is not None and wilting_point is not None and field_capacity > wilting_point:
        taw_mm = 1000.0 * (field_capacity - wilting_point) * effective_root_depth * coarse_fragment_factor

    saturation_storage_mm = None
    if porosity is not None and field_capacity is not None and porosity > field_capacity:
        saturation_storage_mm = 1000.0 * (porosity - field_capacity) * effective_root_depth * coarse_fragment_factor

    if taw_mm is not None:
        soilcp = min(max(taw_mm, 25.0), 400.0)
        soilcp_source = "taw"
    else:
        soilcp = min(max(DEFAULT_SOILCP * (field_capacity / 0.30) * root_depth_factor, 25.0), 400.0)
        soilcp_source = "heuristic"

    if saturation_storage_mm is not None:
        soilsat = min(max(saturation_storage_mm, 20.0), 300.0)
        soilsat_source = "saturation_storage"
    else:
        soilsat = min(max(DEFAULT_SOILSAT * (saturation_excess / 0.15) * root_depth_factor, 20.0), 300.0)
        soilsat_source = "heuristic"

    return {
        "soilcp": round(soilcp, 2),
        "soilsat": round(soilsat, 2),
        "source": (
            "soil_grid_scaled_hwsd_root_depth"
            if field_capacity_source == "soil_grid" and wilting_point_source == "soil_grid"
            else "soil_grid_texture_pedotransfer_hwsd_root_depth"
        ),
        "soilcp_source": soilcp_source,
        "soilsat_source": soilsat_source,
        "field_capacity_source": field_capacity_source,
        "wilting_point_source": wilting_point_source,
        "field_capacity_fraction": round(field_capacity, 4),
        "wilting_point_fraction": round(wilting_point, 4) if wilting_point is not None else None,
        "saturation_excess_fraction": round(saturation_excess, 4),
        "bulk_density_g_cm3": _coerce_optional_float(bulk_density),
        "soil_coarse_fragments_fraction": _coerce_optional_float(coarse_fragments),
        "soil_clay_fraction": _coerce_optional_float(clay_content),
        "soil_sand_fraction": _coerce_optional_float(sand_content),
        "soil_organic_carbon_fraction": _coerce_optional_float(organic_carbon),
        "crop_root_depth_m": crop_root_depth,
        "site_root_depth_m": _coerce_optional_float(site_root_depth),
        "root_depth_m": _coerce_optional_float(effective_root_depth),
        "root_depth_source": root_depth_source,
        "taw_mm": round(taw_mm, 2) if taw_mm is not None else None,
        "saturation_storage_mm": round(saturation_storage_mm, 2) if saturation_storage_mm is not None else None,
        "soil_available_water_capacity_mm_m": available_water_capacity,
        "soil_drainage_class": drainage,
    }


def _resolve_soil_storage_params(
    lat: float,
    lon: float,
    soilcp: float,
    soilsat: float,
    crop_root_depth_m: Optional[float] = None,
) -> Dict[str, Any]:
    if soilcp != DEFAULT_SOILCP or soilsat != DEFAULT_SOILSAT:
        return {
            "soilcp": float(soilcp),
            "soilsat": float(soilsat),
            "source": "user_provided",
        }

    try:
        soil_row = _fetch_soil_grid_snapshot(round(lat, 5), round(lon, 5))
    except Exception as exc:
        return {
            "soilcp": float(soilcp),
            "soilsat": float(soilsat),
            "source": "default_fallback",
            "warning": f"soil_grid lookup failed: {exc}",
        }

    try:
        root_depth_row = _fetch_hwsd_snapshot(round(lat, 5), round(lon, 5))
    except Exception as exc:
        root_depth_row = {"root_depth_warning": f"hwsd lookup failed: {exc}"}

    derived = _derive_soil_storage_params_from_row(
        soil_row,
        root_depth_row=root_depth_row,
        crop_root_depth_m=crop_root_depth_m,
    )
    if not derived:
        return {
            "soilcp": float(soilcp),
            "soilsat": float(soilsat),
            "source": "default_fallback",
            "warning": "soil_grid lookup returned insufficient values; using defaults",
        }
    if root_depth_row.get("root_depth_warning"):
        derived["root_depth_warning"] = root_depth_row["root_depth_warning"]
    return derived

# Climate data helpers
def get_climate_data_for_season(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    source: str = 'auto',
    precip_source: Optional[str] = None,
    temp_source: Optional[str] = None,
    model: Optional[str] = None,
    scenario: Optional[str] = None,
    ee_project_id: Optional[str] = None,
    workers: int = 1,
) -> pd.DataFrame:
    """Fetch daily climate data for an explicit window and attach ET0."""
    force_source = None if source == 'auto' else source
    fetch_kwargs = {
        "force_source": force_source,
        "precip_source": precip_source,
        "temp_source": temp_source,
        "model": model,
        "scenario": scenario,
        "ee_project_id": ee_project_id,
    }
    if workers != 1:
        fetch_kwargs["workers"] = workers
    df = get_climate_data(
        lat,
        lon,
        start_date,
        end_date,
        **fetch_kwargs,
    )
    if df.empty:
        raise Exception(f"No climate data returned for {start_date} -> {end_date}")
    df = add_et0(df, lat) 
    return df

# Dry-spell detection
def detect_dry_spells(
    df: pd.DataFrame,
    min_dry_days: int = 7,
    precip_threshold: float = 1.0,
) -> List[Dict[str, Any]]:
    precip_col = next(
        (c for c in ['precipitation', 'precip', 'total_precipitation'] if c in df.columns),
        None,
    )
    if not precip_col or 'date' not in df.columns:
        return []

    df = df.sort_values('date').copy()
    df['is_dry'] = df[precip_col] < precip_threshold

    dry_spells: List[Dict[str, Any]] = []
    spell_start = None
    spell_days  = 0

    for idx, row in df.iterrows():
        if row['is_dry']:
            spell_start = spell_start or row['date']
            spell_days += 1
        else:
            if spell_start and spell_days >= min_dry_days:
                prev_loc = df.index.get_loc(idx) - 1
                dry_spells.append({
                    'start_date':  spell_start,
                    'end_date':    df.iloc[prev_loc]['date'],
                    'length_days': spell_days,
                })
            spell_start = None
            spell_days  = 0
            
    if spell_start and spell_days >= min_dry_days:
        dry_spells.append({
            'start_date':  spell_start,
            'end_date':    df.iloc[-1]['date'],
            'length_days': spell_days,
        })
    return dry_spells

def calculate_dry_spell_statistics(dry_spells: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not dry_spells:
        return {
            'number_of_dry_spells':       0,
            'max_dry_spell_length_days':  0,
            'mean_dry_spell_length_days': 0.0,
            'dry_spells':                 [],
        }
    lengths = [s['length_days'] for s in dry_spells]
    dist: Dict[str, int] = {}
    for ln in lengths:
        key = f"{(ln // 10) * 10}-{(ln // 10) * 10 + 9}"
        dist[key] = dist.get(key, 0) + 1
    return {
        'number_of_dry_spells':       len(dry_spells),
        'max_dry_spell_length_days':  max(lengths),
        'mean_dry_spell_length_days': round(sum(lengths) / len(lengths), 2),
        'length_distribution':        dist,
        'dry_spells':                 dry_spells,
    }

# Soil water balance (Adaptation Atlas algorithm)
DEFAULT_SOILCP  = 100.0
DEFAULT_SOILSAT = 100.0

def calc_water_balance(
    df: pd.DataFrame,
    soilcp:  float = DEFAULT_SOILCP,
    soilsat: float = DEFAULT_SOILSAT,
    kc:      float = 1.0,
    init_avail: float = 0.0,
    kc_init: Optional[float] = None,
    kc_mid: Optional[float] = None,
    kc_end: Optional[float] = None,
    depletion_fraction_p: float = DEFAULT_DEPLETION_FRACTION_P,
    analysis_start: Optional[str] = None,
    analysis_end: Optional[str] = None,
    preseason_kc: float = 0.0,
) -> pd.DataFrame:
    """
    Run a day-by-day root-zone water balance with TAW/RAW style depletion.
    `soilcp` is treated as total available water (TAW, mm) and `soilsat` as
    excess storage above field capacity before runoff (mm). Returns the input
    frame with per-day columns including ERATIO (stress coefficient / AET:PET
    ratio relative to crop demand), LOGGING, RUNOFF, Kc, and available soil
    water. PET is taken from `ET0_mm_day`; actual crop demand is
    ERATIO * Kc * PET. Also returns seasonal-accounting helpers for WRSI:
    CROP_WATER_REQUIREMENT_MM and ACTUAL_CROP_ET_MM.
    """
    precip_col = next(
        (c for c in ['precipitation', 'precip', 'total_precipitation'] if c in df.columns),
        None,
    )
    out = df.sort_values('date').copy() if 'date' in df.columns else df.copy()
    if not precip_col or 'ET0_mm_day' not in out.columns:
        out['ERATIO']  = pd.NA
        out['LOGGING'] = pd.NA
        out['RUNOFF']  = pd.NA
        return out

    if 'date' in out.columns:
        out['date'] = pd.to_datetime(out['date'])
    rain = out[precip_col].fillna(0).to_numpy()
    pet  = out['ET0_mm_day'].fillna(0).to_numpy()
    if 'date' in out.columns:
        kc_series = _build_aligned_kc_series(
            out['date'],
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            default_kc=float(kc),
            kc_init=kc_init,
            kc_mid=kc_mid,
            kc_end=kc_end,
            preseason_kc=preseason_kc,
        )
    else:
        if kc_init is not None or kc_mid is not None or kc_end is not None:
            kc_series = _build_daily_kc_series(
                len(out),
                kc_init=float(kc if kc_init is None else kc_init),
                kc_mid=float(kc if kc_mid is None else kc_mid),
                kc_end=float(kc if kc_end is None else kc_end),
            )
        else:
            kc_series = [float(kc)] * len(out)
    depletion_fraction_p = min(max(float(depletion_fraction_p), 0.05), 0.95)

    eratios, loggings, runoffs, availabilities, depletions = [], [], [], [], []
    crop_water_requirements, actual_crop_ets = [], []
    avail = min(max(float(init_avail), 0.0), float(soilcp))
    raw_mm = float(soilcp) * depletion_fraction_p
    critical_band = max((1.0 - depletion_fraction_p) * float(soilcp), 1e-6)
    for r, e, kc_day in zip(rain, pet, kc_series):
        avail = min(max(avail, 0.0), float(soilcp))
        depletion = max(float(soilcp) - avail, 0.0)
        if depletion <= raw_mm:
            eratio = 1.0
        else:
            eratio = max(avail / critical_band, 0.0)
        eratio = min(eratio, 1.0)
        crop_water_requirement = float(kc_day) * float(e)
        demand = eratio * crop_water_requirement

        result  = avail + float(r) - demand
        logging = min(max(result - soilcp, 0.0), soilsat)
        runoff  = max(result - logging - soilcp, 0.0)
        avail   = max(min(soilcp, result), 0.0)

        eratios.append(eratio)
        loggings.append(logging)
        runoffs.append(runoff)
        availabilities.append(avail)
        depletions.append(max(float(soilcp) - avail, 0.0))
        crop_water_requirements.append(crop_water_requirement)
        actual_crop_ets.append(demand)

    out['ERATIO']  = eratios
    out['LOGGING'] = loggings
    out['RUNOFF']  = runoffs
    out['Kc'] = kc_series
    out['CROP_WATER_REQUIREMENT_MM'] = crop_water_requirements
    out['ACTUAL_CROP_ET_MM'] = actual_crop_ets
    out['RAW_MM'] = raw_mm
    out['AVAILABLE_SOIL_WATER_MM'] = availabilities
    out['DEPLETION_MM'] = depletions
    return out


def summarize_water_balance(
    wb: pd.DataFrame,
    *,
    wrsi_floor: float = 0.0,
    wrsi_ceiling: float = 100.0,
) -> Dict[str, Any]:
    if wb is None or wb.empty:
        return {}

    summary: Dict[str, Any] = {}
    if 'ERATIO' in wb.columns:
        eratio = wb['ERATIO'].dropna()
        if not eratio.empty:
            summary['NDWS'] = int((eratio < 0.5).sum())
            summary['mean_eratio'] = float(eratio.mean())
    if 'LOGGING' in wb.columns:
        logging = wb['LOGGING'].dropna()
        if not logging.empty:
            summary['NDWL0'] = int((logging > 0).sum())
            summary['mean_logging_mm'] = float(logging.mean())

    crop_water_requirement = None
    if 'CROP_WATER_REQUIREMENT_MM' in wb.columns:
        crop_water_requirement = float(wb['CROP_WATER_REQUIREMENT_MM'].fillna(0).sum())
        summary['crop_water_requirement_mm'] = crop_water_requirement
    actual_crop_et = None
    if 'ACTUAL_CROP_ET_MM' in wb.columns:
        actual_crop_et = float(wb['ACTUAL_CROP_ET_MM'].fillna(0).sum())
        summary['actual_crop_et_mm'] = actual_crop_et

    if (
        crop_water_requirement is not None
        and actual_crop_et is not None
        and crop_water_requirement > 0
    ):
        wrsi = 100.0 * actual_crop_et / crop_water_requirement
        summary['WRSI'] = round(min(max(wrsi, wrsi_floor), wrsi_ceiling), 2)

    if 'AVAILABLE_SOIL_WATER_MM' in wb.columns and not wb['AVAILABLE_SOIL_WATER_MM'].empty:
        summary['ending_soil_water_mm'] = float(wb['AVAILABLE_SOIL_WATER_MM'].iloc[-1])
    if 'RUNOFF' in wb.columns:
        summary['runoff_mm'] = float(wb['RUNOFF'].fillna(0).sum())

    return summary

# Season statistics
def calculate_season_statistics(
    df:      pd.DataFrame,
    soilcp:  float = DEFAULT_SOILCP,
    soilsat: float = DEFAULT_SOILSAT,
    kc:      float = 1.0,
    kc_init: Optional[float] = None,
    kc_mid: Optional[float] = None,
    kc_end: Optional[float] = None,
    depletion_fraction_p: float = DEFAULT_DEPLETION_FRACTION_P,
    analysis_start: Optional[str] = None,
    analysis_end: Optional[str] = None,
    init_avail: float = 0.0,
    thi_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    working = df.sort_values('date').copy() if 'date' in df.columns else df.copy()
    if 'date' in working.columns:
        working['date'] = pd.to_datetime(working['date'])

    analysis_df = working
    analysis_mask = None
    if 'date' in working.columns and (analysis_start or analysis_end):
        mask = pd.Series(True, index=working.index)
        if analysis_start:
            mask &= working['date'] >= pd.Timestamp(analysis_start)
        if analysis_end:
            mask &= working['date'] <= pd.Timestamp(analysis_end)
        if mask.any():
            analysis_mask = mask
            analysis_df = working.loc[mask].copy()

    precip_col = next(
        (c for c in ['precipitation', 'precip', 'total_precipitation'] if c in analysis_df.columns),
        None,
    )
    p = None
    if precip_col:
        p = analysis_df[precip_col].copy()
        stats['total_precipitation_mm']      = float(p.sum())
        stats['mean_daily_precipitation_mm'] = float(p.mean())
        stats['max_daily_precipitation_mm']  = float(p.max())
        stats['rainy_days']                  = int((p >= 1.0).sum())
        stats['dry_days']                    = int((p < 1.0).sum())
        # NDD: Number of Dry Days (precip < 1 mm) -- canonical hazard label
        stats['NDD']                         = int((p < 1.0).sum())
        stats['dry_spell_statistics']        = calculate_dry_spell_statistics(
            detect_dry_spells(analysis_df, min_dry_days=7, precip_threshold=1.0)
        )
    tmax_col = next(
        (c for c in ['max_temperature', 'tmax', 'maximum_2m_air_temperature'] if c in analysis_df.columns),
        None,
    )
    tmin_col = next(
        (c for c in ['min_temperature', 'tmin', 'minimum_2m_air_temperature'] if c in analysis_df.columns),
        None,
    )
    if tmax_col and tmin_col:
        tmax = analysis_df[tmax_col].copy()
        tmin = analysis_df[tmin_col].copy()
        if tmax.mean() > 100:
            tmax -= 273.15
            tmin -= 273.15
        tavg = (tmax + tmin) / 2
        stats['mean_temperature_c'] = float(tavg.mean())
        stats['mean_tmax_c']        = float(tmax.mean())
        stats['mean_tmin_c']        = float(tmin.mean())
        stats['max_temperature_c']  = float(tmax.max())
        stats['min_temperature_c']  = float(tmin.min())
        # Canonical hazard labels: Max Tmax and Min Tmin
        stats['max_tmax_c']         = float(tmax.max())
        stats['min_tmin_c']         = float(tmin.min())
        # Adaptation Atlas counts threshold exceedance inclusively (>= threshold).
        stats['NTx35']              = int((tmax >= 35).sum())
        stats['NTx40']              = int((tmax >= 40).sum())
        humidity_col = next(
            (c for c in ['humidity', 'relative_humidity'] if c in analysis_df.columns),
            None,
        )
        if humidity_col:
            try:
                thi_frame = pd.DataFrame(
                    {
                        'date': analysis_df['date'],
                        'tmax': tmax,
                        'tmin': tmin,
                        'humidity': pd.to_numeric(analysis_df[humidity_col], errors='coerce'),
                    }
                )
                thi_daily = compute_daily_thi(
                    thi_frame,
                    thresholds=(thi_profile or {}).get('thresholds'),
                    livestock_type=(thi_profile or {}).get('livestock_type', DEFAULT_LIVESTOCK_TYPE),
                    climate_profile=(thi_profile or {}).get('climate_profile_applied', DEFAULT_LIVESTOCK_CLIMATE_PROFILE),
                    elevation_m=(thi_profile or {}).get('elevation_m'),
                )
            except ValueError:
                thi_daily = None
            if thi_daily is not None and thi_daily['thi'].notna().any():
                counts = thi_daily['thi_class'].value_counts(dropna=True)
                stats['thi_livestock_type'] = (thi_profile or {}).get('livestock_type', DEFAULT_LIVESTOCK_TYPE)
                stats['thi_livestock_label'] = (thi_profile or {}).get('label', 'Cattle (dairy)')
                stats['thi_climate_profile'] = (thi_profile or {}).get('climate_profile_applied', DEFAULT_LIVESTOCK_CLIMATE_PROFILE)
                stats['thi_threshold_source'] = describe_thi_method().get('threshold_reference')
                stats['thi_method_note'] = 'operational defaults | mean-temp+RH THI'
                stats['mean_thi'] = float(thi_daily['thi'].mean())
                stats['max_thi'] = float(thi_daily['thi'].max())
                stats['thi_none_days'] = int(counts.get('none', 0))
                stats['thi_mild_days'] = int(counts.get('mild', 0))
                stats['thi_moderate_days'] = int(counts.get('moderate', 0))
                stats['thi_severe_days'] = int(counts.get('severe', 0))
                stats['thi_stress_days'] = int(
                    counts.get('mild', 0) + counts.get('moderate', 0) + counts.get('severe', 0)
                )

    # Soil-water diagnostics derived from shared running root-zone water balance.
    #   NDWS  = days the crop cannot meet half its evaporative demand (ERATIO < 0.5)
    #   NDWL0 = days soil water exceeds field capacity (LOGGING > 0)
    #   WRSI  = seasonal actual crop ET / crop water requirement * 100
    if p is not None and 'ET0_mm_day' in working.columns:
        wb = calc_water_balance(
            working,
            soilcp=soilcp,
            soilsat=soilsat,
            kc=kc,
            init_avail=init_avail,
            kc_init=kc_init,
            kc_mid=kc_mid,
            kc_end=kc_end,
            depletion_fraction_p=depletion_fraction_p,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
        )
        if analysis_mask is not None:
            wb = wb.loc[analysis_mask]
        stats.update(summarize_water_balance(wb))
    return stats

def evaluate_threshold(value: float, thresholds: Dict[str, Tuple]) -> str:
    for level, (lower, upper) in thresholds.items():
        if lower is None and value < upper:
            return level
        if upper is None and value > lower:
            return level
        if lower is not None and upper is not None and lower <= value <= upper:
            return level
    return 'unknown'


def _hazard_status_symbol(status: str) -> str:
    status_lc = str(status or "").lower()
    if status_lc in {"none", "no_stress"} or "no_stress" in status_lc:
        return "OK"
    if "mild" in status_lc or "moderate" in status_lc:
        return "!!"
    return "XX"

def evaluate_hazard_metrics(
    stats: Dict[str, Any],
    thresholds: Dict[str, Dict[str, Tuple]],
) -> Dict[str, Any]:
    hazard_eval: Dict[str, Any] = {}
    for metric_key, spec in HAZARD_EVAL_SPECS.items():
        if metric_key not in thresholds:
            continue
        stat_key = spec['stat_key']
        if stat_key not in stats:
            continue
        value = stats[stat_key]
        hazard_eval[spec['result_key']] = {
            spec['value_key']: round(value, 2) if isinstance(value, (int, float)) else value,
            'status': evaluate_threshold(value, thresholds[metric_key]),
        }
    return hazard_eval

# Long-Term Mean (Baseline) aggregation
_LTM_SCALAR_KEYS = (
    'total_precipitation_mm', 'mean_daily_precipitation_mm', 'max_daily_precipitation_mm',
    'rainy_days', 'dry_days', 'NDD',
    'mean_temperature_c', 'mean_tmax_c', 'mean_tmin_c',
    'max_temperature_c', 'min_temperature_c', 'max_tmax_c', 'min_tmin_c',
    'mean_thi', 'max_thi', 'thi_none_days', 'thi_mild_days', 'thi_moderate_days', 'thi_severe_days', 'thi_stress_days',
    'crop_water_requirement_mm', 'actual_crop_et_mm', 'ending_soil_water_mm', 'WRSI',
    'NTx35', 'NTx40', 'NDWS', 'NDWL0',
)

def _avg_dry_spell_stats(per_season: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts, max_l, mean_l = [], [], []
    bucket_sums: Dict[str, float] = {}
    n_total = 0
    for stats in per_season:
        ds = stats.get('dry_spell_statistics')
        if not ds:
            continue
        n_total += 1
        counts.append(ds.get('number_of_dry_spells', 0))
        max_l.append(ds.get('max_dry_spell_length_days', 0))
        if ds.get('number_of_dry_spells', 0) > 0:
            mean_l.append(ds.get('mean_dry_spell_length_days', 0))
        for bucket, n in (ds.get('length_distribution') or {}).items():
            bucket_sums[bucket] = bucket_sums.get(bucket, 0) + n
    if not counts:
        return {}
    out = {
        'number_of_dry_spells':       round(sum(counts) / len(counts), 2),
        'max_dry_spell_length_days':  round(sum(max_l)  / len(max_l),  2) if max_l  else 0,
        'mean_dry_spell_length_days': round(sum(mean_l) / len(mean_l), 2) if mean_l else 0,
    }
    if bucket_sums:
        out['length_distribution'] = {
            b: round(total / n_total, 2) for b, total in bucket_sums.items()
        }
    return out

def compute_ltm_baseline(
    assessments: List[Dict[str, Any]],
    crop_name:   str,
    thresholds:  Dict[str, Any],
) -> Dict[str, Any]:
    """
    Long-Term Mean baseline across all evaluated seasons.
    When multiple seasons per year exist (fixed-season two-season mode), produces one LTM entry per season slot ('season_number') so the seasonal signal is
    preserved. Single-season inputs collapse to one overall LTM block.
    """
    # Group by season_number (defaults to 1 for explicit/single-season modes)
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for a in assessments:
        sn = a.get('season_info', {}).get('season_number', 1) or 1
        grouped.setdefault(sn, []).append(a)

    ltm_blocks: List[Dict[str, Any]] = []
    for sn in sorted(grouped):
        bucket = grouped[sn]
        stats_list = [a.get('season_statistics', {}) for a in bucket]
        agg: Dict[str, Any] = {}
        for k in _LTM_SCALAR_KEYS:
            vals = [s[k] for s in stats_list if k in s and s[k] is not None]
            if vals:
                agg[k] = round(sum(vals) / len(vals), 2)
        ds_agg = _avg_dry_spell_stats(stats_list)
        if ds_agg:
            agg['dry_spell_statistics'] = ds_agg

        years   = sorted({a['season_info']['year'] for a in bucket if 'year' in a['season_info']})
        lengths = [a['season_info'].get('length_days') for a in bucket
                   if a['season_info'].get('length_days') is not None]
        total   = max((a['season_info'].get('total_seasons_per_year', 1) for a in bucket), default=1)

        hazard_eval = evaluate_hazard_metrics(agg, thresholds)

        ltm_blocks.append({
            'season_number':          sn,
            'total_seasons_per_year': total,
            'n_seasons_averaged':     len(bucket),
            'years_covered':          years,
            'mean_length_days':       round(sum(lengths) / len(lengths), 1) if lengths else None,
            'thi_profile':            bucket[0].get('thi_profile'),
            'water_balance_methodology': bucket[0].get('water_balance_methodology'),
            'season_statistics':      agg,
            'hazard_evaluation':      hazard_eval,
        })

    return {
        'crop':            crop_name,
        'n_total_seasons': len(assessments),
        'baseline_method': 'long_term_mean',
        'water_balance_methodology': assessments[0].get('water_balance_methodology') if assessments else None,
        'per_season':      ltm_blocks,
    }

def _comparison_value_from_stats(stats: Dict[str, Any], stat_key: str) -> Optional[float]:
    if stat_key in stats:
        return stats.get(stat_key)
    ds = stats.get('dry_spell_statistics') or {}
    return ds.get(stat_key)

def build_actual_vs_ltm_comparisons(
    assessments: List[Dict[str, Any]],
    baseline_ltm: Dict[str, Any],
) -> List[Dict[str, Any]]:
    ltm_by_season = {
        blk.get('season_number', 1): blk
        for blk in (baseline_ltm.get('per_season') or [])
    }
    out: List[Dict[str, Any]] = []
    for assessment in assessments:
        season_info = assessment.get('season_info', {})
        sn = season_info.get('season_number', 1) or 1
        ltm_block = ltm_by_season.get(sn)
        if not ltm_block:
            continue
        actual_stats = assessment.get('season_statistics', {})
        baseline_stats = ltm_block.get('season_statistics', {})
        metric_rows: Dict[str, Any] = {}
        for stat_key, metric_id, label, unit in COMPARISON_METRIC_SPECS:
            actual = _comparison_value_from_stats(actual_stats, stat_key)
            baseline = _comparison_value_from_stats(baseline_stats, stat_key)
            if actual is None or baseline is None:
                continue
            delta = round(actual - baseline, 2)
            pct = round(_percent_change(actual - baseline, baseline), 2)
            metric_rows[metric_id] = {
                'label': label,
                'unit': unit,
                'actual': round(actual, 2),
                'baseline_ltm': round(baseline, 2),
                'delta': delta,
                'pct': pct,
            }
        hazard_status_comparison: Dict[str, Any] = {}
        for result_key in HAZARD_PRINT_ORDER:
            actual_h = (assessment.get('hazard_evaluation') or {}).get(result_key)
            baseline_h = (ltm_block.get('hazard_evaluation') or {}).get(result_key)
            if not actual_h or not baseline_h:
                continue
            hazard_status_comparison[result_key] = {
                'actual_status': actual_h.get('status'),
                'baseline_ltm_status': baseline_h.get('status'),
            }
        out.append({
            'year': season_info.get('year'),
            'season_number': sn,
            'total_seasons_per_year': season_info.get('total_seasons_per_year', 1),
            'metrics': metric_rows,
            'hazard_status_comparison': hazard_status_comparison,
        })
    return out
# Main hazard calculation
def calculate_hazards(
    crop_name:         str,
    location_coord:    Tuple[float, float],
    date_from:         str,
    date_to:           str,
    season_start:      Optional[str]  = None,
    season_end:        Optional[str]  = None,
    fixed_season:      Optional[str]  = None,
    source:            str            = 'auto',
    precip_source:     Optional[str]  = None,
    temp_source:       Optional[str]  = None,
    custom_thresholds: Optional[Dict] = None,
    gap_days:          int            = 30,
    min_season_days:   int            = 30,
    soilcp:            float          = DEFAULT_SOILCP,
    soilsat:           float          = DEFAULT_SOILSAT,
    spinup_days:       int            = DEFAULT_SPINUP_DAYS,
    water_balance_window: str         = FULL_WINDOW_WATER_BALANCE,
    calendar_source:   Optional[str]  = None,
    calendar_system:   str            = "rf",
    livestock_type:    str            = DEFAULT_LIVESTOCK_TYPE,
    livestock_climate_profile: str    = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    livestock_elevation_override_m: Optional[float] = None,
    ee_project_id: Optional[str] = None,
    workers: int = 1,
) -> Dict[str, Any]:

    lat, lon = location_coord
    calendar_system = str(calendar_system).lower()
    if calendar_system not in CALENDAR_SYSTEM_CHOICES:
        return {
            "error": (
                f"Invalid calendar_system '{calendar_system}'. "
                f"Choose from {', '.join(CALENDAR_SYSTEM_CHOICES)}."
            )
        }
    try:
        water_balance_window = _normalize_water_balance_window_mode(water_balance_window)
    except ValueError as exc:
        return {"error": str(exc)}
    try:
        crop_normalized = normalize_crop_name(
            crop_name,
            require_hazard_thresholds=not custom_thresholds,
        )
    except ValueError as exc:
        return {
            'error': str(exc),
            'available_crops': threshold_supported_crop_names(),
        }
    try:
        thi_profile = resolve_thi_profile(
            livestock_type=livestock_type,
            climate_profile=livestock_climate_profile,
            lat=lat,
            lon=lon,
            elevation_m=livestock_elevation_override_m,
            auto_fetch_elevation=True,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    thresholds = resolve_thresholds(
        crop_normalized,
        custom_thresholds,
        livestock_type=livestock_type,
        livestock_climate_profile=livestock_climate_profile,
        lat=lat,
        lon=lon,
        livestock_elevation_override_m=livestock_elevation_override_m,
    )
    crop_water_balance = resolve_crop_water_balance_params(crop_normalized)
    requested_end_year = datetime.fromisoformat(date_to).year
    try:
        _validate_source_window(source, requested_end_year)
        if normalize_climate_dataset_name(source) == PAIRED_SOURCE_SENTINEL:
            _validate_paired_sources(precip_source, temp_source, requested_end_year)
    except ValueError as exc:
        return {'error': str(exc)}
    try:
        requested_calendar_preset = _resolve_calendar_preset_request(
            lat=lat,
            lon=lon,
            crop_name=crop_normalized,
            calendar_source=calendar_source,
            calendar_system=calendar_system,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    calendar_preset_used = False
    applied_calendar_preset: Optional[Dict[str, Any]] = None
    soil_parameters = _resolve_soil_storage_params(
        lat,
        lon,
        soilcp,
        soilsat,
        crop_root_depth_m=crop_water_balance.get("root_depth_m"),
    )

    # Branch A: explicit --season-start / --season-end
    if season_start and season_end:
        print(f"Using provided season dates: {season_start} to {season_end}")
        print(f"Climate data source: {source}")
        fetch_start = _shift_iso_date(season_start, -spinup_days)
        try:
            _validate_request_coverage(
                source,
                fetch_start,
                season_end,
                precip_source=precip_source,
                temp_source=temp_source,
            )
            df = get_climate_data_for_season(
                lat,
                lon,
                fetch_start,
                season_end,
                source=source,
                precip_source=precip_source,
                temp_source=temp_source,
                ee_project_id=ee_project_id,
                workers=workers,
            )
        except Exception as exc:
            return {
                "error": (
                    "Climate data fetch failed for requested hazard window "
                    f"{fetch_start}..{season_end}: {exc}"
                )
            }
        season_info = _attach_season_identity({
            'season_detected': True,
            'onset_date':      season_start,
            'cessation_date':  season_end,
            'fetch_start_date': fetch_start,
            'length_days':     (datetime.fromisoformat(season_end) - datetime.fromisoformat(season_start)).days,
            'spinup_days':     spinup_days,
            'method':          'user_provided',
            'source':          source,          # record dataset used
        })
        all_results = [{'season_info': season_info, 'df': df}]

    # fixed-season (mirrors seasons.py fixed-season mode)
    elif fixed_season:
        print(f"Fixed-season mode: {fixed_season}")
        try:
            fixed_defs = parse_fixed_seasons(fixed_season)
        except ValueError as exc:
            return {'error': f'Invalid --fixed-season argument: {exc}'}

        start_year = datetime.fromisoformat(date_from).year
        end_year   = datetime.fromisoformat(date_to).year
        try:
            for year in range(start_year, end_year + 1):
                for season_def in fixed_defs:
                    s_start, s_end = _fixed_window_dates_for_year(year, season_def)
                    fetch_start = _shift_iso_date(s_start, -spinup_days)
                    _validate_request_coverage(
                        source,
                        fetch_start,
                        s_end,
                        precip_source=precip_source,
                        temp_source=temp_source,
                    )
        except ValueError as exc:
            return {'error': str(exc)}

        fixed_kwargs = {"workers": workers} if workers != 1 else {}
        seasons_dict, annual_dict = fetch_and_analyze_years_fixed(
            lat, lon,
            fixed_seasons=fixed_defs,
            start_year=start_year,
            end_year=end_year,
            source=source,
            precip_source=precip_source,
            temp_source=temp_source,
            prefetch_pad_days=spinup_days,
            ee_project_id=ee_project_id,
            emit_fetch_errors=False,
            **fixed_kwargs,
        )
        num_seasons_per_year = len(fixed_defs) 
        all_results = []
        for year, seasons in sorted(seasons_dict.items()):
            year_fetch_error = (annual_dict.get(year) or {}).get("fetch_error")
            for season_idx, s in enumerate(seasons):   
                s_start = pd.to_datetime(s['onset']).strftime('%Y-%m-%d')
                s_end   = (
                    pd.to_datetime(s['cessation']).strftime('%Y-%m-%d')
                    if s.get('cessation') else date_to
                )
                fetch_start = _shift_iso_date(s_start, -spinup_days)
                season_info = _attach_season_identity({
                    'season_detected':        True,
                    'onset_date':             s_start,
                    'cessation_date':         s_end,
                    'fetch_start_date':       fetch_start,
                    'length_days':            s['length_days'],
                    'spinup_days':            spinup_days,
                    'method':                 'fixed_season',
                    'regime':                 s.get('regime', 'fixed'),
                    'year':                   year,
                    'season_number':          season_idx + 1,           
                    'total_seasons_per_year': num_seasons_per_year,     
                    'source':                 source,                   
                })
                df = _slice_prefetched_window(s.get('source_df'), fetch_start, s_end)
                if df is None:
                    df = _slice_prefetched_window(s.get('window_df'), fetch_start, s_end)
                if df is None and (s.get("fetch_error") or year_fetch_error):
                    fetch_error = s.get("fetch_error") or year_fetch_error
                    return {
                        "error": (
                            "Climate data fetch failed for fixed-season hazard window "
                            f"{fetch_start}..{s_end}: {fetch_error}"
                        )
                    }
                if df is None:
                    try:
                        season_fetch_kwargs = {"workers": workers} if workers != 1 else {}
                        df = get_climate_data_for_season(
                            lat,
                            lon,
                            fetch_start,
                            s_end,
                            source=source,
                            precip_source=precip_source,
                            temp_source=temp_source,
                            ee_project_id=ee_project_id,
                            **season_fetch_kwargs,
                        )
                    except Exception as exc:
                        return {
                            "error": (
                                "Climate data fetch failed for fixed-season hazard window "
                                f"{fetch_start}..{s_end}: {exc}"
                            )
                        }
                all_results.append({'season_info': season_info, 'df': df})
                all_results[-1]["eto_seasons"] = s.get("eto_seasons") or []
                all_results[-1]["eto_detection_note"] = s.get("eto_detection_note")
        if not all_results:
            return {'error': 'No seasons produced by fixed-season mode for the given date range.'}

    # auto-detect via fetch_and_analyze_years using the requested source policy
    else:
        detection_source = source
        print(f"Detecting growing season for {crop_name} at ({lat}, {lon})")
        if detection_source == 'auto':
            print("Climate data source: auto (chirps_v3_daily_rnl + agera_5 -> agera_5 -> era_5 -> chirps_v2+chirts)")
        else:
            print(f"Climate data source: {detection_source}")
        start_year = datetime.fromisoformat(date_from).year
        end_year   = datetime.fromisoformat(date_to).year
        try:
            _validate_request_coverage(
                detection_source,
                date_from,
                date_to,
                precip_source=precip_source,
                temp_source=temp_source,
            )
        except ValueError as exc:
            return {'error': str(exc)}
        auto_master_df = None
        if requested_calendar_preset:
            master_kwargs = {"workers": workers} if workers != 1 else {}
            auto_master_df = fetch_master_range_with_tail(
                lat,
                lon,
                start_year,
                end_year,
                source=detection_source,
                precip_source=precip_source,
                temp_source=temp_source,
                ee_project_id=ee_project_id,
                **master_kwargs,
            )
            seasons_dict, annual_dict = analyze_years_auto_on_prefetched_df(
                auto_master_df,
                lat,
                start_year,
                end_year,
            )
        else:
            auto_kwargs = {"workers": workers} if workers != 1 else {}
            seasons_dict, annual_dict = fetch_and_analyze_years(
                lat, lon, start_year=start_year, end_year=end_year, source=detection_source,
                precip_source=precip_source, temp_source=temp_source,
                ee_project_id=ee_project_id,
                **auto_kwargs,
            )
        if not any(seasons_dict.values()):
            detection_errors = _extract_detection_errors(annual_dict)
            if detection_errors:
                season_detection = _build_hazard_season_detection_error(
                    reason="season_detection_failed",
                    message=detection_errors[0],
                    details={"source": detection_source},
                )
                return {
                    'error': (
                        'Growing-season detection failed before season identification: '
                        f'{detection_errors[0]}'
                    ),
                    'season_detection': season_detection,
                }
            if requested_calendar_preset and auto_master_df is not None:
                print(
                    "  Auto season detection not reliable enough. "
                    f"Applying {requested_calendar_preset['calendar_source']} preset "
                    f"for crop={requested_calendar_preset['crop_name']} "
                    f"system={requested_calendar_preset['calendar_system']} "
                    f"-> {requested_calendar_preset['fixed_season']}"
                )
                fixed_defs = parse_fixed_seasons(requested_calendar_preset["fixed_season"])
                seasons_dict, annual_dict = analyze_years_fixed_on_prefetched_df(
                    auto_master_df,
                    fixed_defs,
                    start_year,
                    end_year,
                )
                calendar_preset_used = True
                applied_calendar_preset = dict(requested_calendar_preset)
                applied_calendar_preset["fallback_from_auto_status"] = "prompt_required"
            else:
                season_detection = _build_hazard_season_detection_error(
                    reason="no_seasons_detected_all_years",
                    message="No growing season detected.",
                    details={"source": detection_source},
                )
                return {
                    'error': (
                        'No growing season detected. '
                        'Provide --season-start/--season-end, use --fixed-season, '
                        'or retry with --calendar-source ggcmi.'
                    ),
                    'season_detection': season_detection,
                }
        all_results = []
        for year, seasons in sorted(seasons_dict.items()):
            num_seasons_per_year = len(seasons)
            for season_idx, s in enumerate(seasons):
                s_start = pd.to_datetime(s['onset']).strftime('%Y-%m-%d')
                s_end   = (
                    pd.to_datetime(s['cessation']).strftime('%Y-%m-%d')
                    if s.get('cessation') else date_to
                )
                fetch_start = _shift_iso_date(s_start, -spinup_days)
                season_info = _attach_season_identity({
                    'season_detected':        True,
                    'onset_date':             s_start,
                    'cessation_date':         s_end,
                    'fetch_start_date':       fetch_start,
                    'length_days':            s['length_days'],
                    'spinup_days':            spinup_days,
                    'method':                 'rainfall_based',
                    'regime':                 s.get('regime', 'auto'),
                    'year':                   year,
                    'season_number':          season_idx + 1,
                    'total_seasons_per_year': num_seasons_per_year,
                    'source':                 detection_source,
                })
                if calendar_preset_used:
                    season_info['method'] = 'fixed_season'
                    season_info['calendar_preset_fallback'] = True
                    season_info['calendar_preset'] = applied_calendar_preset
                    df = _slice_prefetched_window(s.get('source_df'), fetch_start, s_end)
                    if df is None:
                        df = _slice_prefetched_window(s.get('window_df'), fetch_start, s_end)
                    if df is None:
                        try:
                            season_fetch_kwargs = {"workers": workers} if workers != 1 else {}
                            df = get_climate_data_for_season(
                                lat,
                                lon,
                                fetch_start,
                                s_end,
                                source=detection_source,
                                precip_source=precip_source,
                                temp_source=temp_source,
                                ee_project_id=ee_project_id,
                                **season_fetch_kwargs,
                            )
                        except Exception as exc:
                            return {
                                "error": (
                                    "Climate data fetch failed for calendar-preset hazard window "
                                    f"{fetch_start}..{s_end}: {exc}"
                                )
                            }
                else:
                    try:
                        season_fetch_kwargs = {"workers": workers} if workers != 1 else {}
                        df = get_climate_data_for_season(
                            lat,
                            lon,
                            fetch_start,
                            s_end,
                            source=detection_source,
                            precip_source=precip_source,
                            temp_source=temp_source,
                            ee_project_id=ee_project_id,
                            **season_fetch_kwargs,
                        )
                    except Exception as exc:
                        return {
                            "error": (
                                "Climate data fetch failed for detected hazard season window "
                                f"{fetch_start}..{s_end}: {exc}"
                            )
                        }
                all_results.append({'season_info': season_info, 'df': df})
                if calendar_preset_used:
                    all_results[-1]["eto_seasons"] = s.get("eto_seasons") or []
                    all_results[-1]["eto_detection_note"] = s.get("eto_detection_note")
    # Evaluate hazards for every resolved season
    assessments = []
    for entry in all_results:
        stats = calculate_season_statistics(
            entry['df'],
            soilcp=soil_parameters['soilcp'],
            soilsat=soil_parameters['soilsat'],
            kc=float(crop_water_balance.get("kc_mid", 1.0)),
            kc_init=float(crop_water_balance.get("kc_init", crop_water_balance.get("kc_mid", 1.0))),
            kc_mid=float(crop_water_balance.get("kc_mid", 1.0)),
            kc_end=float(crop_water_balance.get("kc_end", crop_water_balance.get("kc_mid", 1.0))),
            depletion_fraction_p=float(
                crop_water_balance.get("depletion_fraction_p", DEFAULT_DEPLETION_FRACTION_P)
            ),
            analysis_start=entry['season_info'].get('onset_date'),
            analysis_end=entry['season_info'].get('cessation_date'),
            thi_profile=thi_profile,
        )
        stats, count_window = _apply_water_balance_window_mode(
            stats,
            entry["df"],
            entry["season_info"],
            soil_parameters,
            crop_water_balance,
            thi_profile=thi_profile,
            water_balance_window=water_balance_window,
            eto_seasons=entry.get("eto_seasons"),
            eto_detection_note=entry.get("eto_detection_note"),
        )
        hazard_eval = evaluate_hazard_metrics(stats, thresholds)
        methodology = build_water_balance_methodology(
            entry['season_info'],
            soil_parameters,
            crop_water_balance,
            count_window=count_window,
        )
        assessments.append({
            'crop':              crop_name,
            'location':          {'latitude': lat, 'longitude': lon},
            'season_info':       entry['season_info'],
            'thi_profile':       thi_profile,
            'soil_parameters':   soil_parameters,
            'water_balance_parameters': crop_water_balance,
            'water_balance_methodology': methodology,
            'season_statistics': stats,
            'hazard_evaluation': hazard_eval,
        })
    # Single season -> flat dict; multiple -> wrapped list with Baseline LTM
    if len(assessments) == 1:
        out = assessments[0]
        out['season_detection'] = _build_hazard_season_detection_from_assessments(assessments)
        out['calendar_source'] = calendar_source
        out['calendar_system'] = calendar_system
        out['calendar_preset_requested'] = requested_calendar_preset
        out['calendar_preset_used'] = calendar_preset_used
        out['calendar_preset'] = applied_calendar_preset
        return out
    auto_ltm_guard = _auto_ltm_guard_message(assessments)
    if auto_ltm_guard:
        return {
            'assessments': assessments,
            'thi_profile': thi_profile,
            'soil_parameters': soil_parameters,
            'water_balance_parameters': crop_water_balance,
            'water_balance_methodology': assessments[0].get('water_balance_methodology'),
            'warning': auto_ltm_guard,
            'season_detection': _build_hazard_season_detection_from_assessments(
                assessments,
                warning=auto_ltm_guard,
            ),
            'calendar_source': calendar_source,
            'calendar_system': calendar_system,
            'calendar_preset_requested': requested_calendar_preset,
            'calendar_preset_used': calendar_preset_used,
            'calendar_preset': applied_calendar_preset,
            'baseline_ltm': None,
            'baseline_ltm_comparisons': [],
        }
    baseline_ltm = compute_ltm_baseline(assessments, crop_name, thresholds)
    return {
        'assessments': assessments,
        'thi_profile': thi_profile,
        'soil_parameters': soil_parameters,
        'water_balance_parameters': crop_water_balance,
        'water_balance_methodology': assessments[0].get('water_balance_methodology'),
        'season_detection': _build_hazard_season_detection_from_assessments(assessments),
        'calendar_source': calendar_source,
        'calendar_system': calendar_system,
        'calendar_preset_requested': requested_calendar_preset,
        'calendar_preset_used': calendar_preset_used,
        'calendar_preset': applied_calendar_preset,
        'baseline_ltm': baseline_ltm,
        'baseline_ltm_comparisons': build_actual_vs_ltm_comparisons(assessments, baseline_ltm),
    }

# Pretty printer
def _fmt_date(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime('%Y-%m-%d')
    return str(d)[:10]

def _get_hazard_spec_by_result_key(result_key: str) -> Optional[Dict[str, str]]:
    for spec in HAZARD_EVAL_SPECS.values():
        if spec['result_key'] == result_key:
            return spec
    return None

def _print_ltm_block(ltm: Dict[str, Any]) -> None:
    """Pretty-print the Baseline LTM (Long-Term Mean) summary."""
    print(f"\n{'='*70}")
    print(f"  BASELINE LTM (LONG-TERM MEAN): {ltm['crop'].upper()}")
    print(f"  Averaged across {ltm['n_total_seasons']} season(s)  -- method: {ltm['baseline_method']}")
    print(f"{'='*70}")

    for blk in ltm['per_season']:
        sn, total = blk['season_number'], blk['total_seasons_per_year']
        label = f"Season {sn} of {total}" if total and total > 1 else "Overall"
        years = blk.get('years_covered') or []
        year_range = f"{years[0]}-{years[-1]}" if len(years) >= 2 else (str(years[0]) if years else "n/a")

        print(f"\n  {label}  ({blk['n_seasons_averaged']} seasons, years {year_range})")
        print(f"  {'─'*66}")
        if blk.get('mean_length_days') is not None:
            print(f"  Mean season length: {blk['mean_length_days']} days")

        s = blk['season_statistics']
        if 'total_precipitation_mm' in s:
            print(f"\n  Precipitation (LTM means)")
            print(f"  {'─'*66}")
            print(f"  {'Total':<32} {s['total_precipitation_mm']:>15.2f}  mm")
            print(f"  {'Daily Mean':<32} {s.get('mean_daily_precipitation_mm', 0):>15.2f}  mm")
            print(f"  {'Daily Maximum':<32} {s.get('max_daily_precipitation_mm', 0):>15.2f}  mm")
            print(f"  {'Rainy Days (>=1mm)':<32} {s.get('rainy_days', 0):>15.2f}  days")
            print(f"  {'NDD (Dry Days)':<32} {s.get('NDD', s.get('dry_days', 0)):>15.2f}  days")

        if 'dry_spell_statistics' in s:
            ds = s['dry_spell_statistics']
            print(f"\n  Dry Spell Statistics (LTM means; >=7 consecutive days <1mm)")
            print(f"  {'─'*66}")
            print(f"  {'Number of Dry Spells':<32} {ds.get('number_of_dry_spells', 0):>15.2f}  spells")
            print(f"  {'Max Dry Spell Length':<32} {ds.get('max_dry_spell_length_days', 0):>15.2f}  days")
            print(f"  {'Mean Dry Spell Length':<32} {ds.get('mean_dry_spell_length_days', 0):>15.2f}  days")

        if 'mean_temperature_c' in s:
            print(f"\n  Temperature (LTM means)")
            print(f"  {'─'*66}")
            print(f"  {'Mean Temperature':<32} {s['mean_temperature_c']:>15.2f}  deg C")
            print(f"  {'Mean Tmax':<32} {s.get('mean_tmax_c', 0):>15.2f}  deg C")
            print(f"  {'Mean Tmin':<32} {s.get('mean_tmin_c', 0):>15.2f}  deg C")
            print(f"  {'Max Tmax':<32} {s.get('max_tmax_c', s.get('max_temperature_c', 0)):>15.2f}  deg C")
            print(f"  {'Min Tmin':<32} {s.get('min_tmin_c', s.get('min_temperature_c', 0)):>15.2f}  deg C")

        # New hazard counts
        has_counts = any(k in s for k in ('mean_thi', 'thi_stress_days', 'NTx35', 'NTx40', 'NDWS', 'NDWL0', 'WRSI'))
        if has_counts:
            print(f"\n  Hazard Indices (LTM means)")
            print(f"  {'─'*66}")
            if 'WRSI' in s:
                print(f"  {'WRSI (seasonal satisfaction)':<32} {s['WRSI']:>15.2f}  %")
            if 'crop_water_requirement_mm' in s:
                print(f"  {'Crop Water Requirement':<32} {s['crop_water_requirement_mm']:>15.2f}  mm")
            if 'actual_crop_et_mm' in s:
                print(f"  {'Actual Crop ET':<32} {s['actual_crop_et_mm']:>15.2f}  mm")
            if 'mean_thi' in s:
                print(f"  {_thi_profile_label(blk.get('thi_profile') or s):<32} {s['mean_thi']:>15.2f}  index")
            if 'max_thi' in s:
                max_label = f"Max {_thi_profile_label(blk.get('thi_profile') or s)}"
                print(f"  {max_label:<32} {s['max_thi']:>15.2f}  index")
            if 'thi_stress_days' in s:
                print(f"  {'THI stress days':<32} {s['thi_stress_days']:>15.2f}  days")
            if 'NTx35' in s:
                print(f"  {'NTx35 (days Tmax > 35C)':<32} {s['NTx35']:>15.2f}  days")
            if 'NTx40' in s:
                print(f"  {'NTx40 (days Tmax > 40C)':<32} {s['NTx40']:>15.2f}  days")
            if 'NDWS' in s:
                print(f"  {'NDWS (water-stress days)':<32} {s['NDWS']:>15.2f}  days")
            if 'NDWL0' in s:
                print(f"  {'NDWL0 (water-logging days)':<32} {s['NDWL0']:>15.2f}  days")
            if 'NDWS' in s or 'NDWL0' in s:
                print("  Note: NDWS/NDWL0 come from the crop water-balance model, not a raw precip-minus-ET0 count.")
                methodology = blk.get('water_balance_methodology') or ltm.get('water_balance_methodology') or {}
                count_window = methodology.get("count_window") or {}
                if count_window.get("applied_mode") == CROP_ACTIVE_WATER_BALANCE:
                    print("  Count window: crop-active ETO sub-season(s) inside fixed window.")

        h = blk.get('hazard_evaluation', {})
        if h:
            print(f"\n  Hazard Assessment (vs crop thresholds, LTM-based)")
            print(f"  {'─'*66}")
            if 'precipitation' in h:
                pp  = h['precipitation']
                sym = _hazard_status_symbol(pp['status'])
                print(f"  {'Precipitation':<25} {pp['value_mm']:>16.2f} mm  [{sym}] {pp['status'].replace('_', ' ').upper()}")
            if 'temperature' in h:
                tt  = h['temperature']
                sym = _hazard_status_symbol(tt['status'])
                print(f"  {'Temperature':<25} {tt['value_c']:>16.2f} degC [{sym}] {tt['status'].replace('_', ' ').upper()}")
            for hazard_key in ('THI', 'NDD', 'NTx35', 'NTx40', 'NDWS', 'NDWL0'):
                if hazard_key not in h:
                    continue
                spec = _get_hazard_spec_by_result_key(hazard_key)
                item = h[hazard_key]
                sym = _hazard_status_symbol(item['status'])
                value_key = spec['value_key']
                print(
                    f"  {spec['label']:<25} {item[value_key]:>16.2f} {spec['unit']:<6} "
                    f"[{sym}] {item['status'].replace('_', ' ').upper()}"
                )
    print(f"\n{'='*70}\n")

def _print_actual_vs_ltm_comparisons(comparisons: List[Dict[str, Any]]) -> None:
    if not comparisons:
        return
    print(f"\n{'='*70}")
    print("  ACTUAL YEAR vs BASELINE LTM")
    print(f"{'='*70}")
    for cmp_block in comparisons:
        year = cmp_block.get('year')
        sn = cmp_block.get('season_number')
        total = cmp_block.get('total_seasons_per_year', 1)
        label = f"Year {year} - Season {sn} of {total}" if total and total > 1 else f"Year {year}"
        print(f"\n  {label}")
        print(f"  {'─'*66}")
        rows = []
        for metric in cmp_block.get('metrics', {}).values():
            rows.append({
                'Metric': metric['label'],
                'actual': metric['actual'],
                'baseline_ltm': metric['baseline_ltm'],
                'Δ': metric['delta'],
                'Δ%': f"{metric['pct']:+.2f}%",
                'unit': metric['unit'],
            })
        if rows:
            for line in _compact_display_frame(pd.DataFrame(rows)).to_string(index=False).splitlines():
                print(f"  {line}")
        hazard_cmp = cmp_block.get('hazard_status_comparison') or {}
        if hazard_cmp:
            print(f"\n  Hazard status shifts")
            print(f"  {'─'*66}")
            for result_key in HAZARD_PRINT_ORDER:
                if result_key not in hazard_cmp:
                    continue
                spec = _get_hazard_spec_by_result_key(result_key)
                row = hazard_cmp[result_key]
                print(
                    f"  {spec['label']:<25} "
                    f"{str(row['actual_status']).replace('_', ' '):<22} -> "
                    f"{str(row['baseline_ltm_status']).replace('_', ' ')}"
                )
    print(f"\n{'='*70}\n")

def print_hazard_results(result: Dict[str, Any]) -> None:
    # Multi-season wrapper, label each block as "Year YYYY – Season X of Y" when available
    if 'assessments' in result:
        _print_hazard_season_detection_summary(result.get('season_detection'))
        total = len(result['assessments'])
        for i, a in enumerate(result['assessments'], 1):
            print(f"\n{'─'*70}")
            season = a.get('season_info', {})
            year   = season.get('year', '')
            snum   = season.get('season_number', i)
            spyr   = season.get('total_seasons_per_year', '')
            if year and spyr and spyr > 1:
                label = f"Year {year}  –  Season {snum} of {spyr}"
            elif year:
                label = f"Year {year}"
            else:
                label = f"Assessment {i} of {total}"
            print(f"  {label}")
            print_hazard_results(a)
        if result.get('baseline_ltm'):
            _print_ltm_block(result['baseline_ltm'])
        if result.get('baseline_ltm_comparisons'):
            _print_actual_vs_ltm_comparisons(result['baseline_ltm_comparisons'])
        return

    if 'error' in result:
        print(f"\nError: {result['error']}")
        _print_hazard_season_detection_summary(result.get('season_detection'))
        if 'available_crops' in result:
            print(f"Available crops: {', '.join(result['available_crops'])}")
        return

    print(f"\n{'='*70}")
    print(f"  CROP HAZARD ASSESSMENT: {result['crop'].upper()}")
    print(f"{'='*70}")
    print(f"  Location: {result['location']['latitude']:.4f}, {result['location']['longitude']:.4f}")
    thi_context = _thi_profile_context_line(result.get('thi_profile'))
    if thi_context:
        print(f"  Livestock THI: {thi_context}")
        print(f"  THI note     : {_thi_method_line(result.get('thi_profile'))}")
    _print_hazard_season_detection_summary(result.get('season_detection'))

    season = result['season_info']
    print(f"\n  Season Information")
    print(f"  {'─'*66}")
    print(f"  Onset:  {season['onset_date']:<20} End: {season['cessation_date']}")
    print(f"  Length: {season['length_days']} days{'':15} Method: {season.get('method', 'unknown')}")
    # always display the dataset that was used
    if season.get('source'):
        print(f"  Source: {season['source']}")

    stats = result['season_statistics']

    if 'total_precipitation_mm' in stats:
        print(f"\n  Precipitation Statistics")
        print(f"  {'─'*66}")
        print(f"  {'Metric':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        print(f"  {'Total':<32} {stats['total_precipitation_mm']:>15.2f}  mm")
        print(f"  {'Daily Mean':<32} {stats['mean_daily_precipitation_mm']:>15.2f}  mm")
        print(f"  {'Daily Maximum':<32} {stats['max_daily_precipitation_mm']:>15.2f}  mm")
        print(f"  {'Rainy Days (>=1mm)':<32} {stats['rainy_days']:>15}  days")
        print(f"  {'Dry Days (<1mm)':<32} {stats['dry_days']:>15}  days")

    if 'dry_spell_statistics' in stats:
        ds = stats['dry_spell_statistics']
        print(f"\n  Dry Spell Statistics (>=7 consecutive days with <1mm rain)")
        print(f"  {'─'*66}")
        print(f"  {'Number of Dry Spells':<32} {ds['number_of_dry_spells']:>15}  spells")
        print(f"  {'Max Dry Spell Length':<32} {ds['max_dry_spell_length_days']:>15}  days")
        print(f"  {'Mean Dry Spell Length':<32} {ds['mean_dry_spell_length_days']:>15.2f}  days")

        if ds['dry_spells']:
            print(f"\n  Individual Dry Spells:")
            print(f"  {'─'*66}")
            print(f"  {'#':<4} {'Start Date':<13} {'End Date':<13} {'Length (days)':>15}")
            print(f"  {'─'*4} {'─'*13} {'─'*13} {'─'*15}")
            for i, spell in enumerate(ds['dry_spells'], 1):
                print(
                    f"  {i:<4} {_fmt_date(spell['start_date']):<13} "
                    f"{_fmt_date(spell['end_date']):<13} {spell['length_days']:>15}"
                )

        if ds.get('length_distribution'):
            print(f"\n  Length Distribution:")
            print(f"  {'─'*66}")
            for rng, cnt in sorted(ds['length_distribution'].items()):
                print(f"  {rng:<15} days: {cnt:>3} spell(s)")

    if 'mean_temperature_c' in stats:
        print(f"\n  Temperature Statistics")
        print(f"  {'─'*66}")
        print(f"  {'Metric':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        print(f"  {'Mean Temperature':<32} {stats['mean_temperature_c']:>15.2f}  deg C")
        print(f"  {'Mean Tmax':<32} {stats['mean_tmax_c']:>15.2f}  deg C")
        print(f"  {'Mean Tmin':<32} {stats['mean_tmin_c']:>15.2f}  deg C")
        print(f"  {'Max Tmax (Maximum Recorded)':<32} {stats['max_temperature_c']:>15.2f}  deg C")
        print(f"  {'Min Tmin (Minimum Recorded)':<32} {stats['min_temperature_c']:>15.2f}  deg C")

    # Hazard index counts (NTx35, NTx40, NDD, NDWS, NDWL0)
    has_counts = any(k in stats for k in ('mean_thi', 'thi_stress_days', 'NTx35', 'NTx40', 'NDWS', 'NDWL0', 'WRSI'))
    if has_counts:
        print(f"\n  Hazard Index Counts")
        print(f"  {'─'*66}")
        print(f"  {'Index':<32} {'Value':>15}  Unit")
        print(f"  {'─'*32} {'─'*15}  {'─'*10}")
        if 'WRSI' in stats:
            print(f"  {'WRSI (seasonal satisfaction)':<32} {stats['WRSI']:>15}  %")
        if 'crop_water_requirement_mm' in stats:
            print(f"  {'Crop Water Requirement':<32} {stats['crop_water_requirement_mm']:>15.2f}  mm")
        if 'actual_crop_et_mm' in stats:
            print(f"  {'Actual Crop ET':<32} {stats['actual_crop_et_mm']:>15.2f}  mm")
        if 'mean_thi' in stats:
            print(f"  {_thi_profile_label(result.get('thi_profile') or stats):<32} {stats['mean_thi']:>15.2f}  index")
        if 'max_thi' in stats:
            max_label = f"Max {_thi_profile_label(result.get('thi_profile') or stats)}"
            print(f"  {max_label:<32} {stats['max_thi']:>15.2f}  index")
        if 'thi_stress_days' in stats:
            print(f"  {'THI stress days':<32} {stats['thi_stress_days']:>15}  days")
        if 'NTx35' in stats:
            print(f"  {'NTx35 (days Tmax > 35C)':<32} {stats['NTx35']:>15}  days")
        if 'NTx40' in stats:
            print(f"  {'NTx40 (days Tmax > 40C)':<32} {stats['NTx40']:>15}  days")
        if 'NDD' in stats:
            print(f"  {'NDD (dry days, <1mm)':<32} {stats['NDD']:>15}  days")
        if 'NDWS' in stats:
            print(f"  {'NDWS (water-stress days)':<32} {stats['NDWS']:>15}  days")
        if 'NDWL0' in stats:
            print(f"  {'NDWL0 (water-logging days)':<32} {stats['NDWL0']:>15}  days")
        if 'NDWS' in stats or 'NDWL0' in stats:
            print("  Note: NDWS/NDWL0 come from the crop water-balance model, not a raw precip-minus-ET0 count.")
            methodology = result.get("water_balance_methodology") or {}
            count_window = methodology.get("count_window") or {}
            if count_window.get("applied_mode") == CROP_ACTIVE_WATER_BALANCE:
                print("  Count window: crop-active ETO sub-season(s) inside fixed window.")
            elif season.get('method') == 'fixed_season':
                print("  Caution: fixed-season windows can bias counts if they include non-growing shoulder months.")

    hazards = result['hazard_evaluation']
    print(f"\n  Hazard Assessment")
    print(f"  {'─'*66}")
    print(f"  {'Indicator':<25} {'Value':>18}  Status")
    print(f"  {'─'*25} {'─'*18}  {'─'*20}")
    if 'precipitation' in hazards:
        p   = hazards['precipitation']
        sym = _hazard_status_symbol(p['status'])
        print(f"  {'Precipitation':<25} {p['value_mm']:>16.2f} mm  [{sym}] {p['status'].replace('_', ' ').upper()}")
    if 'temperature' in hazards:
        t   = hazards['temperature']
        sym = _hazard_status_symbol(t['status'])
        print(f"  {'Temperature':<25} {t['value_c']:>16.2f} degC [{sym}] {t['status'].replace('_', ' ').upper()}")
    for hazard_key in ('THI', 'NDD', 'NTx35', 'NTx40', 'NDWS', 'NDWL0'):
        if hazard_key not in hazards:
            continue
        spec = _get_hazard_spec_by_result_key(hazard_key)
        item = hazards[hazard_key]
        sym = _hazard_status_symbol(item['status'])
        print(
            f"  {spec['label']:<25} {item[spec['value_key']]:>16.2f} {spec['unit']:<6} "
            f"[{sym}] {item['status'].replace('_', ' ').upper()}"
        )

    print(f"\n{'='*70}\n")

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Calculate crop hazard indices',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        'crop', type=str,
        help=f"Crop name with hazard thresholds. Available: {' | '.join(threshold_supported_crop_names())}",
    )
    parser.add_argument('--location',  type=str, required=True,
                        help='Coordinates as "lat,lon"  e.g. "-1.286,36.817"')
    parser.add_argument('--date-from', type=str, required=True,
                        help='Analysis start date (YYYY-MM-DD)')
    parser.add_argument('--date-to',   type=str, required=True,
                        help='Analysis end date   (YYYY-MM-DD)')

    # season specification (mutually exclusive) 
    season_group = parser.add_mutually_exclusive_group()
    season_group.add_argument(
        '--season-start', type=str, default=None,
        help='Explicit season start (YYYY-MM-DD). Pair with --season-end.',
    )
    season_group.add_argument(
        '--fixed-season',
        type=str, default=None,
        metavar='MM-DD:MM-DD[,MM-DD:MM-DD]',
        help=(
            "Fixed calendar season window(s) applied to every year in the date range.\n"
            "Mirrors --fixed-season in seasons.py.\n\n"
            "Format : one or two 'onset:cessation' tokens as MM-DD:MM-DD,\n"
            "         comma-separated for two seasons per year.\n\n"
            "Examples:\n"
            "  Single season  : --fixed-season '03-01:06-30'\n"
            "  Two seasons    : --fixed-season '03-01:05-31,10-01:12-15'\n"
            "  Year-crossing  : --fixed-season '11-01:02-28'\n"
        ),
    )
    parser.add_argument('--season-end', type=str, default=None,
                        help='Explicit season end (YYYY-MM-DD). Pair with --season-start.')
    parser.add_argument(
        '--source',
        choices=['era_5', 'agera_5', 'chirps+chirts', 'chirps_v2+chirts', 'chirps_v3_daily_rnl', 'imerg', 'tamsat', 'paired', 'auto'],
        default='auto',
        help=(
            "Climate data source (default: auto).\n"
            "  agera_5       -- AgERA5 / ERA5-Land\n"
            "  era_5         -- ERA5 reanalysis\n"
            "  chirps_v2+chirts -- CHIRPS v2 precipitation + CHIRTS temperature\n"
            "  chirps_v3_daily_rnl -- precipitation-only; use via paired or auto\n"
            "  imerg         -- precipitation-only; use via paired\n"
            "  tamsat        -- precipitation-only; use via paired\n"
            "  paired        -- explicit precip+temp pairing via --precip-source and --temp-source\n"
            "  auto          -- tries chirps_v3_daily_rnl + agera_5 -> agera_5 -> era_5 -> chirps_v2+chirts\n"
            "Default historical daily path: chirps_v3_daily_rnl + agera_5.\n"
            "Recommended direct single-source fallback: agera_5.\n"
            "Note: auto-detection (no --season-* flag) now honors this source\n"
            "      setting instead of forcing chirps_v2+chirts."
        ),
    )
    parser.add_argument(
        '--precip-source',
        default=None,
        help='Required with --source paired. Example: chirps_v3_daily_rnl, imerg, or tamsat.',
    )
    parser.add_argument(
        '--temp-source',
        default=None,
        help='Required with --source paired. Example: agera_5 or era_5.',
    )
    parser.add_argument(
        '--project-id',
        default=None,
        help='Optional Earth Engine / GCP project ID for GEE-backed climate sources.',
    )
    parser.add_argument(
        '--calendar-source',
        choices=['ggcmi'],
        default=None,
        help='Optional crop-calendar preset source to use if auto season detection is not reliable.',
    )
    parser.add_argument(
        '--calendar-system',
        choices=list(CALENDAR_SYSTEM_CHOICES),
        default='rf',
        help='Crop-calendar system when --calendar-source is used.',
    )
    parser.add_argument(
        '--livestock-type',
        choices=list_thi_livestock_profiles(),
        default=DEFAULT_LIVESTOCK_TYPE,
        help='Livestock THI profile (default: cattle_dairy).',
    )
    parser.add_argument(
        '--livestock-climate-profile',
        choices=['auto', 'temperate', 'tropical'],
        default=DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
        help='THI climate context. auto uses latitude plus highland elevation when available.',
    )
    parser.add_argument(
        '--livestock-elevation-override-m',
        '--livestock-elevation-m',
        dest='livestock_elevation_override_m',
        type=float,
        default=None,
        help='Optional site elevation override, meters above sea level, for THI climate-context selection.',
    )
    parser.add_argument('--gap-days',        type=int, default=30,
                        help='Dry-day gap used to end auto-detected season (default: 30)')
    parser.add_argument('--min-season-days', type=int, default=30,
                        help='Minimum season length for auto-detection (default: 30)')
    parser.add_argument('--soilcp',  type=float, default=DEFAULT_SOILCP,
                        help=f'Soil available water capacity at field capacity, mm '
                             f'(water-balance NDWS/NDWL0; default: {DEFAULT_SOILCP})')
    parser.add_argument('--soilsat', type=float, default=DEFAULT_SOILSAT,
                        help=f'Extra soil water from field capacity to saturation, mm '
                             f'(water-balance NDWL0; default: {DEFAULT_SOILSAT})')
    parser.add_argument(
        '--water-balance-window',
        choices=list(WATER_BALANCE_WINDOW_CHOICES),
        default=FULL_WINDOW_WATER_BALANCE,
        help=(
            "How to count NDWS/NDWL0 within fixed-season runs.\n"
            "  full_window  -- use full fixed window [default]\n"
            "  crop_active  -- use detected ETO sub-season(s) inside fixed window when available\n"
        ),
    )
    parser.add_argument(
        '--workers', type=int, default=1,
        help='Bounded historical GEE/Xee worker count for chunked fetches.',
    )
    parser.add_argument('--format',          choices=['json', 'text'], default='text',
                        help='Output format (default: text)')
    parser.add_argument('--thresholds-file', type=str, default=None,
                        help=('Optional JSON file overriding threshold bands by metric name. '
                              'Metrics omitted from file keep package defaults.'))
    parser.add_argument('--output',          type=str, default=None,
                        help='Save JSON result to this file path')
    args = parser.parse_args()

    # Validate explicit-season pair
    if bool(args.season_start) != bool(args.season_end):
        parser.error('--season-start and --season-end must be supplied together.')

    lat, lon = map(float, args.location.split(','))

    custom_thresholds = load_custom_thresholds_file(args.thresholds_file)

    calculate_kwargs = {
        'crop_name': args.crop,
        'location_coord': (lat, lon),
        'date_from': args.date_from,
        'date_to': args.date_to,
        'season_start': args.season_start,
        'season_end': args.season_end,
        'fixed_season': args.fixed_season,
        'source': args.source,
        'precip_source': args.precip_source,
        'temp_source': args.temp_source,
        'ee_project_id': args.project_id,
        'custom_thresholds': custom_thresholds,
        'gap_days': args.gap_days,
        'min_season_days': args.min_season_days,
        'soilcp': args.soilcp,
        'soilsat': args.soilsat,
        'water_balance_window': args.water_balance_window,
        'workers': args.workers,
        'calendar_source': args.calendar_source,
        'calendar_system': args.calendar_system,
        'livestock_type': args.livestock_type,
        'livestock_climate_profile': args.livestock_climate_profile,
        'livestock_elevation_override_m': args.livestock_elevation_override_m,
    }
    if args.format == 'json':
        with redirect_stdout(sys.stderr):
            result = calculate_hazards(**calculate_kwargs)
    else:
        result = calculate_hazards(**calculate_kwargs)
    if args.format == 'json':
        output_str = json.dumps(result, indent=2, default=str)
        print(output_str)
        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
            with open(args.output, 'w') as f:
                f.write(output_str)
    else:
        print_hazard_results(result)
        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
            with open(args.output, 'w') as f:
                f.write(json.dumps(result, indent=2, default=str))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())

# Auto-detect season (no season flag supplied -- uses requested source policy):
# python -m climate_tookit.calculate_hazards.hazards maize --location="-1.286,36.817" --date-from 2016-01-01 --date-to 2016-12-31 --season-start 2016-03-01 --season-end 2016-06-30

# Fixed single season:
# python -m climate_tookit.calculate_hazards.hazards maize --location="-1.286,36.817" --date-from 2018-01-01 --date-to 2022-12-31 --fixed-season "03-01:06-30" --source era_5

# Fixed two seasons:
# python -m climate_tookit.calculate_hazards.hazards beans --location="-1.286,36.817" --date-from 2018-01-01 --date-to 2022-12-31 --fixed-season "03-01:05-31,10-01:12-15" --source agera_5

# Fixed year-crossing season:
# python -m climate_tookit.calculate_hazards.hazards sorghum --location="-1.286,36.817" --date-from 2012-01-01 --date-to 2016-12-31 --fixed-season "11-01:02-28" --source chirps_v2+chirts

# Explicit season dates (single season):
# python -m climate_tookit.calculate_hazards.hazards maize --location="-1.286,36.817" --date-from 2020-01-01 --date-to 2020-12-31 --season-start 2020-03-01 --season-end 2020-06-30

# JSON output to file:
# python -m climate_tookit.calculate_hazards.hazards rice --location="-1.286,36.817" --date-from 2019-01-01 --date-to 2021-12-31 --fixed-season "04-15:07-10" --source auto --format json --output results.json
