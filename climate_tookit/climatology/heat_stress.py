"""Livestock heat-stress helpers.

THI formula:
    THI = (1.8 * T + 32) - ((0.55 - 0.0055 * RH) * ((1.8 * T) - 26))

Operational thresholds follow Thornton et al. (2021) Table 1 by livestock
profile, with optional tropical-context extreme-threshold adjustments from
their Table 2. Package auto-selection distinguishes tropical lowland from
temperate/highland contexts using latitude first and elevation when available.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

THI_FORMULA = "THI = (1.8*T + 32) - ((0.55 - 0.0055*RH) * ((1.8*T) - 26))"
TROPICS_LATITUDE_DEG = 23.5
HIGHLAND_ELEVATION_M = 1500.0
DEFAULT_LIVESTOCK_TYPE = "cattle_dairy"
DEFAULT_LIVESTOCK_CLIMATE_PROFILE = "auto"

LIVESTOCK_THI_BASE_PROFILES: dict[str, dict[str, Any]] = {
    "cattle_dairy": {
        "label": "Cattle (dairy)",
        "species_group": "cattle",
        "moderate": 72.0,
        "high": 79.0,
        "extreme": 89.0,
    },
    "cattle_general": {
        "label": "Cattle (general)",
        "species_group": "cattle",
        "moderate": 72.0,
        "high": 79.0,
        "extreme": 90.0,
    },
    "cattle_beef": {
        "label": "Cattle (beef)",
        "species_group": "cattle",
        "moderate": 72.0,
        "high": 82.0,
        "extreme": 94.0,
    },
    "goats": {
        "label": "Goats",
        "species_group": "goats",
        "moderate": 70.0,
        "high": 79.0,
        "extreme": 89.0,
    },
    "sheep": {
        "label": "Sheep",
        "species_group": "sheep",
        "moderate": 72.0,
        "high": 78.0,
        "extreme": 90.0,
    },
    "pigs": {
        "label": "Pigs",
        "species_group": "pigs",
        "moderate": 75.0,
        "high": 79.0,
        "extreme": 84.0,
    },
    "poultry_broilers": {
        "label": "Poultry (broilers)",
        "species_group": "poultry",
        "moderate": 74.0,
        "high": 79.0,
        "extreme": 84.0,
    },
    "poultry_layers": {
        "label": "Poultry (layers)",
        "species_group": "poultry",
        "moderate": 71.0,
        "high": 76.0,
        "extreme": 82.0,
    },
    "poultry_general": {
        "label": "Poultry (general)",
        "species_group": "poultry",
        "moderate": 73.0,
        "high": 81.0,
        "extreme": 85.0,
    },
}

LIVESTOCK_THI_TROPICAL_EXTREME_THRESHOLDS: dict[str, float] = {
    "cattle": 94.0,
    "goats": 94.0,
    "sheep": 93.0,
    "pigs": 92.0,
    "poultry": 92.0,
}

_MEAN_TEMP_CANDIDATES = (
    "mean_temperature",
    "tavg",
    "tmean",
    "temperature",
    "temp",
)

_THI_SOURCE_SUPPORT = {
    "agera_5": "supported: humidity derived from dewpoint + air temperature in current fetch pipeline",
    "nasa_power": "supported: humidity available from current NASA POWER fetch path",
    "ghcn_daily": "supported when RHAV humidity field exists for chosen station and window",
    "gsod": "supported when humidity field exists for chosen station and window",
    "custom_station": "supported when uploaded file includes humidity/rh column",
    "era_5": (
        "uncertain: current ERA5 fetch configuration does not define a humidity band for the "
        "operational THI workflow, even though downstream canonical humidity naming exists elsewhere"
    ),
    "nex_gddp": "conditionally supported: relative humidity uses NEX-GDDP hurs when present, but some GEE model/scenario combinations lack that band",
    "chirps_v2": "not supported: precipitation-only source",
    "chirps_v3_daily_rnl": "not supported: precipitation-only source",
    "imerg": "not supported: precipitation-only source",
    "tamsat": "not supported: no humidity data",
    "chirts": "not supported: temperature-only source",
}


def list_thi_livestock_profiles() -> list[str]:
    return sorted(LIVESTOCK_THI_BASE_PROFILES)


def _normalize_thresholds(
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, float]:
    merged = {
        "none_max": 72.0,
        "mild_max": 79.0,
        "moderate_max": 89.0,
    }
    if thresholds:
        merged.update({str(key): float(value) for key, value in thresholds.items()})
    required = {"none_max", "mild_max", "moderate_max"}
    missing = required.difference(merged)
    if missing:
        raise ValueError(f"Missing THI threshold keys: {', '.join(sorted(missing))}")
    if not (merged["none_max"] < merged["mild_max"] < merged["moderate_max"]):
        raise ValueError("THI thresholds must satisfy none_max < mild_max < moderate_max.")
    return merged


def _normalize_livestock_type(livestock_type: str | None) -> str:
    normalized = str(livestock_type or DEFAULT_LIVESTOCK_TYPE).strip().lower()
    if normalized not in LIVESTOCK_THI_BASE_PROFILES:
        raise ValueError(
            "Unknown livestock_type "
            f"{livestock_type!r}. Choose from {', '.join(list_thi_livestock_profiles())}."
        )
    return normalized


def _normalize_climate_profile(profile: str | None) -> str:
    normalized = str(profile or DEFAULT_LIVESTOCK_CLIMATE_PROFILE).strip().lower()
    aliases = {
        "highland": "temperate",
        "highland_temperate": "temperate",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"auto", "temperate", "tropical"}:
        raise ValueError(
            "Unknown livestock climate profile "
            f"{profile!r}. Choose from auto, temperate, tropical."
        )
    return normalized


def infer_livestock_climate_profile(
    *,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    requested = _normalize_climate_profile(climate_profile)
    resolved_elevation_m = None if elevation_m is None else float(elevation_m)
    elevation_source = "user" if elevation_m is not None else None

    if requested != "auto":
        return {
            "requested": requested,
            "applied": requested,
            "reason": "user_selected",
            "lat": None if lat is None else float(lat),
            "lon": None if lon is None else float(lon),
            "elevation_m": resolved_elevation_m,
            "elevation_source": elevation_source,
        }

    if resolved_elevation_m is None and auto_fetch_elevation and lat is not None and lon is not None:
        try:
            from climate_tookit.weather_station.dem import fetch_anchor_elevation

            resolved_elevation_m = float(
                fetch_anchor_elevation(
                    lat=float(lat),
                    lon=float(lon),
                    cache_dir=cache_dir,
                )
            )
            elevation_source = "dem"
        except Exception:
            resolved_elevation_m = None
            elevation_source = None

    abs_lat = None if lat is None else abs(float(lat))
    if abs_lat is None:
        applied = "temperate"
        reason = "auto_default_no_location"
    elif abs_lat <= TROPICS_LATITUDE_DEG:
        if (
            resolved_elevation_m is not None
            and resolved_elevation_m >= HIGHLAND_ELEVATION_M
        ):
            applied = "temperate"
            reason = "tropical_highland_proxy"
        else:
            applied = "tropical"
            reason = (
                "tropical_latitude_band"
                if elevation_source is None
                else "tropical_lowland_by_dem"
            )
    else:
        applied = "temperate"
        reason = "extratropical_latitude_band"

    return {
        "requested": requested,
        "applied": applied,
        "reason": reason,
        "lat": None if lat is None else float(lat),
        "lon": None if lon is None else float(lon),
        "elevation_m": resolved_elevation_m,
        "elevation_source": elevation_source,
    }


def resolve_thi_profile(
    *,
    livestock_type: str | None = DEFAULT_LIVESTOCK_TYPE,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    normalized_type = _normalize_livestock_type(livestock_type)
    base = LIVESTOCK_THI_BASE_PROFILES[normalized_type]
    climate_meta = infer_livestock_climate_profile(
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        climate_profile=climate_profile,
        auto_fetch_elevation=auto_fetch_elevation,
        cache_dir=cache_dir,
    )
    extreme = float(base["extreme"])
    source_notes = ["Thornton et al. (2021) Table 1 operational thresholds."]
    if climate_meta["applied"] == "tropical":
        tropical_extreme = LIVESTOCK_THI_TROPICAL_EXTREME_THRESHOLDS.get(base["species_group"])
        if tropical_extreme is not None and tropical_extreme > extreme:
            extreme = float(tropical_extreme)
            source_notes.append(
                "Tropical extreme threshold adjusted using Thornton et al. (2021) Table 2."
            )

    thresholds = _normalize_thresholds(
        {
            "none_max": float(base["moderate"]),
            "mild_max": float(base["high"]),
            "moderate_max": extreme,
        }
    )
    return {
        "livestock_type": normalized_type,
        "label": str(base["label"]),
        "species_group": str(base["species_group"]),
        "climate_profile_requested": climate_meta["requested"],
        "climate_profile_applied": climate_meta["applied"],
        "climate_profile_reason": climate_meta["reason"],
        "lat": climate_meta["lat"],
        "lon": climate_meta["lon"],
        "elevation_m": climate_meta["elevation_m"],
        "elevation_source": climate_meta["elevation_source"],
        "thresholds": thresholds,
        "source_notes": source_notes,
    }


def build_thi_hazard_thresholds(
    *,
    livestock_type: str | None = DEFAULT_LIVESTOCK_TYPE,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
) -> dict[str, tuple[float | None, float | None]]:
    profile = resolve_thi_profile(
        livestock_type=livestock_type,
        climate_profile=climate_profile,
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        auto_fetch_elevation=auto_fetch_elevation,
        cache_dir=cache_dir,
    )
    thresholds = profile["thresholds"]
    return {
        "none": (None, thresholds["none_max"]),
        "mild": (thresholds["none_max"], thresholds["mild_max"]),
        "moderate": (thresholds["mild_max"], thresholds["moderate_max"]),
        "severe": (thresholds["moderate_max"], None),
    }


def _resolve_temperature_series(
    frame: pd.DataFrame,
    *,
    temp_col: str | None = None,
    tmax_col: str = "tmax",
    tmin_col: str = "tmin",
) -> tuple[pd.Series, str]:
    if temp_col and temp_col in frame.columns:
        return pd.to_numeric(frame[temp_col], errors="coerce"), temp_col

    for candidate in _MEAN_TEMP_CANDIDATES:
        if candidate in frame.columns:
            return pd.to_numeric(frame[candidate], errors="coerce"), candidate

    if tmax_col in frame.columns and tmin_col in frame.columns:
        tmax = pd.to_numeric(frame[tmax_col], errors="coerce")
        tmin = pd.to_numeric(frame[tmin_col], errors="coerce")
        return ((tmax + tmin) / 2.0), f"derived_from_{tmax_col}_{tmin_col}"

    raise ValueError(
        "THI needs mean temperature column or both tmax and tmin so mean daily temperature can be derived."
    )


def _profile_or_thresholds_metadata(
    *,
    thresholds: Mapping[str, float] | None,
    livestock_type: str | None,
    climate_profile: str | None,
    lat: float | None,
    lon: float | None,
    elevation_m: float | None,
    auto_fetch_elevation: bool,
    cache_dir: str | None,
) -> dict[str, Any]:
    if thresholds is not None:
        return {
            "livestock_type": _normalize_livestock_type(livestock_type),
            "label": LIVESTOCK_THI_BASE_PROFILES[_normalize_livestock_type(livestock_type)]["label"],
            "species_group": LIVESTOCK_THI_BASE_PROFILES[_normalize_livestock_type(livestock_type)]["species_group"],
            "climate_profile_requested": _normalize_climate_profile(climate_profile),
            "climate_profile_applied": _normalize_climate_profile(climate_profile),
            "climate_profile_reason": "custom_threshold_override",
            "lat": None if lat is None else float(lat),
            "lon": None if lon is None else float(lon),
            "elevation_m": None if elevation_m is None else float(elevation_m),
            "elevation_source": "user" if elevation_m is not None else None,
            "thresholds": _normalize_thresholds(thresholds),
            "source_notes": ["Custom THI thresholds override livestock profile defaults."],
        }
    return resolve_thi_profile(
        livestock_type=livestock_type,
        climate_profile=climate_profile,
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        auto_fetch_elevation=auto_fetch_elevation,
        cache_dir=cache_dir,
    )


def compute_daily_thi(
    frame: pd.DataFrame,
    *,
    date_col: str = "date",
    humidity_col: str = "humidity",
    temp_col: str | None = None,
    tmax_col: str = "tmax",
    tmin_col: str = "tmin",
    thresholds: Mapping[str, float] | None = None,
    livestock_type: str | None = DEFAULT_LIVESTOCK_TYPE,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Compute daily livestock THI from air temperature and relative humidity."""
    if date_col not in frame.columns:
        raise ValueError(f"Missing required date column: {date_col}")
    if humidity_col not in frame.columns:
        raise ValueError(
            f"Missing required humidity column: {humidity_col}. THI workflow needs relative humidity."
        )

    profile_meta = _profile_or_thresholds_metadata(
        thresholds=thresholds,
        livestock_type=livestock_type,
        climate_profile=climate_profile,
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        auto_fetch_elevation=auto_fetch_elevation,
        cache_dir=cache_dir,
    )
    active_thresholds = dict(profile_meta["thresholds"])
    out = frame.copy()
    out[date_col] = pd.to_datetime(out[date_col])
    out["humidity"] = pd.to_numeric(out[humidity_col], errors="coerce")
    temperature_c, temperature_source = _resolve_temperature_series(
        out,
        temp_col=temp_col,
        tmax_col=tmax_col,
        tmin_col=tmin_col,
    )
    out["temperature_c"] = pd.to_numeric(temperature_c, errors="coerce")

    valid_humidity = out["humidity"].between(0.0, 100.0) | out["humidity"].isna()
    if not bool(valid_humidity.all()):
        raise ValueError("Humidity values for THI must stay within 0..100 percent.")

    out["thi"] = (
        (1.8 * out["temperature_c"] + 32.0)
        - ((0.55 - 0.0055 * out["humidity"]) * ((1.8 * out["temperature_c"]) - 26.0))
    )
    out["thi_class"] = classify_thi_values(out["thi"], thresholds=active_thresholds)
    out = out.sort_values(date_col).reset_index(drop=True)
    out.attrs["thi_metadata"] = {
        "metric": "livestock_thi",
        "formula": THI_FORMULA,
        "temperature_source": temperature_source,
        "humidity_source_column": humidity_col,
        "thresholds": active_thresholds,
        "livestock_type": profile_meta["livestock_type"],
        "livestock_label": profile_meta["label"],
        "species_group": profile_meta["species_group"],
        "climate_profile_requested": profile_meta["climate_profile_requested"],
        "climate_profile_applied": profile_meta["climate_profile_applied"],
        "climate_profile_reason": profile_meta["climate_profile_reason"],
        "elevation_m": profile_meta["elevation_m"],
        "elevation_source": profile_meta["elevation_source"],
        "notes": list(profile_meta["source_notes"]) + [
            "Relative humidity required; future projection sources without stable humidity path remain unsupported."
        ],
    }
    return out


def classify_thi_values(
    values: Iterable[float] | pd.Series,
    *,
    thresholds: Mapping[str, float] | None = None,
    livestock_type: str | None = DEFAULT_LIVESTOCK_TYPE,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
) -> pd.Series:
    """Classify THI values into livestock-specific stress bands."""
    if thresholds is None:
        thresholds = resolve_thi_profile(
            livestock_type=livestock_type,
            climate_profile=climate_profile,
            lat=lat,
            lon=lon,
            elevation_m=elevation_m,
            auto_fetch_elevation=auto_fetch_elevation,
            cache_dir=cache_dir,
        )["thresholds"]
    active_thresholds = _normalize_thresholds(thresholds)
    series = pd.Series(values)
    classes = pd.Series(index=series.index, dtype="object")
    classes[series.isna()] = None
    classes[series <= active_thresholds["none_max"]] = "none"
    classes[(series > active_thresholds["none_max"]) & (series <= active_thresholds["mild_max"])] = "mild"
    classes[
        (series > active_thresholds["mild_max"])
        & (series <= active_thresholds["moderate_max"])
    ] = "moderate"
    classes[series > active_thresholds["moderate_max"]] = "severe"
    return classes


def summarize_thi_periods(
    frame: pd.DataFrame,
    *,
    date_col: str = "date",
    thi_col: str = "thi",
    thresholds: Mapping[str, float] | None = None,
    livestock_type: str | None = DEFAULT_LIVESTOCK_TYPE,
    climate_profile: str | None = DEFAULT_LIVESTOCK_CLIMATE_PROFILE,
    lat: float | None = None,
    lon: float | None = None,
    elevation_m: float | None = None,
    auto_fetch_elevation: bool = False,
    cache_dir: str | None = None,
    freq: str = "YS",
) -> pd.DataFrame:
    """Summarize THI into period means, maxima, and stress-band day counts."""
    if date_col not in frame.columns or thi_col not in frame.columns:
        raise ValueError(f"THI summary needs columns {date_col!r} and {thi_col!r}.")

    profile_meta = _profile_or_thresholds_metadata(
        thresholds=thresholds,
        livestock_type=livestock_type,
        climate_profile=climate_profile,
        lat=lat,
        lon=lon,
        elevation_m=elevation_m,
        auto_fetch_elevation=auto_fetch_elevation,
        cache_dir=cache_dir,
    )
    active_thresholds = dict(profile_meta["thresholds"])
    working = frame[[date_col, thi_col]].copy()
    working[date_col] = pd.to_datetime(working[date_col])
    working[thi_col] = pd.to_numeric(working[thi_col], errors="coerce")
    working["thi_class"] = classify_thi_values(working[thi_col], thresholds=active_thresholds)
    grouped = working.set_index(date_col).groupby(pd.Grouper(freq=freq))
    rows: list[dict[str, object]] = []
    for period_start, group in grouped:
        if pd.isna(period_start):
            continue
        class_counts = group["thi_class"].value_counts(dropna=True)
        rows.append(
            {
                "period_start": pd.Timestamp(period_start).strftime("%Y-%m-%d"),
                "days_total": int(group[thi_col].notna().sum()),
                "thi_mean": round(float(group[thi_col].mean()), 3) if group[thi_col].notna().any() else None,
                "thi_max": round(float(group[thi_col].max()), 3) if group[thi_col].notna().any() else None,
                "days_none": int(class_counts.get("none", 0)),
                "days_mild": int(class_counts.get("mild", 0)),
                "days_moderate": int(class_counts.get("moderate", 0)),
                "days_severe": int(class_counts.get("severe", 0)),
                "days_stress": int(class_counts.get("mild", 0) + class_counts.get("moderate", 0) + class_counts.get("severe", 0)),
            }
        )
    result = pd.DataFrame(rows)
    result.attrs["thi_metadata"] = {
        "metric": "livestock_thi",
        "thresholds": active_thresholds,
        "frequency": freq,
        "livestock_type": profile_meta["livestock_type"],
        "livestock_label": profile_meta["label"],
        "climate_profile_applied": profile_meta["climate_profile_applied"],
        "summary_note": "Period summaries report mean/max THI plus day counts by livestock stress band.",
    }
    return result


def describe_thi_source_support() -> dict[str, str]:
    """Return current source-support notes for THI workflow."""
    return dict(_THI_SOURCE_SUPPORT)


def describe_thi_method() -> dict[str, Any]:
    """Return current operational THI method, thresholds, and source-support notes."""
    profiles: dict[str, dict[str, Any]] = {}
    for livestock_type in list_thi_livestock_profiles():
        temperate = resolve_thi_profile(
            livestock_type=livestock_type,
            climate_profile="temperate",
        )
        tropical = resolve_thi_profile(
            livestock_type=livestock_type,
            climate_profile="tropical",
        )
        profiles[livestock_type] = {
            "label": temperate["label"],
            "species_group": temperate["species_group"],
            "thresholds_temperate": dict(temperate["thresholds"]),
            "thresholds_tropical": dict(tropical["thresholds"]),
        }

    return {
        "metric": "livestock_thi",
        "formula": THI_FORMULA,
        "default_daily_workflow": "daily mean temperature plus daily relative humidity",
        "temperature_input": {
            "preferred_mean_columns": list(_MEAN_TEMP_CANDIDATES),
            "fallback_rule": "derive mean daily temperature from (tmax + tmin) / 2",
        },
        "humidity_input": {
            "required": True,
            "type": "daily relative humidity in percent",
            "valid_range_percent": [0.0, 100.0],
        },
        "climate_profile_logic": {
            "options": ["auto", "temperate", "tropical"],
            "auto_rule": (
                "auto uses latitude first; tropical sites at or above highland elevation use "
                "temperate thresholds as highland proxy"
            ),
            "tropics_latitude_deg": TROPICS_LATITUDE_DEG,
            "highland_elevation_m": HIGHLAND_ELEVATION_M,
        },
        "threshold_reference": (
            "Thornton et al. (2021) Table 1 operational thresholds; "
            "tropical extreme-threshold adjustments from Table 2 when applicable."
        ),
        "method_rationale": {
            "default_choice": (
                "Keep daily mean-temperature THI as toolkit default because current projection-facing "
                "literature and gridded-source support are strongest for daily average temperature plus "
                "relative humidity, while consistent paired peak-heat humidity pathways are not yet "
                "stable across toolkit sources."
            ),
            "max_temperature_screening_status": (
                "Not default. Potential future screening companion, but not yet promoted because "
                "daily Tmax combined with non-coincident RH can overstate or distort heat-stress signal."
            ),
        },
        "interpretation_caveats": [
            "Species-group operational defaults, not breed-resolved physiology.",
            "Toolkit does not currently distinguish Bos indicus, Bos taurus, Sanga, or crossbred cattle within a livestock type.",
            "Climate-profile auto logic is coarse location proxy, not direct animal adaptation measurement.",
            "For locally adapted breeds or project-specific veterinary guidance, treat package THI bands as screening defaults and consider custom threshold override.",
        ],
        "references": [
            {
                "short": "Thornton et al. 2021",
                "doi": "10.1111/gcb.15825",
                "notes": (
                    "Uses THI from daily temperature and relative humidity for global livestock heat-stress "
                    "projection work; supports current default workflow and species-specific threshold table."
                ),
            },
            {
                "short": "Thom 1959 / NRC 1971 equivalence",
                "doi": None,
                "notes": (
                    "Thornton et al. summarize Thom (1959) and algebraically equivalent NRC (1971) THI forms; "
                    "toolkit formula follows this widely used family."
                ),
            },
        ],
        "profiles": profiles,
        "source_support": describe_thi_source_support(),
    }


__all__ = [
    "DEFAULT_LIVESTOCK_CLIMATE_PROFILE",
    "DEFAULT_LIVESTOCK_TYPE",
    "HIGHLAND_ELEVATION_M",
    "TROPICS_LATITUDE_DEG",
    "THI_FORMULA",
    "build_thi_hazard_thresholds",
    "classify_thi_values",
    "compute_daily_thi",
    "describe_thi_method",
    "describe_thi_source_support",
    "infer_livestock_climate_profile",
    "list_thi_livestock_profiles",
    "resolve_thi_profile",
    "summarize_thi_periods",
]
