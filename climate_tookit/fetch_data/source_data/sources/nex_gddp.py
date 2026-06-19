"""
Real NEX-GDDP adapter.

This module is main package entry point for NEX-GDDP access. It delegates to
Earth Engine + Xee implementation in `nex_gddp_xee.py` and exposes stable
symbols used elsewhere in toolkit.
"""

from __future__ import annotations

from .nex_gddp_xee import (
    DEFAULT_DATASET_VERSION,
    SCENARIO_MAPPING,
    DownloadData,
    _normalize_scenario,
    _validate_period_against_scenario,
)

AFRICA_CMIP6_GUIDANCE_URL = (
    "https://cgiar-climate-data-hub.github.io/wikis/aaa-atlas/"
    "african-cmip6-ensembling/"
)
AFRICA_CMIP6_POLICY_VERSION = "AAA Atlas v0.3-validated"
AFRICA_CMIP6_REALIZATION = "r1i1p1f1"
POLICY_PROFILE_CHOICES = ["default", "regional_fast"]
POLICY_PROFILE_HELP = (
    "Ensemble policy profile. 'regional_fast' uses codified regional screening "
    "subsets for AFR-EAF, AFR-WAF, and ANDES. These are provisional fast pools "
    "for screening only and are accompanied by runtime warnings/disclaimers."
)

AVAILABLE_MODELS = [
    "ACCESS-CM2",
    "ACCESS-ESM1-5",
    "CanESM5",
    "CMCC-ESM2",
    "EC-Earth3",
    "EC-Earth3-Veg-LR",
    "GFDL-ESM4",
    "INM-CM4-8",
    "INM-CM5-0",
    "IPSL-CM6A-LR",
    "KACE-1-0-G",
    "MIROC6",
    "MPI-ESM1-2-HR",
    "MPI-ESM1-2-LR",
    "MRI-ESM2-0",
    "NorESM2-LM",
    "NorESM2-MM",
    "TaiESM1",
]

AFR13_EXCLUDED_MODELS = [
    "CanESM5",
    "INM-CM4-8",
    "INM-CM5-0",
    "KACE-1-0-G",
    "TaiESM1",
]

AFRICA_DEFAULT_ENSEMBLE_MODELS = [
    model for model in AVAILABLE_MODELS if model not in AFR13_EXCLUDED_MODELS
]

AFR_EAF_FAST_PROVISIONAL_MODELS = [
    "EC-Earth3-Veg-LR",
    "CanESM5",
    "INM-CM5-0",
    "IPSL-CM6A-LR",
    "MPI-ESM1-2-HR",
]

AFR_WAF_FAST_WARNING_MODELS = [
    "INM-CM5-0",
    "IPSL-CM6A-LR",
    "TaiESM1",
]

ANDES_FAST_WARNING_MODELS = [
    "NorESM2-LM",
    "MPI-ESM1-2-HR",
    "EC-Earth3",
    "MRI-ESM2-0",
    "KACE-1-0-G",
]

REGIONAL_FAST_MEMO_PATHS = {
    "AFR-EAF": "analysis/nex_regional_fast_pool_memo_eaf.md",
    "AFR-WAF": "analysis/nex_regional_fast_pool_memo_waf.md",
    "ANDES": "analysis/nex_regional_fast_pool_memo_andes.md",
}


def is_africa_coordinate(lat: float, lon: float) -> bool:
    return -35.0 <= lat <= 38.0 and -20.0 <= lon <= 55.0


def africa_subregion_for_coordinate(lat: float, lon: float) -> str | None:
    """Operational broad-box mapping for African NEX guidance metadata.

    These are intentionally simple boxes used to attach AAA Atlas regional
    context to point workflows. They are not a GIS-precise implementation of
    AR6 polygons.
    """
    if not is_africa_coordinate(lat, lon):
        return None
    if -26.5 <= lat <= -10.0 and 42.0 <= lon <= 52.0:
        return "AFR-MDG"
    if -5.0 <= lat <= 18.0 and 28.0 <= lon <= 52.0:
        return "AFR-EAF"
    if 0.0 <= lat <= 22.0 and -20.0 <= lon <= 15.0:
        return "AFR-WAF"
    if -12.0 <= lat <= 12.0 and 8.0 <= lon <= 32.0:
        return "AFR-CAF"
    if -35.0 <= lat <= -15.0 and 10.0 <= lon <= 28.0:
        return "AFR-WSAF"
    if -35.0 <= lat <= -10.0 and 28.0 <= lon <= 43.0:
        return "AFR-ESAF"
    return "AFR-13"


def is_andes_coordinate(lat: float, lon: float) -> bool:
    """Operational broad-box mapping for Andes-facing screening context."""
    return -35.0 <= lat <= 15.0 and -81.0 <= lon <= -65.0


def policy_runtime_messages(policy: dict) -> list[str]:
    lines: list[str] = []
    if policy.get("warning_level"):
        lines.append(
            f"{policy.get('warning_level').upper()}: {policy.get('policy_label')} "
            "is provisional screening subset, not full structural uncertainty envelope."
        )
    disclaimer = policy.get("runtime_disclaimer")
    if disclaimer:
        lines.append(str(disclaimer))
    memo = policy.get("documentation_memo")
    if memo:
        lines.append(f"Decision memo: {memo}")
    if policy.get("policy_fallback"):
        notes = list(policy.get("notes") or [])
        if notes:
            lines.append(notes[-1])
    return lines


def resolve_ensemble_policy_for_location(
    location_coord,
    models=None,
    exclude_models=None,
    policy_profile=None,
):
    lat, lon = location_coord
    subregion = africa_subregion_for_coordinate(lat, lon)
    andes_context = "ANDES" if is_andes_coordinate(lat, lon) else None

    if models:
        active = list(models)
        policy = {
            "policy_id": "USER_SUPPLIED",
            "policy_label": "User-supplied model list",
            "selection_scope": "manual_override",
            "regional_context": subregion or andes_context,
            "guidance_url": AFRICA_CMIP6_GUIDANCE_URL if subregion else None,
            "guidance_version": AFRICA_CMIP6_POLICY_VERSION if subregion else None,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": subregion == "AFR-EAF",
            "models": active,
            "documentation_memo": REGIONAL_FAST_MEMO_PATHS.get(subregion or andes_context),
            "notes": (
                ["Regional African CMIP6 guidance metadata attached, but explicit user model list preserved."]
                if subregion else
                ["Explicit user model list preserved."]
            ),
        }
    elif policy_profile == "regional_fast" and subregion == "AFR-EAF":
        active = list(AFR_EAF_FAST_PROVISIONAL_MODELS)
        policy = {
            "policy_id": "AFR-EAF-FAST-PROVISIONAL-V2",
            "policy_label": "East/Horn Africa provisional fast shortlist",
            "selection_scope": "regional_fast_provisional",
            "regional_context": subregion,
            "guidance_url": AFRICA_CMIP6_GUIDANCE_URL,
            "guidance_version": AFRICA_CMIP6_POLICY_VERSION,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": True,
            "models": active,
            "documentation_memo": REGIONAL_FAST_MEMO_PATHS["AFR-EAF"],
            "warning_level": "warning",
            "runtime_disclaimer": (
                "Two-source regional fast pool for mixed precipitation/temperature East Africa screening. "
                "Use for rapid regional scoping; retain broader pools for uncertainty-sensitive work."
            ),
            "notes": [
                "This provisional fast shortlist is source-backed only for AFR-EAF/Horn context.",
                "Current v2 set reflects two-source regional evidence: IGAD rainfall evaluation plus East Africa NEX-GDDP evaluation.",
                "Use for fast regional screening, not as final structural uncertainty envelope.",
            ],
            "evidence_confidence": "medium",
            "comparability_class": "strict_proxy",
        }
    elif policy_profile == "regional_fast" and subregion == "AFR-WAF":
        active = list(AFR_WAF_FAST_WARNING_MODELS)
        policy = {
            "policy_id": "AFR-WAF-FAST-WARNING",
            "policy_label": "West Africa extremes-weighted fast watchlist",
            "selection_scope": "regional_fast_warning_watchlist",
            "regional_context": subregion,
            "guidance_url": None,
            "guidance_version": None,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": False,
            "models": active,
            "documentation_memo": REGIONAL_FAST_MEMO_PATHS["AFR-WAF"],
            "warning_level": "warning",
            "runtime_disclaimer": (
                "West Africa fast pool is extremes-focused watchlist built from limited monsoon-extremes evidence. "
                "Do not treat as general seasonality/onset pool."
            ),
            "notes": [
                "Evidence currently supports an extremes-oriented West Africa watchlist, not a full regional fast pool.",
                "Subset is intentionally small and should be used only for rapid exploratory screening.",
            ],
            "evidence_confidence": "low",
            "comparability_class": "strict_proxy",
        }
    elif policy_profile == "regional_fast" and andes_context == "ANDES":
        active = list(ANDES_FAST_WARNING_MODELS)
        policy = {
            "policy_id": "ANDES-FAST-WARNING",
            "policy_label": "Andes screening watchlist",
            "selection_scope": "regional_fast_warning_watchlist",
            "regional_context": andes_context,
            "guidance_url": None,
            "guidance_version": None,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": False,
            "models": active,
            "documentation_memo": REGIONAL_FAST_MEMO_PATHS["ANDES"],
            "warning_level": "warning",
            "runtime_disclaimer": (
                "Andes fast pool is screening watchlist built from limited Andes-specific annual-cycle evidence "
                "plus broader South America shortlist support. Not final Andes pool."
            ),
            "notes": [
                "Current Andes evidence is sufficient for a screening watchlist, not a final regional fast pool.",
                "Use for rapid exploratory screening and revisit with broader pools for uncertainty-sensitive work.",
            ],
            "evidence_confidence": "low",
            "comparability_class": "strict_proxy",
        }
    elif subregion:
        active = list(AFRICA_DEFAULT_ENSEMBLE_MODELS)
        policy = {
            "policy_id": "AFR-13",
            "policy_label": "African continental default (AFR-13)",
            "selection_scope": "auto_africa_default",
            "regional_context": subregion,
            "guidance_url": AFRICA_CMIP6_GUIDANCE_URL,
            "guidance_version": AFRICA_CMIP6_POLICY_VERSION,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": subregion == "AFR-EAF",
            "models": active,
            "excluded_models": list(AFR13_EXCLUDED_MODELS),
            "notes": [
                "Continental African default excludes CanESM5, INM-CM4-8, INM-CM5-0, KACE-1-0-G, and TaiESM1.",
                "Regional context is attached for interpretation; Horn/East Africa MAM rainfall needs paradox caution.",
            ],
            "evidence_confidence": "medium",
            "comparability_class": "strict_proxy",
        }
    else:
        active = list(AVAILABLE_MODELS)
        policy = {
            "policy_id": "FULL-18",
            "policy_label": "Full 18-model v1.2-comparable proxy pool",
            "selection_scope": "default_full_pool",
            "regional_context": None,
            "guidance_url": None,
            "guidance_version": None,
            "realization": AFRICA_CMIP6_REALIZATION,
            "east_african_paradox_caution": False,
            "models": active,
            "notes": [
                "Non-African location uses full 18-model v1.2-comparable proxy pool by default.",
                "Additional NEX-GDDP v1.1 models exist in GEE, but are excluded from this default pool because they do not match the intended v1.2-comparable realization screen.",
            ],
            "evidence_confidence": "high",
            "comparability_class": "strict_proxy",
        }

    if (
        policy_profile == "regional_fast"
        and subregion not in {"AFR-EAF", "AFR-WAF"}
        and andes_context != "ANDES"
        and not models
    ):
        notes = list(policy.get("notes") or [])
        notes.append(
            f"Requested policy_profile=regional_fast, but no source-backed fast shortlist is codified yet for {subregion or 'this location'}; using fallback policy."
        )
        policy = {
            **policy,
            "notes": notes,
            "requested_policy_profile": policy_profile,
            "policy_fallback": True,
        }

    if exclude_models:
        excluded = {model.upper() for model in exclude_models}
        active = [model for model in active if model.upper() not in excluded]
        policy = {
            **policy,
            "models": active,
            "exclude_models_applied": list(exclude_models),
        }
    return policy


def default_ensemble_models_for_location(
    location_coord,
    models=None,
    exclude_models=None,
    policy_profile=None,
):
    return resolve_ensemble_policy_for_location(
        location_coord,
        models=models,
        exclude_models=exclude_models,
        policy_profile=policy_profile,
    )["models"]

__all__ = [
    "AFR13_EXCLUDED_MODELS",
    "AFR_EAF_FAST_PROVISIONAL_MODELS",
    "AFR_WAF_FAST_WARNING_MODELS",
    "AFRICA_CMIP6_GUIDANCE_URL",
    "AFRICA_CMIP6_POLICY_VERSION",
    "AFRICA_CMIP6_REALIZATION",
    "ANDES_FAST_WARNING_MODELS",
    "AVAILABLE_MODELS",
    "AFRICA_DEFAULT_ENSEMBLE_MODELS",
    "DEFAULT_DATASET_VERSION",
    "POLICY_PROFILE_CHOICES",
    "POLICY_PROFILE_HELP",
    "REGIONAL_FAST_MEMO_PATHS",
    "SCENARIO_MAPPING",
    "DownloadData",
    "africa_subregion_for_coordinate",
    "default_ensemble_models_for_location",
    "is_africa_coordinate",
    "is_andes_coordinate",
    "policy_runtime_messages",
    "resolve_ensemble_policy_for_location",
    "_normalize_scenario",
    "_validate_period_against_scenario",
]
