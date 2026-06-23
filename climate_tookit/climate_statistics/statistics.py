"""
Climate Statistics Module
Computes agroecology-focused climate statistics by season.
Supports both automatic detection (ETO-based, from seasons.py) and fixed-season calendar windows (--fixed-season), matching the season_analysis interface.
Outputs three views per run, all sliced per detected/fixed season (no full-period summaries):
    1. Raw Climate Summary by Season -- mean / min / max / std per core variable (precip, tmax, tmin, humidity, solar, wind), one block per season
    2. Overall Statistics by Season  -- essential agro metrics, one block per season
    3. Season Statistics             -- compact agro headline per season (plus ETO sub-seasons inside fixed windows)
Detection: delegates to seasons.py building blocks (add_et0, detect_onset_cessation, reassign_spillover_seasons, remove_duplicate_seasons,
parse_fixed_seasons, check_humid) so behaviour is identical to seasons.py:
    Per reference year, a 1.5-year window is sliced from the master DataFrame so seasons crossing the year boundary are captured. After detection,
    seasons are reassigned to onset year, filtered to MAM/OND windows for equatorial climates, and de-duplicated.
Data sources accepted: agera_5, era_5, nasa_power, nex_gddp, auto, paired, and legacy chirps_v2+chirts / chirps_v2 paths. Legacy alias `chirps` still works. Precipitation-only sources such as chirps_v3_daily_rnl, imerg, and tamsat should be used through paired mode with a temperature partner. NEX-GDDP requires --model and --scenario. Default historical daily path uses CHIRPS v3 Daily RNL precipitation plus AgERA5 companion variables.

Dependencies: pandas, numpy, climate_toolkit (preprocess_data, seasons.py)
"""

import os
import sys
import math
import json
import argparse
import shutil
from datetime import datetime, date
from pathlib import Path
from time import perf_counter
from typing import Tuple, Dict, List, Any, Optional

import pandas as pd
from climate_tookit.season_analysis.season_identity import build_season_identity
import numpy as np

from climate_tookit.fetch_data.runtime_notes import build_historical_cache_note
from climate_tookit.crop_calendar.ggcmi import (
    CALENDAR_SYSTEM_CHOICES,
    resolve_calendar_preset,
)
from climate_tookit.fetch_data.source_data.sources.nex_gddp import _validate_period_against_scenario
from climate_tookit.climatology import (
    DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    DEFAULT_LIVESTOCK_TYPE,
    compute_daily_thi,
    compute_monthly_spei,
    compute_monthly_spi,
    list_thi_livestock_profiles,
    resolve_thi_profile,
)
try:
    from climate_tookit.fetch_data.preprocess_data.preprocess_data import preprocess_data
    PREPROCESS_AVAILABLE = True
except Exception:
    preprocess_data = None
    PREPROCESS_AVAILABLE = False
from climate_tookit.weather_station.overrides import apply_custom_station_overrides
from climate_tookit.fetch_data.source_data.sources.utils.models import (
    ClimateVariable,
    normalize_climate_dataset_name,
)
from climate_tookit.season_analysis.seasons import (
    add_et0,
    parse_fixed_seasons,
    detect_onset_cessation,
    reassign_spillover_seasons,
    remove_duplicate_seasons,
    check_humid,
)
from climate_tookit.calculate_hazards.hazards import (
    DEFAULT_KC_PARAMS as HAZARD_DEFAULT_KC_PARAMS,
    DEFAULT_SOILCP as HAZARD_DEFAULT_SOILCP,
    DEFAULT_SOILSAT as HAZARD_DEFAULT_SOILSAT,
    FULL_WINDOW_WATER_BALANCE as HAZARD_FULL_WINDOW_WATER_BALANCE,
    build_water_balance_methodology as shared_build_water_balance_methodology,
    calc_water_balance as shared_calc_water_balance,
    summarize_water_balance as shared_summarize_water_balance,
)

CLIMATE_VARS = [
    ClimateVariable.precipitation,
    ClimateVariable.max_temperature,
    ClimateVariable.min_temperature,
    ClimateVariable.humidity,
    ClimateVariable.soil_moisture,
    ClimateVariable.solar_radiation,
    ClimateVariable.wind_speed,
]

# Constants
RENAME_MAP = {
    'precipitation':    'precip',
    'max_temperature':  'tmax',
    'min_temperature':  'tmin',
}

# Variables shown in the Raw Climate Summary table
SUMMARY_VARS: List[Tuple[str, str]] = [
    ('precip',          'Precipitation (mm/day)'),
    ('tmax',            'Max Temperature (°C)'),
    ('tmin',            'Min Temperature (°C)'),
    ('humidity',        'Humidity (%)'),
    ('solar_radiation', 'Solar Radiation (W/m²)'),
    ('wind_speed',      'Wind Speed (m/s)'),
]

# LTM (Long-Term Mean) coverage rules
BASELINE_DEFAULT_PERIOD: Tuple[int, int] = (1991, 2020)
MIN_LTM_YEARS:           int            = 20
CHIRTS_LAST_YEAR:        int            = 2016
PRECIP_ONLY_SOURCES = {'chirps', 'chirps_v2', 'chirps_v3_daily_rnl', 'imerg', 'tamsat'}
TEMP_ONLY_SOURCES = {'chirts'}
PAIRED_SOURCE_SENTINEL = 'paired'
DEFAULT_AUTO_PRECIP_SOURCE = 'chirps_v3_daily_rnl'
DEFAULT_AUTO_TEMP_SOURCE = 'agera_5'


def _validate_nex_ltm_period(
    source: str,
    start_year: int,
    end_year: int,
) -> Optional[str]:
    """NEX-GDDP LTM summaries should use multi-year windows."""
    if source != 'nex_gddp':
        return None
    years_span = end_year - start_year + 1
    if years_span < 2:
        return (
            "NEX-GDDP LTM/statistics analysis requires a multi-year period. "
            f"Got {start_year}-{end_year} ({years_span} year(s)). "
            "Single-year NEX-GDDP future/baseline summary runs are not allowed here."
        )
    return None


def _validate_nex_requested_period(
    source: str,
    start_year: int,
    end_year: int,
    scenario: Optional[str],
) -> Optional[str]:
    if source != "nex_gddp" or not scenario or _validate_period_against_scenario is None:
        return None
    try:
        _validate_period_against_scenario(
            str(scenario),
            date(start_year, 1, 1),
            date(end_year, 12, 31),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _validate_source_compatibility(
    source: str,
    start_year: int,
    end_year: int,
) -> Optional[str]:
    source_lc = source.lower()
    if source_lc == 'terraclimate':
        return (
            "terraclimate is monthly-cadence, but climate_statistics.statistics "
            "requires daily data for ET0, water balance, and season windows."
        )
    if source_lc == 'chirts':
        return (
            "chirts provides temperature only and is not supported in the current "
            "single-source interface for precipitation-driven season statistics. "
            "Use a paired precip+temp workflow or another full daily source."
        )
    if source_lc == 'imerg':
        return (
            "imerg provides precipitation only and is not supported in the current "
            "single-source interface. climate_statistics.statistics currently "
            "requires temperature inputs for ET0 and season analysis, so imerg "
            "needs an explicit temperature partner."
        )
    if source_lc == 'tamsat':
        return (
            "tamsat provides precipitation and soil moisture, but not temperature. "
            "climate_statistics.statistics requires temperature inputs for ET0 and "
            "season analysis, so tamsat must be paired with a temperature source "
            "such as agera_5 or era_5."
        )
    if source_lc == 'chirps_v3_daily_rnl':
        return (
            "chirps_v3_daily_rnl provides precipitation only and is not supported "
            "in the current single-source interface. Use --source auto for the "
            "default CHIRPS v3 Daily RNL + AgERA5 path, or use paired sources "
            "explicitly."
        )
    if source_lc in {'chirps+chirts', 'chirps_v2+chirts'} and end_year > CHIRTS_LAST_YEAR:
        return (
            "chirps_v2+chirts is unavailable for this window because CHIRTS daily "
            f"coverage ends in {CHIRTS_LAST_YEAR}. Use agera_5, era_5, "
            "nasa_power, chirps_v2, or nex_gddp for later periods."
        )
    return None


def _validate_paired_sources(
    precip_source: Optional[str],
    temp_source: Optional[str],
    start_year: int,
    end_year: int,
) -> Optional[str]:
    precip_lc = normalize_climate_dataset_name(precip_source)
    temp_lc = normalize_climate_dataset_name(temp_source)
    if bool(precip_lc) != bool(temp_lc):
        return "Provide both precip_source and temp_source together."
    if not precip_lc and not temp_lc:
        return None
    if precip_lc in TEMP_ONLY_SOURCES:
        return f"precip_source '{precip_source}' is temperature-only."
    if temp_lc in PRECIP_ONLY_SOURCES:
        return f"temp_source '{temp_source}' is precipitation-only."
    if temp_lc == 'chirts' and end_year > CHIRTS_LAST_YEAR:
        return (
            "Temperature partner chirts is unavailable for this window because "
            f"CHIRTS daily coverage ends in {CHIRTS_LAST_YEAR}."
        )
    return None

# Data fetching
def _call_preprocess(
    source,
    lat,
    lon,
    date_from,
    date_to,
    model,
    scenario,
    ee_project_id=None,
):
    """Single preprocess_data call -- isolates the kwargs handling."""
    return preprocess_data(
        source=source,
        location_coord=(lat, lon),
        variables=CLIMATE_VARS,
        date_from=date_from,
        date_to=date_to,
        model=model,
        scenario=scenario,
        ee_project_id=ee_project_id,
    )

def _fetch_chirps_chirts(lat, lon, date_from, date_to, ee_project_id=None):
    """Merge CHIRPS (precip) + CHIRTS (temp). Other vars unavailable."""
    df_p = _call_preprocess(
        'chirps_v2', lat, lon, date_from, date_to, None, None, ee_project_id
    )
    df_t = _call_preprocess(
        'chirts', lat, lon, date_from, date_to, None, None, ee_project_id
    )
    if df_p is None or df_p.empty:
        raise RuntimeError("CHIRPS returned no data")
    if df_t is None or df_t.empty:
        raise RuntimeError("CHIRTS returned no data")
    return pd.merge(df_p, df_t, on='date', how='inner')


def _fetch_paired_sources(
    lat,
    lon,
    date_from,
    date_to,
    precip_source,
    temp_source,
    *,
    model=None,
    scenario=None,
    ee_project_id=None,
):
    precip_lc = normalize_climate_dataset_name(precip_source)
    temp_lc = normalize_climate_dataset_name(temp_source)
    precip_df = _call_preprocess(
        precip_lc,
        lat,
        lon,
        date_from,
        date_to,
        model if precip_lc == 'nex_gddp' else None,
        scenario if precip_lc == 'nex_gddp' else None,
        ee_project_id,
    )
    temp_df = _call_preprocess(
        temp_lc,
        lat,
        lon,
        date_from,
        date_to,
        model if temp_lc == 'nex_gddp' else None,
        scenario if temp_lc == 'nex_gddp' else None,
        ee_project_id,
    )
    if precip_df is None or precip_df.empty or 'date' not in precip_df.columns:
        raise RuntimeError(f"No precipitation data returned from source '{precip_source}'")
    if temp_df is None or temp_df.empty or 'date' not in temp_df.columns:
        raise RuntimeError(f"No temperature data returned from source '{temp_source}'")

    temp_columns = [
        column for column in temp_df.columns
        if column == 'date' or column != 'precipitation'
    ]
    merged = pd.merge(
        precip_df[['date', 'precipitation']],
        temp_df[temp_columns],
        on='date',
        how='inner',
    )
    if merged.empty:
        raise RuntimeError(
            f"No overlapping daily records between precip_source='{precip_source}' "
            f"and temp_source='{temp_source}'."
        )
    return merged


def _fetch_auto(lat, lon, date_from, date_to, ee_project_id=None):
    """
    Default historical path:
    try CHIRPS v3 Daily RNL precipitation + AgERA5 companion variables first,
    then AgERA5 alone, then ERA5, then legacy CHIRPS v2 + CHIRTS fallback.
    """
    try:
        return _fetch_paired_sources(
            lat,
            lon,
            date_from,
            date_to,
            DEFAULT_AUTO_PRECIP_SOURCE,
            DEFAULT_AUTO_TEMP_SOURCE,
            ee_project_id=ee_project_id,
        )
    except Exception:
        pass

    for candidate in (DEFAULT_AUTO_TEMP_SOURCE, 'era_5'):
        try:
            return _call_preprocess(
                candidate,
                lat,
                lon,
                date_from,
                date_to,
                None,
                None,
                ee_project_id,
            )
        except Exception:
            continue

    if date_to.year > CHIRTS_LAST_YEAR:
        raise RuntimeError(
            "auto fallback exhausted default CHIRPS v3 Daily RNL + AgERA5 pair, "
            "AgERA5, and ERA5, and legacy chirps_v2+chirts is unavailable after "
            f"{CHIRTS_LAST_YEAR} because CHIRTS daily coverage ends there."
        )
    return _fetch_chirps_chirts(lat, lon, date_from, date_to, ee_project_id)


def _apply_custom_station_overrides(
    base_df: pd.DataFrame,
    *,
    lat: float,
    lon: float,
    date_from: date,
    date_to: date,
    custom_station_file: str | None,
    custom_station_variables: Optional[List[str]] = None,
    custom_station_name: Optional[str] = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
) -> pd.DataFrame:
    if not custom_station_file:
        return base_df
    return apply_custom_station_overrides(
        base_df,
        lat=lat,
        lon=lon,
        date_from=date_from,
        date_to=date_to,
        custom_station_file=custom_station_file,
        custom_station_variables=custom_station_variables,
        custom_station_name=custom_station_name,
        custom_temp_unit=custom_temp_unit,
        custom_precip_unit=custom_precip_unit,
        rename_map=RENAME_MAP,
        stage="preprocessed",
    )

def get_climate_data(
    lat: float, lon: float,
    start_date: str, end_date: str,
    source: str,
    model:    Optional[str] = None,
    scenario: Optional[str] = None,
    precip_source: Optional[str] = None,
    temp_source: Optional[str] = None,
    verbose: bool = False,
    custom_station_file: Optional[str] = None,
    custom_station_variables: Optional[List[str]] = None,
    custom_station_name: Optional[str] = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    ee_project_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch all variables for [start_date, end_date] from the given source.
    Source handling
    ---------------
      - 'auto'              : tries chirps_v3_daily_rnl + agera_5, then agera_5, then era_5, then chirps_v2+chirts fallback
      - 'paired'            : merges explicit precip_source + temp_source
      - 'chirps_v2+chirts'  : merges CHIRPS v2 precip + CHIRTS temperature
      - any other string    : passed straight to preprocess_data (agera_5, era_5, nasa_power, nex_gddp, chirps_v2, chirts, …)
    Recommendation
    --------------
      - Default historical daily path uses `chirps_v3_daily_rnl` + `agera_5`.
      - For direct single-source historical daily runs, prefer `agera_5`.
    Renames pipeline columns to canonical names: precip, tmax, tmin (humidity, soil_moisture, solar_radiation, wind_speed pass through when the source provides them).
    """
    date_from = date.fromisoformat(start_date)
    date_to   = date.fromisoformat(end_date)
    source_lc = normalize_climate_dataset_name(source)
    precip_lc = normalize_climate_dataset_name(precip_source)
    temp_lc = normalize_climate_dataset_name(temp_source)

    # Resolve source -> raw DataFrame
    if precip_lc and temp_lc:
        if verbose:
            print(f"  [source] paired precip={precip_lc} + temp={temp_lc}")
        df = _fetch_paired_sources(
            lat,
            lon,
            date_from,
            date_to,
            precip_lc,
            temp_lc,
            model=model,
            scenario=scenario,
            ee_project_id=ee_project_id,
        )
    elif source_lc == 'auto':
        if verbose:
            print("  [source] auto -> chirps_v3_daily_rnl + agera_5 -> agera_5 -> era_5 -> chirps_v2+chirts")
        df = _fetch_auto(lat, lon, date_from, date_to, ee_project_id)
    elif source_lc in {'chirps+chirts', 'chirps_v2+chirts'}:
        if verbose:
            print("  [source] CHIRPS v2 + CHIRTS")
        df = _fetch_chirps_chirts(lat, lon, date_from, date_to, ee_project_id)
    else:
        df = _call_preprocess(
            source_lc,
            lat,
            lon,
            date_from,
            date_to,
            model,
            scenario,
            ee_project_id,
        )

    if df is None or df.empty:
        raise RuntimeError(f"No data returned from source '{source}'")

    df = df.rename(columns=RENAME_MAP).copy()
    df['date'] = pd.to_datetime(df['date'])
    df = _apply_custom_station_overrides(
        df,
        lat=lat,
        lon=lon,
        date_from=date_from,
        date_to=date_to,
        custom_station_file=custom_station_file,
        custom_station_variables=custom_station_variables,
        custom_station_name=custom_station_name,
        custom_temp_unit=custom_temp_unit,
        custom_precip_unit=custom_precip_unit,
    )
    for row in df.attrs.get("custom_station_override_summary", []):
        print(
            "  [station] "
            f"{row.get('variable')}: custom_days={row.get('override_days', 0)}/"
            f"{row.get('total_days', 0)} | "
            f"gridded_fallback_days={row.get('fallback_days', 0)} | "
            f"status={row.get('status', 'unknown')}"
        )
    for warning in df.attrs.get("custom_station_warnings", []):
        print(f"  [WARN] {warning}")

    # Minimum required for ET0 + water balance
    if 'precip' not in df.columns:
        print(f"  [WARN] No precipitation column from {source}; defaulting to 0")
        df['precip'] = 0.0
    elif df['precip'].notna().sum() == 0:
        source_label = source
        if precip_lc and temp_lc:
            source_label = f"paired precip={precip_lc} temp={temp_lc}"
        raise RuntimeError(
            "Precipitation fetch returned no usable daily values "
            f"for {source_label} over {start_date}..{end_date}. "
            "Abort analysis instead of treating missing rainfall as zero."
        )
    if 'tmax' not in df.columns or 'tmin' not in df.columns:
        if source_lc == 'chirps_v2':
            print("  [WARN] CHIRPS v2 provides precipitation only -- defaulting tmax=25, tmin=15")
            df['tmax'] = 25.0
            df['tmin'] = 15.0
        else:
            available = [c for c in df.columns if c != 'date']
            raise RuntimeError(
                f"Temperature missing from '{source}'. Got: {available}"
            )
    return df.sort_values('date').reset_index(drop=True)

# Water balance
def calculate_water_balance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Daily water balance:
      water_balance      = precip - ET0
      cumulative_balance = running sum
      water_stress       = water_balance < 0  (boolean)
    Requires column 'ET0_mm_day' (added via seasons.add_et0).
    """
    df = df.copy()
    df['water_balance']      = df['precip'].fillna(0) - df['ET0_mm_day'].fillna(0)
    df['cumulative_balance'] = df['water_balance'].cumsum()
    df['water_stress']       = df['water_balance'] < 0
    return df


def _shared_water_balance_summary(
    df: pd.DataFrame,
    *,
    analysis_start: Optional[str] = None,
    analysis_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Shared root-zone diagnostics from calculate_hazards.hazards.

    Keep legacy precip-minus-ET0 totals for continuity, but source NDWS/NDWL0/WRSI
    from the same running soil-water balance used by hazards/ensemble_hazards.
    """
    if df is None or df.empty:
        return {}
    if 'ET0_mm_day' not in df.columns:
        return {}
    if not any(col in df.columns for col in ('precip', 'precipitation', 'total_precipitation')):
        return {}

    working_df = df
    if analysis_end and 'date' in df.columns:
        end_ts = pd.Timestamp(analysis_end)
        trimmed = df.loc[df['date'] <= end_ts]
        if not trimmed.empty:
            working_df = trimmed

    params = dict(HAZARD_DEFAULT_KC_PARAMS)
    wb = shared_calc_water_balance(
        working_df,
        soilcp=HAZARD_DEFAULT_SOILCP,
        soilsat=HAZARD_DEFAULT_SOILSAT,
        kc=float(params.get('kc_mid', 1.0)),
        kc_init=params.get('kc_init'),
        kc_mid=params.get('kc_mid'),
        kc_end=params.get('kc_end'),
        depletion_fraction_p=float(params.get('depletion_fraction_p', 0.5)),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
    )
    if wb is None or wb.empty:
        return {}

    if analysis_start or analysis_end:
        mask = pd.Series(True, index=wb.index)
        if analysis_start:
            mask &= wb['date'] >= pd.Timestamp(analysis_start)
        if analysis_end:
            mask &= wb['date'] <= pd.Timestamp(analysis_end)
        wb = wb.loc[mask]
        if wb.empty:
            return {}

    summary = shared_summarize_water_balance(wb)
    if not summary:
        return {}

    rounded: Dict[str, Any] = {}
    for key, value in summary.items():
        if key in {'NDWS', 'NDWL0'}:
            rounded[key] = int(value)
        elif key == 'WRSI':
            rounded[key] = _r(value, 2)
        elif key in {'crop_water_requirement_mm', 'actual_crop_et_mm', 'runoff_mm'}:
            rounded[key] = _r(value, 1)
        else:
            rounded[key] = _r(value, 2)
    return rounded

# Statistics
def _r(value, n=2):
    """Round but preserve None for missing data."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), n)


def _slice_date_window(
    df: pd.DataFrame,
    onset_ts: pd.Timestamp,
    cess_ts: pd.Timestamp,
) -> pd.DataFrame:
    return df[(df['date'] >= onset_ts) & (df['date'] <= cess_ts)]


def _thi_profile_label(profile: Optional[Dict[str, Any]]) -> str:
    if not profile:
        return "Livestock THI"
    label = (
        profile.get("label")
        or profile.get("livestock_label")
        or profile.get("livestock_type")
        or "Livestock THI"
    )
    climate = profile.get("climate_profile_applied") or profile.get("climate_profile")
    if climate:
        return f"Livestock THI ({label}; {climate})"
    return f"Livestock THI ({label})"


def _livestock_heat_stress_summary(
    df: pd.DataFrame,
    *,
    thi_profile: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Summarize livestock THI when humidity-backed inputs are available."""
    if df is None or df.empty or 'date' not in df.columns or 'humidity' not in df.columns:
        return None

    thi_input = df.copy()
    for col in ('tmax', 'tmin'):
        if col in thi_input.columns:
            series = pd.to_numeric(thi_input[col], errors='coerce')
            if series.dropna().mean() > 100:
                thi_input[col] = series - 273.15
            else:
                thi_input[col] = series

    try:
        thi_df = compute_daily_thi(
            thi_input,
            date_col='date',
            humidity_col='humidity',
            thresholds=(thi_profile or {}).get('thresholds'),
            livestock_type=(thi_profile or {}).get('livestock_type', DEFAULT_LIVESTOCK_TYPE),
            climate_profile=(thi_profile or {}).get('climate_profile_applied', DEFAULT_LIVESTOCK_CLIMATE_PROFILE),
            elevation_m=(thi_profile or {}).get('elevation_m'),
        )
    except ValueError:
        return None

    if 'thi' not in thi_df.columns or thi_df['thi'].notna().sum() == 0:
        return None

    counts = thi_df['thi_class'].value_counts(dropna=True)
    return {
        'livestock_type': (thi_profile or {}).get('livestock_type', DEFAULT_LIVESTOCK_TYPE),
        'livestock_label': (thi_profile or {}).get('label', 'Cattle (dairy)'),
        'climate_profile': (thi_profile or {}).get('climate_profile_applied', DEFAULT_LIVESTOCK_CLIMATE_PROFILE),
        'mean_thi': _r(thi_df['thi'].mean(), 2),
        'max_thi': _r(thi_df['thi'].max(), 2),
        'days_total': int(thi_df['thi'].notna().sum()),
        'days_none': int(counts.get('none', 0)),
        'days_mild': int(counts.get('mild', 0)),
        'days_moderate': int(counts.get('moderate', 0)),
        'days_severe': int(counts.get('severe', 0)),
        'days_stress': int(
            counts.get('mild', 0)
            + counts.get('moderate', 0)
            + counts.get('severe', 0)
        ),
    }

def raw_climate_summary(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Compact summary table -- mean / min / max / std per core variable.
    Missing variables (e.g. humidity not in CHIRPS) appear as None.
    """
    rows: List[Dict[str, Any]] = []
    for col, label in SUMMARY_VARS:
        if col not in df.columns:
            rows.append({'Variable': label,
                         'Mean': None, 'Min': None, 'Max': None, 'Std': None})
            continue
        s = df[col].dropna()
        if s.empty:
            rows.append({'Variable': label,
                         'Mean': None, 'Min': None, 'Max': None, 'Std': None})
            continue
        rows.append({
            'Variable': label,
            'Mean': _r(s.mean(), 3),
            'Min':  _r(s.min(),  3),
            'Max':  _r(s.max(),  3),
            'Std':  _r(s.std(),  3),
        })
    return rows

def overall_statistics(
    df: pd.DataFrame,
    *,
    full_df: Optional[pd.DataFrame] = None,
    analysis_start: Optional[str] = None,
    analysis_end: Optional[str] = None,
    shared_water_balance_summary: Optional[Dict[str, Any]] = None,
    thi_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Essential agro metrics for the full period.
    Filtered to remove noisy daily means/medians/stds and duplicate metrics (per the agroecology-priority spec).
    """
    p   = df['precip'].fillna(0)
    tx  = df['tmax']
    tn  = df['tmin']
    et0 = df['ET0_mm_day'].fillna(0)
    wb  = df['water_balance']
    shared_wb = (
        dict(shared_water_balance_summary)
        if isinstance(shared_water_balance_summary, dict)
        else _shared_water_balance_summary(
            full_df if full_df is not None else df,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
        )
    )

    water_balance_stats = {
        'total_balance': _r(wb.sum(), 1),
        'deficit_days':  int((wb < 0).sum()),
        'surplus_days':  int((wb > 0).sum()),
        'max_deficit':   _r(wb.min()),
        'max_surplus':   _r(wb.max()),
    }
    water_balance_stats.update(shared_wb)
    heat_stress = _livestock_heat_stress_summary(df, thi_profile=thi_profile)

    result = {
        'total_days': int(len(df)),
        'precipitation': {
            'total_mm':   _r(p.sum(),  1),
            'rainy_days': int((p >= 1.0).sum()),
            'dry_days':   int((p <  1.0).sum()),
            'max_daily':  _r(p.max(), 2),
        },
        'temperature': {
            'mean_tmax':  _r(tx.mean()),
            'mean_tmin':  _r(tn.mean()),
            'mean_tavg':  _r(((tx + tn) / 2).mean()),
            'max_tmax':   _r(tx.max()),
            'min_tmin':   _r(tn.min()),
        },
        'et0': {
            'total_mm':   _r(et0.sum(), 1),
        },
        'water_balance': water_balance_stats,
    }
    if heat_stress:
        result['livestock_heat_stress'] = heat_stress
    return result

def season_statistics(
    df: pd.DataFrame,
    season: Dict,
    *,
    shared_water_balance_summary: Optional[Dict[str, Any]] = None,
    season_df: Optional[pd.DataFrame] = None,
    thi_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Essential agro metrics for one season.
    Slices df to [onset, cessation] and computes the trimmed metric set:
      Precip       : Total_mm, Max_Daily, Rainy_Days, Intensity
      Temperature  : Mean_Tmax, Mean_Tmin, Mean_Tavg, Max_Tmax, Min_Tmin
      Water Balance: legacy precip-minus-ET0 totals plus shared NDWS/NDWL0/WRSI
    """
    onset_ts = pd.to_datetime(season['onset'])
    if season.get('cessation') is not None:
        cess_ts = pd.to_datetime(season['cessation'])
    else:
        cess_ts = df['date'].iloc[-1]

    sdf = (
        season_df.copy()
        if isinstance(season_df, pd.DataFrame)
        else _slice_date_window(df, onset_ts, cess_ts).copy()
    )
    if sdf.empty:
        return {}

    p  = sdf['precip'].fillna(0)
    tx = sdf['tmax']
    tn = sdf['tmin']
    wb = sdf['water_balance']

    rainy_days  = int((p >= 1.0).sum())
    length_days = int(season.get('length_days',
                                 (cess_ts - onset_ts).days + 1))
    intensity = _r(p.sum() / rainy_days, 2) if rainy_days else 0.0
    shared_wb = (
        dict(shared_water_balance_summary)
        if isinstance(shared_water_balance_summary, dict)
        else _shared_water_balance_summary(
            df,
            analysis_start=onset_ts.strftime('%Y-%m-%d'),
            analysis_end=cess_ts.strftime('%Y-%m-%d'),
        )
    )

    water_balance_stats = {
        'total_balance': _r(wb.sum(), 1),
        'deficit_days':  int((wb < 0).sum()),
        'surplus_days':  int((wb > 0).sum()),
        'stress_ratio':  _r((wb < 0).mean(), 3),
    }
    water_balance_stats.update(shared_wb)

    water_balance_methodology = None
    if shared_wb:
        water_balance_methodology = shared_build_water_balance_methodology(
            {
                'method': season.get('method', 'statistics_default_full_window'),
                'onset_date': onset_ts.strftime('%Y-%m-%d'),
                'cessation_date': cess_ts.strftime('%Y-%m-%d'),
                'spinup_days': season.get('spinup_days'),
            },
            {
                'soilcp': HAZARD_DEFAULT_SOILCP,
                'soilsat': HAZARD_DEFAULT_SOILSAT,
            },
            dict(HAZARD_DEFAULT_KC_PARAMS),
            count_window={
                'requested_window_mode': HAZARD_FULL_WINDOW_WATER_BALANCE,
                'applied_window_mode': HAZARD_FULL_WINDOW_WATER_BALANCE,
                'counted_days': int(len(sdf)),
                'counted_subseasons': 0,
                'fallback_reason': None,
                'warnings': [
                    'climate_statistics shared NDWS/WRSI uses default full-window root-zone settings.'
                ],
            },
        )

    heat_stress = _livestock_heat_stress_summary(sdf, thi_profile=thi_profile)

    result = {
        'onset':       onset_ts.strftime('%Y-%m-%d'),
        'cessation':   cess_ts.strftime('%Y-%m-%d'),
        'length_days': length_days,
        'precipitation': {
            'total_mm':   _r(p.sum(), 1),
            'max_daily':  _r(p.max(), 2),
            'rainy_days': rainy_days,
            'intensity':  intensity,
        },
        'temperature': {
            'mean_tmax':  _r(tx.mean()),
            'mean_tmin':  _r(tn.mean()),
            'mean_tavg':  _r(((tx + tn) / 2).mean()),
            'max_tmax':   _r(tx.max()),
            'min_tmin':   _r(tn.min()),
        },
        'water_balance': water_balance_stats,
        'water_balance_methodology': water_balance_methodology,
    }
    if heat_stress:
        result['livestock_heat_stress'] = heat_stress
    return result

# LTM (Long-Term Mean) aggregation across years per season window
def _is_num(v: Any) -> bool:
    """Numeric check that excludes bool and NaN/Inf floats."""
    return (isinstance(v, (int, float))
            and not isinstance(v, bool)
            and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))))

def _avg(values: List[Any], n: int = 2) -> Optional[float]:
    nums = [float(v) for v in values if _is_num(v)]
    if not nums:
        return None
    return _r(sum(nums) / len(nums), n)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{sec:02d}s"


def _derive_year_regime(seasons: List[Dict[str, Any]]) -> str:
    if not seasons:
        return "none"
    if len(seasons) == 1:
        return str(seasons[0].get("regime", "unimodal"))
    if len(seasons) == 2:
        return "bimodal"
    return "erratic"


def _season_heading(season: Dict[str, Any]) -> str:
    year = season.get("year", "n/a")
    season_number = season.get("season_number", 1)
    return f"Year {year} | Season {season_number}"


def _spei_block(
    df: pd.DataFrame,
    *,
    scale_months: int,
    fit: str,
    ref_start: Optional[str],
    ref_end: Optional[str],
) -> Dict[str, Any]:
    monthly = compute_monthly_spei(
        df,
        scale_months=scale_months,
        fit=fit,
        ref_start=ref_start,
        ref_end=ref_end,
    )
    records_df = monthly[
        ["date", "year", "month", "precipitation_mm", "et0_mm", "water_balance_mm", "water_balance_accumulated_mm", "spei"]
    ].copy()
    records_df["date"] = records_df["date"].dt.strftime("%Y-%m-%d")
    valid = records_df["spei"].notna()
    return {
        "config": {
            "scale_months": scale_months,
            "fit": fit,
            "ref_start": ref_start,
            "ref_end": ref_end,
        },
        "summary": {
            "n_months": int(len(records_df)),
            "n_valid_spei": int(valid.sum()),
            "start_date": records_df["date"].iloc[0] if len(records_df) else None,
            "end_date": records_df["date"].iloc[-1] if len(records_df) else None,
        },
        "metadata": monthly.attrs.get("spei_metadata", {}),
        "monthly_series": records_df.to_dict(orient="records"),
    }


def _spi_block(
    df: pd.DataFrame,
    *,
    scale_months: int,
    fit: str,
    ref_start: Optional[str],
    ref_end: Optional[str],
) -> Dict[str, Any]:
    monthly = compute_monthly_spi(
        df,
        scale_months=scale_months,
        fit=fit,
        ref_start=ref_start,
        ref_end=ref_end,
    )
    records_df = monthly[
        ["date", "year", "month", "precipitation_mm", "precipitation_accumulated_mm", "spi"]
    ].copy()
    records_df["date"] = records_df["date"].dt.strftime("%Y-%m-%d")
    valid = records_df["spi"].notna()
    return {
        "config": {
            "scale_months": scale_months,
            "fit": fit,
            "ref_start": ref_start,
            "ref_end": ref_end,
        },
        "summary": {
            "n_months": int(len(records_df)),
            "n_valid_spi": int(valid.sum()),
            "start_date": records_df["date"].iloc[0] if len(records_df) else None,
            "end_date": records_df["date"].iloc[-1] if len(records_df) else None,
        },
        "metadata": monthly.attrs.get("spei_metadata", {}),
        "monthly_series": records_df.to_dict(orient="records"),
    }


def _xclim_references_block(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "available": False,
            "core_period_metrics": [],
            "core_period_status": "skipped",
            "core_period_skip_reason": "no period data",
            "precip_reference_indices": [],
            "precip_reference_status": "skipped",
            "precip_reference_skip_reason": "no period data",
        }
    unique_dates = int(pd.to_datetime(df["date"]).dropna().nunique()) if "date" in df.columns else 0
    if unique_dates < 3:
        return {
            "available": True,
            "core_period_metrics": [],
            "core_period_status": "skipped",
            "core_period_skip_reason": "need at least 3 daily rows for xclim frequency inference",
            "precip_reference_indices": [],
            "precip_reference_status": "skipped",
            "precip_reference_skip_reason": "need at least 3 daily rows for xclim frequency inference",
        }

    from climate_tookit.climatology import (
        XCLIM_AVAILABLE,
        assess_xclim_precip_annual_readiness,
        compute_xclim_core_period_metrics,
        compute_xclim_precip_indices,
    )

    if not XCLIM_AVAILABLE:
        return {
            "available": False,
            "core_period_metrics": [],
            "core_period_status": "unavailable",
            "core_period_skip_reason": "xclim not installed",
            "precip_reference_indices": [],
            "precip_reference_status": "unavailable",
            "precip_reference_skip_reason": "xclim not installed",
        }

    block: Dict[str, Any] = {
        "available": True,
        "core_period_metrics": [],
        "core_period_status": "computed",
        "core_period_skip_reason": None,
        "precip_reference_indices": [],
        "precip_reference_status": "computed",
        "precip_reference_skip_reason": None,
    }

    core = compute_xclim_core_period_metrics(df)
    if core.empty:
        block["core_period_status"] = "skipped"
        block["core_period_skip_reason"] = "xclim returned no core period metrics"
    else:
        block["core_period_metrics"] = core.to_dict(orient="records")

    precip_skip = assess_xclim_precip_annual_readiness(df, value_column="precip")
    if precip_skip:
        block["precip_reference_status"] = "skipped"
        block["precip_reference_skip_reason"] = precip_skip
    else:
        precip = compute_xclim_precip_indices(df, value_column="precip")
        if precip.empty:
            block["precip_reference_status"] = "skipped"
            block["precip_reference_skip_reason"] = "xclim returned no precipitation reference indices"
        else:
            block["precip_reference_indices"] = precip.to_dict(orient="records")

    return block


def _save_index_csv_if_present(result: Dict[str, Any], json_path: Path, key: str) -> Optional[Path]:
    payload = result.get(key)
    if not payload or not payload.get("monthly_series"):
        return None
    csv_path = json_path.with_name(f"{json_path.stem}_{key}.csv")
    pd.DataFrame(payload["monthly_series"]).to_csv(csv_path, index=False)
    return csv_path

def ltm_season_summary(
    season_results: List[Dict[str, Any]],
    fixed_season:   Optional[str] = None,
) -> Dict[str, Any]:
    """
    Long-term mean across years per season window.
    Groups per-year season_results by season_number and averages each numeric metric. With --fixed-season "<w1>,<w2>", season_numbers 1..N map to the
    windows in order; auto-detected runs use the season_number assigned by seasons.py. Aggregates the per-season block AND the per-season views (raw
    climate summary + overall statistics).
    """
    if not season_results:
        return {'mode': 'fixed' if fixed_season else 'auto', 'windows': []}

    grouped: Dict[int, List[Dict]] = {}
    for s in season_results:
        sn = s.get('season_number', 1)
        grouped.setdefault(sn, []).append(s)

    labels = ([w.strip() for w in fixed_season.split(',')]
              if fixed_season else None)

    windows: List[Dict[str, Any]] = []
    for sn in sorted(grouped):
        seasons = grouped[sn]
        years   = sorted({s.get('year') for s in seasons
                          if s.get('year') is not None})
        label   = (labels[sn - 1] if labels and 0 < sn <= len(labels)
                   else f"season_{sn}")

        block: Dict[str, Any] = {
            'window':          label,
            'season_number':   sn,
            'n_years':         len(seasons),
            'years':           years,
            'length_days_avg': _avg([s.get('length_days') for s in seasons], 1),
        }

        for cat in ('precipitation', 'temperature', 'water_balance', 'livestock_heat_stress'):
            pool: Dict[str, List[float]] = {}
            for s in seasons:
                for k, v in (s.get(cat) or {}).items():
                    if _is_num(v):
                        pool.setdefault(k, []).append(float(v))
            if pool:
                block[cat] = {k: _avg(vs, 2) for k, vs in pool.items()}
            if cat == "livestock_heat_stress":
                for meta_key in ("livestock_type", "livestock_label", "climate_profile"):
                    meta_value = next(
                        (
                            (s.get(cat) or {}).get(meta_key)
                            for s in seasons
                            if isinstance(s.get(cat), dict)
                            and (s.get(cat) or {}).get(meta_key) is not None
                        ),
                        None,
                    )
                    if meta_value is not None:
                        block.setdefault(cat, {})[meta_key] = meta_value

        ov_pool: Dict[str, Dict[str, List[float]]] = {}
        for s in seasons:
            for cat, metrics in (s.get('overall_statistics') or {}).items():
                if not isinstance(metrics, dict):
                    continue
                for k, v in metrics.items():
                    if _is_num(v):
                        ov_pool.setdefault(cat, {}).setdefault(k, []).append(float(v))
        if ov_pool:
            block['overall_statistics'] = {
                cat: {k: _avg(vs, 2) for k, vs in mets.items()}
                for cat, mets in ov_pool.items()
            }

        raw_pool: Dict[str, Dict[str, List[float]]] = {}
        for s in seasons:
            for row in (s.get('raw_climate_summary') or []):
                var = row.get('Variable')
                if not var:
                    continue
                for stat in ('Mean', 'Min', 'Max', 'Std'):
                    v = row.get(stat)
                    if _is_num(v):
                        raw_pool.setdefault(var, {}).setdefault(stat, []).append(float(v))
        if raw_pool:
            block['raw_climate_summary'] = [
                {'Variable': var,
                 'Mean':     _avg(mets.get('Mean', []), 3),
                 'Min':      _avg(mets.get('Min',  []), 3),
                 'Max':      _avg(mets.get('Max',  []), 3),
                 'Std':      _avg(mets.get('Std',  []), 3)}
                for var, mets in raw_pool.items()
            ]
        windows.append(block)

    return {
        'mode':    'fixed' if fixed_season else 'auto',
        'windows': windows,
    }


def _auto_season_slot_warning(season_results: List[Dict[str, Any]]) -> Optional[str]:
    counts: Dict[int, int] = {}
    for season in season_results or []:
        year = season.get("year")
        if isinstance(year, int):
            counts[year] = counts.get(year, 0) + 1
    observed = set(counts.values())
    if len(observed) <= 1:
        return None
    summary = ", ".join(f"{year}:{count}" for year, count in sorted(counts.items())) or "none"
    return (
        "Auto-detected season counts differ across years, so LTM season windows by "
        f"season_number would blend incomparable seasons. Counts by year: {summary}. "
        "Use --fixed-season for stable multi-year seasonal LTM output."
    )


def _season_slot_variability(
    season_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Optional[float]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for season in season_results or []:
        sn = season.get("season_number")
        if isinstance(sn, int):
            grouped.setdefault(sn, []).append(season)

    out: Dict[str, Dict[str, Optional[float]]] = {}
    for sn, seasons in sorted(grouped.items()):
        onset_doys = []
        length_days = []
        for season in seasons:
            onset = pd.to_datetime(season.get("onset"), errors="coerce")
            if pd.notna(onset):
                onset_doys.append(float(onset.dayofyear))
            if _is_num(season.get("length_days")):
                length_days.append(float(season["length_days"]))

        onset_sd = float(np.std(onset_doys, ddof=0)) if len(onset_doys) >= 2 else 0.0 if onset_doys else None
        length_sd = float(np.std(length_days, ddof=0)) if len(length_days) >= 2 else 0.0 if length_days else None
        out[str(sn)] = {
            "n_years": len(seasons),
            "onset_sd_days": _r(onset_sd, 1) if onset_sd is not None else None,
            "length_sd_days": _r(length_sd, 1) if length_sd is not None else None,
        }
    return out


def _build_season_detection_status(
    *,
    fixed_season: Optional[str],
    start_year: int,
    end_year: int,
    annual_summary: Dict[str, Dict[str, Any]],
    season_results: List[Dict[str, Any]],
    season_slot_warning: Optional[str],
) -> Dict[str, Any]:
    expected_years = max(0, end_year - start_year + 1)
    counts_by_year: Dict[int, int] = {year: 0 for year in range(start_year, end_year + 1)}
    regimes_by_year: Dict[int, str] = {}
    for season in season_results or []:
        year = season.get("year")
        if isinstance(year, int):
            counts_by_year[year] = counts_by_year.get(year, 0) + 1
            if season.get("year_regime") not in {None, "none"}:
                regimes_by_year[year] = str(season.get("year_regime"))

    detected_years = sum(1 for count in counts_by_year.values() if count > 0)
    detected_fraction = (detected_years / expected_years) if expected_years else 0.0
    skip_reasons = {
        str(year): info.get("season_skip_reason")
        for year, info in annual_summary.items()
        if info.get("season_skip_reason")
    }
    variability = _season_slot_variability(season_results)

    reasons: List[str] = []
    status = "ok"

    if fixed_season:
        reasons.append("fixed_season_override")
    else:
        all_skip_reasons = [str(v).lower() for v in skip_reasons.values()]
        if expected_years and detected_years == 0:
            status = "prompt_required"
            if all_skip_reasons and all("perhumid location" in reason for reason in all_skip_reasons):
                reasons.append("perhumid_no_clear_onset")
            else:
                reasons.append("no_seasons_detected_all_years")
        elif any(count == 0 for count in counts_by_year.values()) and detected_years > 0:
            status = "prompt_required"
            reasons.append("missing_seasons_some_years")

        if season_slot_warning:
            status = "prompt_required"
            reasons.append("unstable_season_counts")

        if detected_fraction < 0.6 and status != "prompt_required":
            status = "prompt_required"
            reasons.append("low_detected_year_fraction")
        elif detected_fraction < 0.8 and status == "ok":
            status = "warn"
            reasons.append("partial_year_coverage")

        onset_warn = False
        length_warn = False
        onset_prompt = False
        length_prompt = False
        for metrics in variability.values():
            onset_sd = metrics.get("onset_sd_days")
            length_sd = metrics.get("length_sd_days")
            if onset_sd is not None:
                if onset_sd > 30:
                    onset_prompt = True
                elif onset_sd > 15:
                    onset_warn = True
            if length_sd is not None:
                if length_sd > 30:
                    length_prompt = True
                elif length_sd > 15:
                    length_warn = True
        if onset_prompt:
            status = "prompt_required"
            reasons.append("high_onset_variability")
        elif onset_warn and status == "ok":
            status = "warn"
            reasons.append("moderate_onset_variability")
        if length_prompt:
            status = "prompt_required"
            reasons.append("high_season_length_variability")
        elif length_warn and status == "ok":
            status = "warn"
            reasons.append("moderate_season_length_variability")

        regime_set = {regime for regime in regimes_by_year.values() if regime not in {None, "none"}}
        if len(regime_set) > 1 and status == "ok":
            status = "warn"
            reasons.append("regime_flips_across_years")

        if skip_reasons and status == "ok":
            status = "warn"
            reasons.append("season_detection_skips_present")

    reasons = list(dict.fromkeys(reasons))
    guidance = _season_detection_guidance([
        (year, reason) for year, reason in skip_reasons.items() if reason
    ])
    if not guidance and fixed_season:
        guidance = ["Using user-supplied fixed seasons. Review windows before comparing across sites or crops."]
    elif not guidance and status == "warn":
        guidance = ["Auto season detection completed, but review year-to-year stability before interpreting LTM summaries."]
    elif not guidance and status == "prompt_required":
        guidance = ["Auto season detection not reliable enough for direct interpretation. Use --fixed-season or crop-calendar presets."]

    return {
        "status": status,
        "reasons": reasons,
        "human_review_recommended": status in {"warn", "prompt_required"},
        "calendar_override_recommended": status == "prompt_required",
        "diagnostics": {
            "expected_years": expected_years,
            "detected_years": detected_years,
            "detected_year_fraction": _r(detected_fraction, 3),
            "counts_by_year": {str(year): count for year, count in sorted(counts_by_year.items())},
            "regimes_by_year": {str(year): regime for year, regime in sorted(regimes_by_year.items())},
            "season_slot_variability": variability,
            "skip_reasons_by_year": skip_reasons,
            "season_slot_warning": season_slot_warning,
        },
        "guidance": guidance,
    }

# Season detection on a pre-fetched DataFrame
def detect_seasons_auto(
    df: pd.DataFrame,
    lat: float,
    start_year: int,
    end_year: int,
    verbose: bool = False,
) -> Tuple[Dict[int, List[Dict]], Dict[int, Dict]]:
    """
    Mirrors seasons.fetch_and_analyze_years() but operates on the *master* DataFrame already in memory (no re-fetching).
    For each ref year, slices a 1.5-year window so onset/cessation crossing the year boundary is captured, then runs ETO detection.
    Final post-processing (reassign + dedup) matches seasons.py.
    """
    seasons_dict: Dict[int, List[Dict]] = {}
    annual_dict:  Dict[int, Dict]       = {}

    for ref_year in range(start_year, end_year + 1):
        if verbose:
            print(f"\n  Auto-detecting seasons for {ref_year}")
        win_start = pd.Timestamp(f"{ref_year}-01-01")
        win_end   = pd.Timestamp(f"{ref_year + 1}-06-30")
        win = (df[(df['date'] >= win_start) & (df['date'] <= win_end)]
               .copy().reset_index(drop=True))

        # Annual stats (calendar year only)
        yr_df = df[df['date'].dt.year == ref_year]
        if yr_df.empty:
            seasons_dict[ref_year] = []
            annual_dict[ref_year]  = {}
            continue

        annual_rain = float(yr_df['precip'].fillna(0).sum())
        humid_info  = check_humid(annual_rain, yr_df)
        annual_dict[ref_year] = {
            'annual_rain_mm':  round(annual_rain, 1),
            'is_humid':        humid_info['is_humid'],
            'low_rain_months': humid_info['low_rain_months'],
            'result_str':      humid_info['result_str'],
            'season_skip_reason': None,
        }
        if verbose:
            print(f"    Annual rainfall={annual_rain:.1f} mm | "
                  f"{humid_info['result_str']}")

        if len(win) < 30:
            if verbose:
                print(f"    Window too short ({len(win)} days)")
            seasons_dict[ref_year] = []
            annual_dict[ref_year]['season_skip_reason'] = (
                f"Season detection skipped because the analysis window was too short ({len(win)} days)."
            )
            continue
        try:
            seasons_dict[ref_year] = detect_onset_cessation(win, verbose=verbose)
        except ValueError as exc:
            if verbose:
                print(f"    Skipped: {exc}")
            seasons_dict[ref_year] = []
            annual_dict[ref_year]['season_skip_reason'] = str(exc)
        except Exception as exc:
            if verbose:
                print(f"    Detection failed: {exc}")
            seasons_dict[ref_year] = []
            annual_dict[ref_year]['season_skip_reason'] = (
                f"Season detection failed: {type(exc).__name__}: {exc}"
            )

    # Post-process: reassign spillover & remove duplicates
    cleaned = reassign_spillover_seasons(
        seasons_dict, lat=lat, start_year=start_year, end_year=end_year, verbose=verbose
    )
    final = remove_duplicate_seasons(cleaned, verbose=verbose)
    final_annual = {
        y: annual_dict.get(y, {}) for y in range(start_year, end_year + 1)
    }
    return final, final_annual

def detect_seasons_fixed(
    df: pd.DataFrame,
    fixed_defs: List[Dict],
    start_year: int,
    end_year: int,
    include_eto_subseasons: bool = True,
    verbose: bool = False,
) -> Tuple[Dict[int, List[Dict]], Dict[int, Dict]]:
    """
    Mirrors seasons.fetch_and_analyze_years_fixed() on the master DataFrame.
    For each year and each fixed window:
      1. Build the [onset, cessation] dates (handles year-crossing).
      2. Slice the master df and run ETO sub-detection inside the window.
    """
    seasons_dict: Dict[int, List[Dict]] = {
        y: [] for y in range(start_year, end_year + 1)
    }
    annual_dict: Dict[int, Dict] = {}

    for year in range(start_year, end_year + 1):
        if verbose:
            print(f"\n  Fixed-season analysis for {year}")
        yr_df = df[df['date'].dt.year == year]
        if yr_df.empty:
            annual_dict[year] = {}
            continue

        # Annual stats (calendar year only)
        annual_rain = float(yr_df['precip'].fillna(0).sum())
        humid_info  = check_humid(annual_rain, yr_df)
        annual_dict[year] = {
            'annual_rain_mm':  round(annual_rain, 1),
            'is_humid':        humid_info['is_humid'],
            'low_rain_months': humid_info['low_rain_months'],
            'result_str':      humid_info['result_str'],
        }
        if verbose:
            print(f"    Annual rainfall={annual_rain:.1f} mm | "
                  f"{humid_info['result_str']}")
        for sd in fixed_defs:
            (o_m, o_d) = sd['onset_md']
            (c_m, c_d) = sd['cessation_md']
            cess_year  = year + 1 if (c_m, c_d) < (o_m, o_d) else year
            try:
                onset_date = date(year, o_m, o_d)
                cess_date  = date(cess_year, c_m, c_d)
            except ValueError as exc:
                if verbose:
                    print(f"    [WARN] Invalid date: {exc}")
                continue

            length_days = (cess_date - onset_date).days + 1
            cross       = " (year-crossing)" if cess_year != year else ""

            # Optional ETO sub-detection inside the fixed window
            window_df = (df[(df['date'] >= pd.Timestamp(onset_date)) &
                            (df['date'] <= pd.Timestamp(cess_date))]
                         .copy().reset_index(drop=True))
            eto_subs: List[Dict] = []
            if include_eto_subseasons:
                if len(window_df) < 14:
                    if verbose:
                        print(f"    [ETO] {onset_date} → {cess_date}: "
                              f"window too short ({len(window_df)} days)")
                else:
                    try:
                        eto_subs = detect_onset_cessation(window_df, verbose=verbose)
                    except ValueError as exc:
                        if verbose:
                            print(f"    [ETO] {onset_date} → {cess_date}: {exc}")
                    except Exception as exc:
                        if verbose:
                            print(f"    [ETO] {onset_date} → {cess_date} failed: {exc}")
            seasons_dict[year].append({
                'onset':       pd.Timestamp(onset_date),
                'cessation':   pd.Timestamp(cess_date),
                'length_days': length_days,
                'regime':      'fixed',
                'eto_seasons': eto_subs if include_eto_subseasons else None,
            })
            if verbose:
                if include_eto_subseasons:
                    print(f"    Fixed window: {onset_date} → {cess_date}{cross} "
                          f"({length_days}d) | ETO sub-seasons={len(eto_subs)}")
                else:
                    print(f"    Fixed window: {onset_date} → {cess_date}{cross} "
                          f"({length_days}d) | ETO skipped")

    return seasons_dict, annual_dict


def _annual_summary_from_detection(
    annual_dict: Dict[int, Dict[str, Any]],
    seasons_dict: Dict[int, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    return {
        str(y): {
            'annual_rain_mm':  info.get('annual_rain_mm'),
            'is_humid':        info.get('is_humid'),
            'low_rain_months': info.get('low_rain_months'),
            'humid_test':      info.get('result_str'),
            'year_regime':     _derive_year_regime(seasons_dict.get(y, [])),
            'season_skip_reason': info.get('season_skip_reason'),
        }
        for y, info in annual_dict.items()
    }


def _compile_season_results(
    df: pd.DataFrame,
    seasons_dict: Dict[int, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    return _compile_season_results_with_options(df, seasons_dict)


def _compile_season_results_with_options(
    df: pd.DataFrame,
    seasons_dict: Dict[int, List[Dict[str, Any]]],
    *,
    include_season_raw_summary: bool = True,
    include_season_overall_statistics: bool = True,
    thi_profile: Optional[Dict[str, Any]] = None,
    return_breakdown: bool = False,
) -> Any:
    season_results: List[Dict[str, Any]] = []
    reduction_breakdown = {
        "core_seconds": 0.0,
        "raw_summary_seconds": 0.0,
        "overall_statistics_seconds": 0.0,
        "eto_subseason_seconds": 0.0,
    }
    for year in sorted(seasons_dict.keys()):
        year_regime = _derive_year_regime(seasons_dict[year])
        for i, season in enumerate(seasons_dict[year], 1):
            onset_ts = pd.to_datetime(season['onset'])
            cess_ts = (
                pd.to_datetime(season['cessation'])
                if season.get('cessation') is not None
                else df['date'].iloc[-1]
            )
            sdf = _slice_date_window(df, onset_ts, cess_ts)
            core_started = perf_counter()
            shared_wb = _shared_water_balance_summary(
                df,
                analysis_start=season['onset'],
                analysis_end=season['cessation'],
            )
            try:
                stats = season_statistics(
                    df,
                    season,
                    shared_water_balance_summary=shared_wb,
                    season_df=sdf,
                    thi_profile=thi_profile,
                )
            except TypeError as exc:
                if (
                    "shared_water_balance_summary" not in str(exc)
                    and "season_df" not in str(exc)
                ):
                    raise
                stats = season_statistics(df, season)
            reduction_breakdown["core_seconds"] += perf_counter() - core_started
            if not stats:
                continue
            stats['year'] = year
            stats['season_number'] = i
            stats['regime'] = season.get('regime', 'auto')
            stats['year_regime'] = year_regime
            stats['season_identity'] = build_season_identity(
                stats['onset'],
                stats['cessation'],
                length_days=stats.get('length_days'),
                regime=season.get('regime', 'auto'),
                season_number=i,
                total_seasons_per_year=len(seasons_dict[year]),
            )

            if include_season_raw_summary:
                raw_started = perf_counter()
                stats['raw_climate_summary'] = raw_climate_summary(sdf)
                reduction_breakdown["raw_summary_seconds"] += perf_counter() - raw_started
            if include_season_overall_statistics and not sdf.empty:
                overall_started = perf_counter()
                stats['overall_statistics'] = overall_statistics(
                    sdf,
                    full_df=df,
                    analysis_start=season['onset'],
                    analysis_end=season['cessation'],
                    shared_water_balance_summary=shared_wb,
                    thi_profile=thi_profile,
                )
                reduction_breakdown["overall_statistics_seconds"] += (
                    perf_counter() - overall_started
                )

            eto_started = perf_counter()
            sub_results: List[Dict] = []
            for es in (season.get('eto_seasons') or []):
                sub_onset_ts = pd.to_datetime(es['onset'])
                sub_cess_ts = (
                    pd.to_datetime(es['cessation'])
                    if es.get('cessation') is not None
                    else sdf['date'].iloc[-1]
                )
                sub_sdf = _slice_date_window(sdf, sub_onset_ts, sub_cess_ts)
                try:
                    ssub = season_statistics(sdf, es, season_df=sub_sdf, thi_profile=thi_profile)
                except TypeError as exc:
                    if "season_df" not in str(exc):
                        raise
                    ssub = season_statistics(sdf, es, thi_profile=thi_profile)
                if ssub:
                    ssub['regime'] = es.get('regime', 'eto')
                    sub_results.append(ssub)
            if sub_results or season.get('eto_seasons') is not None:
                stats['eto_sub_seasons'] = sub_results
            reduction_breakdown["eto_subseason_seconds"] += perf_counter() - eto_started

            season_results.append(stats)
    if return_breakdown:
        return season_results, {
            key: round(value, 3) for key, value in reduction_breakdown.items()
        }
    return season_results


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
        raise ValueError(f"Unsupported calendar source: {calendar_source}. Available: ggcmi")
    return resolve_calendar_preset(lat, lon, crop_name, system=calendar_system)

# Orchestrator
def analyze_climate_statistics(
    location_coord: Tuple[float, float],
    start_year:     int,
    end_year:       int,
    source:         str,
    fixed_season:   Optional[str] = None,
    model:          Optional[str] = None,
    scenario:       Optional[str] = None,
    extra_months:   int = 6,
    precip_source:  Optional[str] = None,
    temp_source:    Optional[str] = None,
    crop_name:      Optional[str] = None,
    calendar_source: Optional[str] = None,
    calendar_system: str = "rf",
    spei_scale_months: Optional[int] = None,
    spei_fit: str = "ub-pwm",
    spei_ref_start: Optional[str] = None,
    spei_ref_end: Optional[str] = None,
    spi_scale_months: Optional[int] = None,
    spi_fit: str = "ub-pwm",
    spi_ref_start: Optional[str] = None,
    spi_ref_end: Optional[str] = None,
    custom_station_file: Optional[str] = None,
    custom_station_variables: Optional[List[str]] = None,
    custom_station_name: Optional[str] = None,
    custom_temp_unit: str = "c",
    custom_precip_unit: str = "mm",
    livestock_type: str = DEFAULT_LIVESTOCK_TYPE,
    livestock_climate_profile: str = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    livestock_elevation_override_m: Optional[float] = None,
    include_period_raw_summary: bool = True,
    include_season_raw_summary: bool = True,
    include_season_overall_statistics: bool = True,
    include_ltm_season_summary: bool = True,
    ee_project_id: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Single entrypoint.
      Step 1 -- Fetch all climate variables for [start_year, end_year + tail]
      Step 2 -- Add ET0 (Hargreaves) and water balance
      Step 3 -- Detect seasons (auto or fixed)
      Step 4 -- Compute raw / overall / per-season statistics
    """
    lat, lon = location_coord
    run_started = perf_counter()
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
    calendar_system = str(calendar_system).lower()
    if calendar_system not in CALENDAR_SYSTEM_CHOICES:
        return {
            "error": (
                f"Invalid calendar_system '{calendar_system}'. "
                f"Choose from {', '.join(CALENDAR_SYSTEM_CHOICES)}."
            )
        }
    pair_error = _validate_paired_sources(precip_source, temp_source, start_year, end_year)
    if pair_error:
        return {'error': pair_error}
    if not (precip_source and temp_source):
        source_error = _validate_source_compatibility(source, start_year, end_year)
        if source_error:
            return {'error': source_error}
    period_error = _validate_nex_ltm_period(source, start_year, end_year)
    if period_error:
        return {'error': period_error}
    nex_scenario_error = _validate_nex_requested_period(
        source,
        start_year,
        end_year,
        scenario,
    )
    if nex_scenario_error:
        return {'error': nex_scenario_error}

    requested_calendar_preset: Optional[Dict[str, Any]] = None
    if crop_name or calendar_source:
        try:
            requested_calendar_preset = _resolve_calendar_preset_request(
                lat=lat,
                lon=lon,
                crop_name=crop_name,
                calendar_source=calendar_source,
                calendar_system=calendar_system,
            )
        except ValueError as exc:
            return {'error': str(exc)}

    # Decide fetch window (mirror seasons.py's tail logic)
    fixed_defs: Optional[List[Dict]] = None
    direct_calendar_preset = False
    skip_eto_subseasons = False
    direct_calendar_requested = (
        not fixed_season
        and requested_calendar_preset is not None
    )
    if direct_calendar_requested:
        fixed_season = requested_calendar_preset['fixed_season']
        fixed_defs = parse_fixed_seasons(fixed_season)
        direct_calendar_preset = True
        skip_eto_subseasons = True
    if (
        source == 'nex_gddp'
        and str(scenario).lower() == 'historical'
        and direct_calendar_requested
        and end_year >= 2014
    ):
        if any(sd['cessation_md'] < sd['onset_md'] for sd in fixed_defs):
            return {
                'error': (
                    "NEX-GDDP historical auto/calendar mode cannot use a year-crossing "
                    "season window that needs post-2014 tail data. "
                    "Use a non-year-crossing fixed season or shorten the baseline window."
                )
            }
        direct_calendar_preset = True
    tail_extension_years = 0
    if fixed_season:
        if fixed_defs is None:
            fixed_defs = parse_fixed_seasons(fixed_season)
        if any(sd['cessation_md'] < sd['onset_md'] for sd in fixed_defs):
            tail_extension_years = 1
    else:
        # Auto mode: need 6-month tail past final year for late cessations
        tail_extension_years = 1 if extra_months > 0 else 0

    fetch_start = f"{start_year}-01-01"
    if tail_extension_years:
        # Add either 6 months (auto) or full year (fixed year-crossing)
        if fixed_season:
            fetch_end = f"{end_year + 1}-12-31"
        else:
            tail_end_dt = (date(end_year, 12, 31) +
                           pd.DateOffset(months=extra_months)).date()
            fetch_end = tail_end_dt.strftime('%Y-%m-%d')
    else:
        fetch_end = f"{end_year}-12-31"

    if source == 'nex_gddp' and scenario and _validate_period_against_scenario is not None:
        fetch_end_date = pd.Timestamp(fetch_end).date()
        try:
            _validate_period_against_scenario(
                str(scenario),
                date(start_year, 1, 1),
                fetch_end_date,
            )
        except ValueError as exc:
            return {'error': str(exc)}

    run_label = [f"source={source}"]
    if model:
        run_label.append(f"model={model}")
    if scenario:
        run_label.append(f"scenario={scenario}")
    if precip_source:
        run_label.append(f"precip_source={normalize_climate_dataset_name(precip_source)}")
    if temp_source:
        run_label.append(f"temp_source={normalize_climate_dataset_name(temp_source)}")
    if custom_station_file:
        run_label.append("station_override=on")
    if fixed_season:
        run_label.append(f"fixed_season={fixed_season}")
    if requested_calendar_preset:
        run_label.append(
            f"calendar_preset={requested_calendar_preset['calendar_source']}"
            f":{requested_calendar_preset['crop_name']}"
            f":{requested_calendar_preset['calendar_system']}"
        )
    run_label.append(
        "livestock="
        f"{thi_profile['livestock_type']}:{thi_profile['climate_profile_applied']}"
    )
    cache_note = build_historical_cache_note(
        source,
        precip_source=precip_source,
        temp_source=temp_source,
    )
    if cache_note:
        print(cache_note)
    if direct_calendar_preset:
        if (
            source == 'nex_gddp'
            and str(scenario).lower() == 'historical'
            and end_year >= 2014
        ):
            print(
                "NEX-GDDP historical auto tail would cross into post-2014 dates. "
                f"Applying {requested_calendar_preset['calendar_source']} preset directly "
                f"for crop={requested_calendar_preset['crop_name']} "
                f"system={requested_calendar_preset['calendar_system']} "
                f"-> {requested_calendar_preset['fixed_season']}"
            )
        else:
            print(
                f"Using requested {requested_calendar_preset['calendar_source']} preset directly "
                f"for crop={requested_calendar_preset['crop_name']} "
                f"system={requested_calendar_preset['calendar_system']} "
                f"-> {requested_calendar_preset['fixed_season']}"
            )
    print(f"Fetching climate data: {fetch_start} → {fetch_end} | "
          f"{' | '.join(run_label)}")
    fetch_started = perf_counter()
    try:
        df = get_climate_data(lat, lon, fetch_start, fetch_end,
                              source, model=model, scenario=scenario,
                              precip_source=precip_source,
                              temp_source=temp_source,
                              custom_station_file=custom_station_file,
                              custom_station_variables=custom_station_variables,
                              custom_station_name=custom_station_name,
                              custom_temp_unit=custom_temp_unit,
                              custom_precip_unit=custom_precip_unit,
                              verbose=verbose,
                              ee_project_id=ee_project_id)
    except Exception as exc:
        return {
            'error': (
                f"Climate data fetch failed for source='{source}' "
                f"period={fetch_start}..{fetch_end}: {type(exc).__name__}: {exc}"
            )
        }
    fetch_elapsed = perf_counter() - fetch_started
    print(f"  Retrieved {len(df)} days in {_format_elapsed(fetch_elapsed)}, "
          f"columns={list(df.columns)}")

    # ET0 + water balance
    prep_started = perf_counter()
    df = add_et0(df, lat)
    df = calculate_water_balance(df)
    prep_elapsed = perf_counter() - prep_started
    print(f"  Derived ET0 + water balance in {_format_elapsed(prep_elapsed)}")

    # Season detection (uses full df with tail for year-crossing capture)
    detect_started = perf_counter()
    if fixed_season:
        seasons_dict, annual_dict = detect_seasons_fixed(
            df,
            fixed_defs,
            start_year,
            end_year,
            include_eto_subseasons=not skip_eto_subseasons,
            verbose=verbose,
        )
    else:
        seasons_dict, annual_dict = detect_seasons_auto(
            df, lat, start_year, end_year, verbose=verbose
        )
    detect_elapsed = perf_counter() - detect_started
    print(f"  Season detection completed in {_format_elapsed(detect_elapsed)}")

    # Per-season block (computed against the FULL df so year-crossing seasons have access to days beyond Dec 31). Raw and overall stats are computed per season only; no full-period view is produced.
    reduce_started = perf_counter()
    season_results, reduction_breakdown = _compile_season_results_with_options(
        df,
        seasons_dict,
        include_season_raw_summary=include_season_raw_summary,
        include_season_overall_statistics=include_season_overall_statistics,
        thi_profile=thi_profile,
        return_breakdown=True,
    )
    reduce_elapsed = perf_counter() - reduce_started
    annual_summary = _annual_summary_from_detection(annual_dict, seasons_dict)

    # Period-wide views (whole years start_year..end_year, excluding the fetchtail).
    period_df = df[(df['date'] >= pd.Timestamp(f"{start_year}-01-01")) &
                   (df['date'] <= pd.Timestamp(f"{end_year}-12-31"))]
    raw_period     = raw_climate_summary(period_df) if include_period_raw_summary else []
    overall_period = (
        overall_statistics(period_df, thi_profile=thi_profile)
        if not period_df.empty else {}
    )
    xclim_references = _xclim_references_block(period_df)
    spei_result: Optional[Dict[str, Any]] = None
    spi_result: Optional[Dict[str, Any]] = None
    if spei_scale_months is not None and not period_df.empty:
        spei_started = perf_counter()
        spei_result = _spei_block(
            period_df,
            scale_months=spei_scale_months,
            fit=spei_fit,
            ref_start=spei_ref_start,
            ref_end=spei_ref_end,
        )
        spei_elapsed = perf_counter() - spei_started
        print(
            f"  SPEI-{spei_scale_months} computed in {_format_elapsed(spei_elapsed)} "
            f"(valid_months={spei_result.get('summary', {}).get('n_valid_spei', 0)})"
        )
    else:
        spei_elapsed = 0.0
    if spi_scale_months is not None and not period_df.empty:
        spi_started = perf_counter()
        spi_result = _spi_block(
            period_df,
            scale_months=spi_scale_months,
            fit=spi_fit,
            ref_start=spi_ref_start,
            ref_end=spi_ref_end,
        )
        spi_elapsed = perf_counter() - spi_started
        print(
            f"  SPI-{spi_scale_months} computed in {_format_elapsed(spi_elapsed)} "
            f"(valid_months={spi_result.get('summary', {}).get('n_valid_spi', 0)})"
        )
    else:
        spi_elapsed = 0.0

    season_slot_warning: Optional[str] = None
    if not fixed_season:
        season_slot_warning = _auto_season_slot_warning(season_results)

    # LTM (long-term mean) across years per season window
    if season_slot_warning:
        ltm = {'mode': 'auto', 'windows': [], 'warning': season_slot_warning}
        print(f"\n  [WARN] {season_slot_warning}")
    else:
        ltm = (
            ltm_season_summary(season_results, fixed_season)
            if include_ltm_season_summary
            else {'mode': 'skipped', 'windows': [], 'skipped': True}
        )
    years_span = end_year - start_year + 1
    coverage_warning: Optional[str] = None
    if years_span < MIN_LTM_YEARS:
        coverage_warning = (
            f"LTM coverage is {years_span} year(s); recommended ≥ "
            f"{MIN_LTM_YEARS} (standard baseline "
            f"{BASELINE_DEFAULT_PERIOD[0]}-{BASELINE_DEFAULT_PERIOD[1]})."
        )
        print(f"\n  [WARN] {coverage_warning}")

    detection_status = _build_season_detection_status(
        fixed_season=fixed_season,
        start_year=start_year,
        end_year=end_year,
        annual_summary=annual_summary,
        season_results=season_results,
        season_slot_warning=season_slot_warning,
    )

    calendar_preset_used = direct_calendar_preset
    calendar_preset_fallback = False
    applied_calendar_preset: Optional[Dict[str, Any]] = (
        dict(requested_calendar_preset) if direct_calendar_preset and requested_calendar_preset else None
    )
    applied_fixed_season = fixed_season
    applied_mode = 'fixed' if fixed_season else 'auto'
    if applied_calendar_preset is not None:
        applied_calendar_preset['direct_applied_reason'] = (
            'user_requested_calendar_preset'
            if direct_calendar_requested and not (
                source == 'nex_gddp' and str(scenario).lower() == 'historical' and end_year >= 2014
            )
            else 'nex_historical_tail_unavailable'
        )
        direct_reason = (
            'calendar_preset_direct_requested'
            if direct_calendar_requested and not (
                source == 'nex_gddp' and str(scenario).lower() == 'historical' and end_year >= 2014
            )
            else 'calendar_preset_direct_applied'
        )
        detection_status['reasons'] = [
            direct_reason,
            *[r for r in detection_status['reasons'] if r != 'fixed_season_override'],
            'fixed_season_override',
        ]
        detection_status['guidance'] = [
            "Season windows were taken directly from requested crop-calendar preset "
            f"({applied_calendar_preset['calendar_source']} | "
            f"crop={applied_calendar_preset['crop_name']} | "
            f"system={applied_calendar_preset['calendar_system']} | "
            f"fixed={applied_calendar_preset['fixed_season']}). "
            "Review before comparing across sites or crops."
        ]

    if (
        not fixed_season
        and requested_calendar_preset
        and detection_status['status'] == 'prompt_required'
    ):
        print(
            "  Auto season detection not reliable enough. "
            f"Applying {requested_calendar_preset['calendar_source']} preset "
            f"for crop={requested_calendar_preset['crop_name']} "
            f"system={requested_calendar_preset['calendar_system']} "
            f"-> {requested_calendar_preset['fixed_season']}"
        )
        preset_started = perf_counter()
        fallback_fixed_defs = parse_fixed_seasons(requested_calendar_preset['fixed_season'])
        seasons_dict, annual_dict = detect_seasons_fixed(
            df,
            fallback_fixed_defs,
            start_year,
            end_year,
        )
        reduce_started = perf_counter()
        season_results, reduction_breakdown = _compile_season_results_with_options(
            df,
            seasons_dict,
            include_season_raw_summary=include_season_raw_summary,
            include_season_overall_statistics=include_season_overall_statistics,
            thi_profile=thi_profile,
            return_breakdown=True,
        )
        reduce_elapsed = perf_counter() - reduce_started
        annual_summary = _annual_summary_from_detection(annual_dict, seasons_dict)
        season_slot_warning = None
        ltm = (
            ltm_season_summary(season_results, requested_calendar_preset['fixed_season'])
            if include_ltm_season_summary
            else {'mode': 'skipped', 'windows': [], 'skipped': True}
        )
        detection_status = _build_season_detection_status(
            fixed_season=requested_calendar_preset['fixed_season'],
            start_year=start_year,
            end_year=end_year,
            annual_summary=annual_summary,
            season_results=season_results,
            season_slot_warning=season_slot_warning,
        )
        detection_status['reasons'] = [
            'calendar_preset_fallback_applied',
            *[r for r in detection_status['reasons'] if r != 'fixed_season_override'],
            'fixed_season_override',
        ]
        detection_status['guidance'] = [
            "Auto season detection was not reliable enough, so season windows "
            "were taken from the requested crop-calendar preset "
            f"({requested_calendar_preset['calendar_source']} | "
            f"crop={requested_calendar_preset['crop_name']} | "
            f"system={requested_calendar_preset['calendar_system']} | "
            f"fixed={requested_calendar_preset['fixed_season']}). "
            "Review before comparing across sites or crops."
        ]
        calendar_preset_used = True
        calendar_preset_fallback = True
        applied_calendar_preset = dict(requested_calendar_preset)
        applied_calendar_preset['fallback_from_auto_status'] = 'prompt_required'
        applied_calendar_preset['fallback_elapsed_seconds'] = round(
            perf_counter() - preset_started, 3
        )
        applied_fixed_season = requested_calendar_preset['fixed_season']
        applied_mode = 'fixed'

    total_elapsed = perf_counter() - run_started
    print(
        f"  Completed climate statistics in {_format_elapsed(total_elapsed)} "
        f"(season_rows={len(season_results)}, reduction={_format_elapsed(reduce_elapsed)})"
    )

    return {
        'location':            {'lat': lat, 'lon': lon},
        'period':              {'start_year': start_year, 'end_year': end_year},
        'source':              source,
        'mode':                applied_mode,
        'fixed_season':        applied_fixed_season,
        'model':               model,
        'scenario':            scenario,
        'precip_source':       normalize_climate_dataset_name(precip_source),
        'temp_source':         normalize_climate_dataset_name(temp_source),
        'crop_name':           crop_name,
        'thi_profile':         thi_profile,
        'calendar_source':     calendar_source,
        'calendar_system':     calendar_system,
        'calendar_preset_requested': requested_calendar_preset,
        'calendar_preset_used': calendar_preset_used,
        'calendar_preset_fallback': calendar_preset_fallback,
        'calendar_preset':     applied_calendar_preset,
        'raw_climate_summary': raw_period,
        'overall_statistics':  overall_period,
        'xclim_references':    xclim_references,
        'season_statistics':   season_results,
        'ltm_season_summary':  ltm,
        'spei':                spei_result,
        'spi':                 spi_result,
        'season_slot_warning': season_slot_warning,
        'coverage_warning':    coverage_warning,
        'annual_summary':      annual_summary,
        'season_detection_status': detection_status['status'],
        'season_detection_reasons': detection_status['reasons'],
        'human_review_recommended': detection_status['human_review_recommended'],
        'calendar_override_recommended': detection_status['calendar_override_recommended'],
        'season_detection_guidance': detection_status['guidance'],
        'season_detection': detection_status,
        'timing':              {
            'fetch_seconds': round(fetch_elapsed, 3),
            'prep_seconds': round(prep_elapsed, 3),
            'season_detection_seconds': round(detect_elapsed, 3),
            'season_reduction_seconds': round(reduce_elapsed, 3),
            'season_reduction_core_seconds': reduction_breakdown.get('core_seconds'),
            'season_reduction_raw_seconds': reduction_breakdown.get('raw_summary_seconds'),
            'season_reduction_overall_seconds': reduction_breakdown.get('overall_statistics_seconds'),
            'season_reduction_eto_seconds': reduction_breakdown.get('eto_subseason_seconds'),
            'spei_seconds': round(spei_elapsed, 3),
            'spi_seconds': round(spi_elapsed, 3),
            'total_seconds': round(total_elapsed, 3),
        },
        'analysis_date':       datetime.now().isoformat(),
        'methodology':         'preprocess_data + seasons.py detection + water balance',
    }

# Display
TERMINAL_TABLE_HEADER_ALIASES = {
    "Variable": "var",
    "Metric": "metric",
    "Value": "value",
    "Year": "year",
    "Annual rainfall": "rain_mm",
    "Low-rain months": "low_rain_mo",
    "Humid test": "humid_test",
}


def _terminal_width(default: int = 120) -> int:
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except OSError:
        return default


def _short_cell(value: Any, max_len: int = 18) -> Any:
    if value is None or pd.isna(value):
        return "n/a"
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _compact_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy().fillna("n/a")
    for column in ["Variable", "Metric"]:
        if column in display.columns:
            values = display[column].dropna().astype(str).str.strip()
            if not values.empty and values.nunique() == 1:
                display = display.drop(columns=[column])
    display = display.rename(columns=TERMINAL_TABLE_HEADER_ALIASES)
    rendered = display.to_string(index=False)
    if max((len(line) for line in rendered.splitlines()), default=0) <= _terminal_width():
        return display
    for column in display.columns:
        if display[column].dtype == object:
            display[column] = display[column].map(lambda value: _short_cell(value, max_len=14))
    return display


def _print_indented_table(df: pd.DataFrame, indent: str = "    ") -> None:
    for line in _compact_display_frame(df).to_string(index=False).splitlines():
        print(f"{indent}{line}")


def _print_xclim_references(payload: Dict[str, Any], *, detailed: bool) -> None:
    if not payload:
        return
    print("\n" + "=" * 70)
    print("XCLIM STANDARD REFERENCES")
    print("=" * 70)
    if not payload.get("available"):
        reason = payload.get("core_period_skip_reason") or "xclim unavailable"
        print(f"xclim status : unavailable ({reason})")
        return

    core_rows = payload.get("core_period_metrics") or []
    core_status = payload.get("core_period_status") or "n/a"
    print(f"Core period metrics : {core_status} | rows={len(core_rows)}")
    if payload.get("core_period_skip_reason"):
        print(f"Core note           : {payload['core_period_skip_reason']}")
    if detailed and core_rows:
        _print_indented_table(pd.DataFrame(core_rows).fillna("n/a"))

    precip_rows = payload.get("precip_reference_indices") or []
    precip_status = payload.get("precip_reference_status") or "n/a"
    print(f"Precip reference indices : {precip_status} | rows={len(precip_rows)}")
    if payload.get("precip_reference_skip_reason"):
        print(f"Precip note              : {payload['precip_reference_skip_reason']}")
    if detailed and precip_rows:
        _print_indented_table(pd.DataFrame(precip_rows).fillna("n/a"))

def print_raw_summary_by_season(seasons: List[Dict]) -> None:
    """One raw mean/min/max/std table per season, printed as stacked blocks."""
    print("\n" + "=" * 70)
    print("RAW CLIMATE SUMMARY BY SEASON")
    print("=" * 70)
    if not seasons:
        print("No seasons detected for this period.")
        return
    current_year = None
    for s in seasons:
        if s['year'] != current_year:
            current_year = s['year']
            if s.get("year_regime") not in {None, "none"}:
                print(f"\n  Year {current_year} regime: {s['year_regime']}")
        print(f"\n  {_season_heading(s)}")
        print(f"    {s['onset']} → {s['cessation']}  ({s['length_days']}d)")
        rows = s.get('raw_climate_summary') or []
        if not rows:
            print("    (no data)")
            continue
        _print_indented_table(pd.DataFrame(rows).fillna("n/a"))

def print_overall_by_season(seasons: List[Dict]) -> None:
    """One overall agro-metric table per season, printed as stacked blocks."""
    print("\n" + "=" * 70)
    print("OVERALL STATISTICS BY SEASON")
    print("=" * 70)
    if not seasons:
        print("No seasons detected for this period.")
        return
    current_year = None
    for s in seasons:
        if s['year'] != current_year:
            current_year = s['year']
            if s.get("year_regime") not in {None, "none"}:
                print(f"\n  Year {current_year} regime: {s['year_regime']}")
        print(f"\n  {_season_heading(s)}")
        print(f"    {s['onset']} → {s['cessation']}  ({s['length_days']}d)")
        stats = s.get('overall_statistics')
        if not stats:
            print("    (no data)")
            continue
        print(f"    Total days: {stats['total_days']}")
        rows = []
        for var_key, var_label in [
            ('precipitation', 'Precipitation'),
            ('temperature',   'Temperature'),
            ('et0',           'ET0'),
            ('water_balance', 'Water Balance'),
            ('livestock_heat_stress', 'Livestock THI'),
        ]:
            if var_key not in stats:
                continue
            for metric, value in stats[var_key].items():
                rows.append({
                    'Variable': var_label,
                    'Metric':   metric,
                    'Value':    value if value is not None else "n/a",
                })
        _print_indented_table(pd.DataFrame(rows))

def print_seasons(seasons: List[Dict]) -> None:
    print("\n" + "=" * 70)
    print("SEASON STATISTICS")
    print("=" * 70)
    if not seasons:
        print("No seasons detected for this period.")
        return

    current_year = None
    for s in seasons:
        if s['year'] != current_year:
            current_year = s['year']
            if s.get("year_regime") not in {None, "none"}:
                print(f"\n  Year {current_year} regime: {s['year_regime']}")
        print(f"\n  {_season_heading(s)}")
        print(f"    {s['onset']} → {s['cessation']}  ({s['length_days']}d)")
        p = s['precipitation']
        t = s['temperature']
        w = s['water_balance']
        print(f"    Precipitation : "
              f"total={p['total_mm']} mm | "
              f"max_daily={p['max_daily']} mm | "
              f"rainy_days={p['rainy_days']} | "
              f"intensity={p['intensity']} mm/wet-day")
        print(f"    Temperature   : "
              f"mean_tmax={t['mean_tmax']}°C | "
              f"mean_tmin={t['mean_tmin']}°C | "
              f"mean_tavg={t['mean_tavg']}°C | "
              f"max_tmax={t['max_tmax']}°C | "
              f"min_tmin={t['min_tmin']}°C")
        h = s.get('livestock_heat_stress') or {}
        if h:
            print(f"    {_thi_profile_label(h)} : "
                  f"mean_thi={h.get('mean_thi')} | "
                  f"max_thi={h.get('max_thi')} | "
                  f"stress_days={h.get('days_stress')} | "
                  f"mild={h.get('days_mild')} | "
                  f"moderate={h.get('days_moderate')} | "
                  f"severe={h.get('days_severe')}")
        print(f"    Water balance : "
              f"total={w['total_balance']} mm | "
              f"deficit_days={w['deficit_days']} | "
              f"surplus_days={w['surplus_days']} | "
              f"stress_ratio={w['stress_ratio']}")
        if any(key in w for key in ('WRSI', 'NDWS', 'NDWL0')):
            extras = []
            if 'WRSI' in w:
                extras.append(f"WRSI={w['WRSI']}%")
            if 'NDWS' in w:
                extras.append(f"NDWS={w['NDWS']}d")
            if 'NDWL0' in w:
                extras.append(f"NDWL0={w['NDWL0']}d")
            if 'crop_water_requirement_mm' in w:
                extras.append(f"CWR={w['crop_water_requirement_mm']} mm")
            if 'actual_crop_et_mm' in w:
                extras.append(f"AET={w['actual_crop_et_mm']} mm")
            print(f"                    crop_model: {' | '.join(extras)}")

        subs = s.get('eto_sub_seasons')
        if subs is not None:
            print(f"    {'─' * 50}")
            print(f"    ETO sub-seasons within fixed window:")
            if not subs:
                print(f"      none detected")
            for j, es in enumerate(subs, 1):
                ep = es['precipitation']
                ew = es['water_balance']
                print(f"      {j}. {es['onset']} → {es['cessation']} "
                      f"({es['length_days']}d) | "
                      f"rain={ep['total_mm']} mm | "
                      f"rainy={ep['rainy_days']}d | "
                      f"stress_ratio={ew['stress_ratio']}"
                      + (
                          f" | WRSI={ew.get('WRSI')}%"
                          if ew.get('WRSI') is not None else ""
                      ))

def print_ltm_by_season(ltm: Dict[str, Any],
                        header: str = "LTM SEASON SUMMARY") -> None:
    """Long-term-mean view (averaged across years per season window)."""
    print("\n" + "=" * 70)
    print(header)
    print("=" * 70)
    windows = (ltm or {}).get('windows') or []
    if not windows:
        print("(no LTM windows)")
        return
    for w in windows:
        years = w.get('years') or []
        rng   = (f"{years[0]}-{years[-1]}" if len(years) >= 2
                 else (str(years[0]) if years else "n/a"))
        n_lbl = (f"n_models={w['n_models']}" if 'n_models' in w
                 else f"n_years={w.get('n_years')}")
        print(f"\n  Window {w.get('window')} "
              f"(season #{w.get('season_number')}, {n_lbl}, years={rng})")
        if w.get('length_days_avg') is not None:
            print(f"    avg_length_days={w['length_days_avg']}")
        p  = w.get('precipitation') or {}
        t  = w.get('temperature')   or {}
        wb = w.get('water_balance') or {}
        if p:
            print(f"    Precipitation : "
                  f"total={p.get('total_mm')} mm | "
                  f"max_daily={p.get('max_daily')} mm | "
                  f"rainy_days={p.get('rainy_days')} | "
                  f"intensity={p.get('intensity')} mm/wet-day")
        if t:
            print(f"    Temperature   : "
                  f"mean_tmax={t.get('mean_tmax')}°C | "
                  f"mean_tmin={t.get('mean_tmin')}°C | "
                  f"mean_tavg={t.get('mean_tavg')}°C | "
                  f"max_tmax={t.get('max_tmax')}°C | "
                  f"min_tmin={t.get('min_tmin')}°C")
        h = w.get('livestock_heat_stress') or {}
        if h:
            print(f"    {_thi_profile_label(h)} : "
                  f"mean_thi={h.get('mean_thi')} | "
                  f"max_thi={h.get('max_thi')} | "
                  f"stress_days={h.get('days_stress')} | "
                  f"mild={h.get('days_mild')} | "
                  f"moderate={h.get('days_moderate')} | "
                  f"severe={h.get('days_severe')}")
        if wb:
            print(f"    Water balance : "
                  f"total={wb.get('total_balance')} mm | "
                  f"deficit_days={wb.get('deficit_days')} | "
                  f"surplus_days={wb.get('surplus_days')} | "
                  f"stress_ratio={wb.get('stress_ratio')}")
            if any(key in wb for key in ('WRSI', 'NDWS', 'NDWL0')):
                extras = []
                if wb.get('WRSI') is not None:
                    extras.append(f"WRSI={wb.get('WRSI')}%")
                if wb.get('NDWS') is not None:
                    extras.append(f"NDWS={wb.get('NDWS')}d")
                if wb.get('NDWL0') is not None:
                    extras.append(f"NDWL0={wb.get('NDWL0')}d")
                if wb.get('crop_water_requirement_mm') is not None:
                    extras.append(f"CWR={wb.get('crop_water_requirement_mm')} mm")
                if wb.get('actual_crop_et_mm') is not None:
                    extras.append(f"AET={wb.get('actual_crop_et_mm')} mm")
                print(f"                    crop_model: {' | '.join(extras)}")

def print_annual(annual: Dict[str, Dict]) -> None:
    print("\n" + "=" * 70)
    print("ANNUAL SUMMARY (humid test)")
    print("=" * 70)
    if not annual:
        print("(no annual data)")
        return
    rows = []
    for year, info in sorted(annual.items()):
        rows.append({
            'Year':              year,
            'Annual rainfall':   f"{info.get('annual_rain_mm')} mm"
                                 if info.get('annual_rain_mm') is not None
                                 else "n/a",
            'Low-rain months':   info.get('low_rain_months', 'n/a'),
            'Humid test':        info.get('humid_test', 'n/a'),
        })
    print(_compact_display_frame(pd.DataFrame(rows)).to_string(index=False))

def _ltm_header(result: Dict[str, Any]) -> str:
    """Pick BASELINE / FUTURE / generic LTM header based on the run window."""
    end          = (result.get('period') or {}).get('end_year',   0)
    start        = (result.get('period') or {}).get('start_year', 0)
    baseline_end = BASELINE_DEFAULT_PERIOD[1]
    source_label = "paired" if result.get("source") == PAIRED_SOURCE_SENTINEL else "single-source"
    if start > baseline_end:
        return f"FUTURE LTM SEASON SUMMARY ({source_label})"
    if end <= baseline_end:
        return f"BASELINE LTM SEASON SUMMARY ({source_label})"
    return f"LTM SEASON SUMMARY ({source_label})"


def _season_detection_guidance(notes: List[Tuple[str, str]]) -> List[str]:
    guidance: List[str] = []
    for _, reason in notes:
        reason_lc = str(reason).lower()
        if "perhumid location" in reason_lc or "no clear onset/cessation" in reason_lc:
            guidance.append(
                "Auto onset/cessation not suitable for this climate window. "
                "Use --fixed-season or crop-calendar presets for seasonal interpretation."
            )
        elif "too short" in reason_lc:
            guidance.append(
                "Analysis window too short for season detection. Expand year coverage or use --fixed-season."
            )
        elif "failed" in reason_lc:
            guidance.append(
                "Season detection failed. Review inputs, then retry with --fixed-season if seasonal summaries are still needed."
            )
        else:
            guidance.append(
                "Auto season detection needs review. Consider --fixed-season or crop-calendar preset."
            )
    return list(dict.fromkeys(guidance))


def print_season_detection_notes(result: Dict[str, Any]) -> None:
    annual = result.get('annual_summary') or {}
    detection = result.get("season_detection") or {}
    notes = []
    for year, info in sorted(annual.items()):
        reason = info.get('season_skip_reason')
        if reason:
            notes.append((year, reason))
    status = detection.get("status")
    reasons = detection.get("reasons") or []
    guidance = detection.get("guidance") or []
    if not notes and (not status or (status == "ok" and not reasons and not guidance)):
        return
    print("\n" + "=" * 70)
    print("SEASON DETECTION NOTES")
    print("=" * 70)
    if status:
        print(f"status: {status}")
    if reasons:
        print(f"reasons: {', '.join(reasons)}")
    for year, reason in notes:
        print(f"{year}: {reason}")
    if guidance:
        print("\nRecommended next step(s):")
        for item in guidance:
            print(f"- {item}")

def print_pandas(result: Dict[str, Any]) -> None:
    _print_pandas(result, detailed=True)


def _has_custom_water_balance_metrics(result: Dict[str, Any]) -> bool:
    for season in result.get('season_statistics') or []:
        water_balance = season.get('water_balance') or {}
        if any(key in water_balance for key in ('NDWS', 'NDWL0', 'WRSI')):
            return True
    for window in ((result.get('ltm_season_summary') or {}).get('windows') or []):
        water_balance = window.get('water_balance') or {}
        if any(key in water_balance for key in ('NDWS', 'NDWL0', 'WRSI')):
            return True
    overall = result.get('overall_statistics') or {}
    water_balance = overall.get('water_balance') if isinstance(overall, dict) else {}
    return any(key in (water_balance or {}) for key in ('NDWS', 'NDWL0', 'WRSI'))


def _print_pandas(result: Dict[str, Any], *, detailed: bool = True) -> None:
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    print(f"\nLocation : {result['location']['lat']:.4f}, "
          f"{result['location']['lon']:.4f}")
    print(f"Period   : {result['period']['start_year']} – "
          f"{result['period']['end_year']}")
    print(f"Source   : {result['source']}  | mode={result['mode']}")
    if result.get('fixed_season'):
        print(f"Fixed    : {result['fixed_season']}")
    if result.get('calendar_preset_used') and result.get('calendar_preset'):
        preset = result['calendar_preset']
        print(
            "Calendar : "
            f"{preset.get('calendar_source')} | crop={preset.get('crop_name')} | "
            f"system={preset.get('calendar_system')} | "
            f"matched=({preset.get('matched_lat'):.2f},{preset.get('matched_lon'):.2f}) | "
            f"distance={preset.get('distance_deg'):.3f}°"
        )
    if result.get('model'):
        print(f"Model    : {result['model']}")
    if result.get('scenario'):
        print(f"Scenario : {result['scenario']}")
    if result.get('coverage_warning'):
        print(f"Coverage : [WARN] {result['coverage_warning']}")
    if result.get('season_detection_status'):
        print(f"Season detect : {result['season_detection_status']}")
    if result.get('season_slot_warning'):
        print(f"Season LTM: [WARN] {result['season_slot_warning']}")
    if _has_custom_water_balance_metrics(result):
        print(
            "Water-balance note : NDWS, NDWL0, and WRSI are custom crop-water-balance "
            "metrics under model assumptions, not standard xclim/ETCCDI indicators."
        )

    if detailed:
        print_raw_summary_by_season(result['season_statistics'])
        print_overall_by_season(result['season_statistics'])
    print_seasons(result['season_statistics'])
    print_ltm_by_season(result.get('ltm_season_summary', {}),
                        header=_ltm_header(result))
    print_season_detection_notes(result)
    print_annual(result['annual_summary'])
    _print_xclim_references(result.get("xclim_references") or {}, detailed=detailed)
    spei = result.get("spei")
    if spei:
        print("\n" + "=" * 70)
        print("SPEI")
        print("=" * 70)
        summary = spei.get("summary") or {}
        config = spei.get("config") or {}
        print(
            f"SPEI-{config.get('scale_months')} | fit={config.get('fit')} | "
            f"months={summary.get('n_months')} | valid={summary.get('n_valid_spei')}"
        )
        rows = (spei.get("monthly_series") or [])[-12:]
        if detailed and rows:
            preview = pd.DataFrame(rows)[["date", "water_balance_accumulated_mm", "spei"]]
            _print_indented_table(preview.fillna("n/a"))
    spi = result.get("spi")
    if spi:
        print("\n" + "=" * 70)
        print("SPI")
        print("=" * 70)
        summary = spi.get("summary") or {}
        config = spi.get("config") or {}
        print(
            f"SPI-{config.get('scale_months')} | fit={config.get('fit')} | "
            f"months={summary.get('n_months')} | valid={summary.get('n_valid_spi')}"
        )
        rows = (spi.get("monthly_series") or [])[-12:]
        if detailed and rows:
            preview = pd.DataFrame(rows)[["date", "precipitation_accumulated_mm", "spi"]]
            _print_indented_table(preview.fillna("n/a"))

# CLI
def main() -> int:
    parser = argparse.ArgumentParser(
        description='Climate statistics analysis by season (auto or fixed)',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--location', required=True,
                        help='Coordinates as "lat,lon"  e.g. "-1.286,36.817"')
    parser.add_argument('--start-year', type=int, required=True)
    parser.add_argument('--end-year',   type=int, required=True)
    parser.add_argument('--source',     required=True,
                        help=(
                            "Data source. Examples:\n"
                            "  agera_5, era_5, chirps_v2, chirps_v2+chirts, paired,\n"
                            "  nasa_power, nex_gddp, auto\n"
                            "Default historical daily path: chirps_v3_daily_rnl + agera_5.\n"
                            "Recommended direct single-source fallback: agera_5.\n"
                            "For GEE/Xee-backed historical paths, cold-cache first runs can "
                            "take noticeably longer than warm-cache reruns.\n"
                            "Incompatible sources are rejected with a clean "
                            "error at runtime."
                        ))
    parser.add_argument('--precip-source', default=None,
                        help='Optional paired precipitation source, e.g. chirps_v3_daily_rnl, chirps_v2, imerg, or tamsat')
    parser.add_argument('--temp-source', default=None,
                        help='Optional paired temperature source, e.g. agera_5 or era_5')
    parser.add_argument('--custom-station-file', default=None,
                        help='Optional custom station CSV/JSON used to override historical variables by date.')
    parser.add_argument('--custom-station-vars', default=None,
                        help='Comma-separated station override vars, e.g. precipitation,max_temperature,min_temperature')
    parser.add_argument('--custom-station-name', default=None,
                        help='Optional station name label for custom station input.')
    parser.add_argument('--custom-temp-unit', choices=['c', 'f', 'k'],
                        default='c',
                        help='Temperature unit in custom station file (default: c)')
    parser.add_argument('--custom-precip-unit', choices=['mm', 'inch', 'tenth_mm'],
                        default='mm',
                        help='Precipitation unit in custom station file (default: mm)')
    parser.add_argument('--livestock-type',
                        choices=list_thi_livestock_profiles(),
                        default=DEFAULT_LIVESTOCK_TYPE,
                        help='Livestock THI profile (default: cattle_dairy)')
    parser.add_argument('--livestock-climate-profile',
                        choices=['auto', 'temperate', 'tropical'],
                        default=DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
                        help='THI climate context. auto uses latitude plus highland elevation when available.')
    parser.add_argument('--livestock-elevation-override-m', '--livestock-elevation-m',
                        dest='livestock_elevation_override_m', type=float, default=None,
                        help='Optional site elevation override, meters above sea level, for THI climate-context selection.')
    parser.add_argument('--crop', default=None,
                        help='Optional crop name for crop-calendar preset fallback, e.g. maize or rice')
    parser.add_argument('--calendar-source', choices=['ggcmi'], default=None,
                        help='Optional crop-calendar preset source. Currently: ggcmi')
    parser.add_argument('--calendar-system', choices=list(CALENDAR_SYSTEM_CHOICES),
                        default='rf',
                        help="Crop-calendar management system for presets: rf, ir, or both (default: rf)")
    parser.add_argument(
        '--fixed-season',
        default=None,
        metavar='MM-DD:MM-DD[,MM-DD:MM-DD]',
        help=(
            "Force fixed calendar season windows (matches seasons.py)."
            "Climate data is still fetched via --source for statistics"
            "and ETO-based onset/cessation analysis within each window."
            "Examples:"
            "  Single season : --fixed-season '03-01:05-31'"
            "  Two seasons   : --fixed-season '03-01:05-31,10-01:12-15'"
            "  Year-crossing : --fixed-season '11-01:02-28'"
        ),
    )
    parser.add_argument('--extra-months', type=int, default=6,
                        help='Extra months past Dec for late cessations '
                             '(auto mode, default: 6)')
    parser.add_argument('--model', default=None,
                        help='NEX-GDDP model (e.g. ACCESS-CM2)')
    parser.add_argument('--scenario', default=None,
                        help='NEX-GDDP scenario (e.g. ssp245)')
    parser.add_argument('--project-id', default=None,
                        help='Optional Earth Engine / GCP project ID for GEE-backed sources.')
    parser.add_argument('--spei-scale-months', type=int, default=None,
                        help='Optional SPEI scale in months, e.g. 3, 6, or 12')
    parser.add_argument('--spei-fit', choices=['ub-pwm', 'empirical'],
                        default='ub-pwm',
                        help='SPEI fitting method (default: ub-pwm)')
    parser.add_argument('--spei-ref-start', default=None,
                        help='Optional SPEI reference-period start date, e.g. 1991-01-01')
    parser.add_argument('--spei-ref-end', default=None,
                        help='Optional SPEI reference-period end date, e.g. 2020-12-31')
    parser.add_argument('--spi-scale-months', type=int, default=None,
                        help='Optional SPI scale in months, e.g. 1, 3, 6, or 12')
    parser.add_argument('--spi-fit', choices=['ub-pwm', 'empirical'],
                        default='ub-pwm',
                        help='SPI fitting method (default: ub-pwm)')
    parser.add_argument('--spi-ref-start', default=None,
                        help='Optional SPI reference-period start date, e.g. 1991-01-01')
    parser.add_argument('--spi-ref-end', default=None,
                        help='Optional SPI reference-period end date, e.g. 2020-12-31')
    parser.add_argument('--format', choices=['json', 'pandas'],
                        default='pandas',
                        help='Output format (default: pandas)')
    parser.add_argument('--output', default=None,
                        help='Output JSON file path (json format only)')
    parser.add_argument('--output-dir', default='.',
                        help='Directory for default JSON output (default: cwd)')
    parser.add_argument('--no-save', action='store_true',
                        help='Skip saving the JSON output')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed season-detection diagnostics and per-year logs.')

    args = parser.parse_args()

    try:
        lat, lon = map(float, args.location.split(','))
    except ValueError:
        print("Error: --location must be in 'lat,lon' format.")
        return 1

    if args.fixed_season:
        print(f"Fixed-season mode | {lat:.4f}N, {lon:.4f}E | "
              f"{args.start_year}–{args.end_year} | source={args.source}")
    else:
        print(f"Auto-detection mode | {lat:.4f}N, {lon:.4f}E | "
              f"{args.start_year}–{args.end_year} | source={args.source}")

    result = analyze_climate_statistics(
        location_coord=(lat, lon),
        start_year=args.start_year,
        end_year=args.end_year,
        source=args.source,
        fixed_season=args.fixed_season,
        model=args.model,
        scenario=args.scenario,
        extra_months=args.extra_months,
        precip_source=args.precip_source,
        temp_source=args.temp_source,
        custom_station_file=args.custom_station_file,
        custom_station_variables=(
            [item.strip() for item in args.custom_station_vars.split(',') if item.strip()]
            if args.custom_station_vars else None
        ),
        custom_station_name=args.custom_station_name,
        custom_temp_unit=args.custom_temp_unit,
        custom_precip_unit=args.custom_precip_unit,
        livestock_type=args.livestock_type,
        livestock_climate_profile=args.livestock_climate_profile,
        livestock_elevation_override_m=args.livestock_elevation_override_m,
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
        ee_project_id=args.project_id,
        verbose=args.verbose,
    )

    # Display
    if args.format == 'pandas':
        _print_pandas(result, detailed=args.verbose)
        if 'error' in result:
            return 1
    else:
        out = json.dumps(result, indent=2, default=str)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, 'w') as f:
                f.write(out)
            spei_csv_path = _save_index_csv_if_present(result, Path(args.output), "spei")
            spi_csv_path = _save_index_csv_if_present(result, Path(args.output), "spi")
            if 'error' in result:
                print(f"Saved error report to {args.output}")
                raise SystemExit(1)
            print(f"Saved to {args.output}")
            if spei_csv_path is not None:
                print(f"Saved SPEI CSV to {spei_csv_path}")
            if spi_csv_path is not None:
                print(f"Saved SPI CSV to {spi_csv_path}")
        else:
            print(out)
            if 'error' in result:
                raise SystemExit(1)

    # Auto-save JSON alongside pandas display
    if not args.no_save and args.format == 'pandas' and 'error' not in result:
        mode_tag = 'fixed' if args.fixed_season else args.source
        fname = (f"climate_stats_{lat:.4f}_{lon:.4f}_"
                 f"{args.start_year}_{args.end_year}_{mode_tag}.json")
        path  = Path(args.output_dir) / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(json.dumps(result, indent=2, default=str))
        spei_csv_path = _save_index_csv_if_present(result, path, "spei")
        spi_csv_path = _save_index_csv_if_present(result, path, "spi")
        print(f"\n✓ SAVED: {path}")
        if spei_csv_path is not None:
            print(f"✓ SAVED SPEI CSV: {spei_csv_path}")
        if spi_csv_path is not None:
            print(f"✓ SAVED SPI CSV: {spi_csv_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

# Fixed single season:
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2018 --end-year 2022 --fixed-season "03-01:05-31" --source era_5 --format pandas

# Fixed two seasons:
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2018 --end-year 2022 --fixed-season "03-01:05-31,10-01:12-15" --source agera_5 --format pandas

# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2018 --end-year 2022 --fixed-season "11-01:02-28" --source chirps_v2+chirts --format pandas

# NEX-GDDP with fixed season:
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2030 --end-year 2032 --fixed-season "03-01:05-31" --source nex_gddp --model ACCESS-CM2 --scenario ssp245 --format pandas

# Baseline LTM (standard 1991-2020 window, fixed MAM):
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 1991 --end-year 2020 --fixed-season "03-01:05-31" --source era_5 --format pandas

# Auto season detection:
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2018 --end-year 2020 --source era_5 --format pandas
# python climate_tookit/climate_statistics/statistics.py --location="-1.286,36.817" --start-year 2015 --end-year 2020 --source agera_5 --format pandas
