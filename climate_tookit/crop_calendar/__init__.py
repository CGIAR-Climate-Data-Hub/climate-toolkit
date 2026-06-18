"""Crop-calendar registry and lookup helpers."""

from __future__ import annotations

__all__ = [
    "DATA_SOURCE_USED_LABELS",
    "CALENDAR_SYSTEM_CHOICES",
    "GGCMICalendarAssetMissingError",
    "CropSupport",
    "asset_available",
    "asset_paths",
    "build_fixed_season_tokens",
    "calendar_supported_crop_names",
    "extract_point_calendar",
    "get_crop_support",
    "load_calendar_manifest",
    "load_calendar_table",
    "normalize_crop_name",
    "resolve_calendar_preset",
    "supported_crop_names",
    "threshold_supported_crop_names",
]


def __getattr__(name: str):
    if name in {
        "DATA_SOURCE_USED_LABELS",
        "CALENDAR_SYSTEM_CHOICES",
        "GGCMICalendarAssetMissingError",
        "asset_available",
        "asset_paths",
        "build_fixed_season_tokens",
        "extract_point_calendar",
        "load_calendar_manifest",
        "load_calendar_table",
        "resolve_calendar_preset",
    }:
        from .ggcmi import (
            CALENDAR_SYSTEM_CHOICES as _CALENDAR_SYSTEM_CHOICES,
            DATA_SOURCE_USED_LABELS as _DATA_SOURCE_USED_LABELS,
            GGCMICalendarAssetMissingError as _GGCMICalendarAssetMissingError,
            asset_available as _asset_available,
            asset_paths as _asset_paths,
            build_fixed_season_tokens as _build_fixed_season_tokens,
            extract_point_calendar as _extract_point_calendar,
            load_calendar_manifest as _load_calendar_manifest,
            load_calendar_table as _load_calendar_table,
            resolve_calendar_preset as _resolve_calendar_preset,
        )

        exports = {
            "DATA_SOURCE_USED_LABELS": _DATA_SOURCE_USED_LABELS,
            "CALENDAR_SYSTEM_CHOICES": _CALENDAR_SYSTEM_CHOICES,
            "GGCMICalendarAssetMissingError": _GGCMICalendarAssetMissingError,
            "asset_available": _asset_available,
            "asset_paths": _asset_paths,
            "build_fixed_season_tokens": _build_fixed_season_tokens,
            "extract_point_calendar": _extract_point_calendar,
            "load_calendar_manifest": _load_calendar_manifest,
            "load_calendar_table": _load_calendar_table,
            "resolve_calendar_preset": _resolve_calendar_preset,
        }
        return exports[name]
    if name in {
        "CropSupport",
        "calendar_supported_crop_names",
        "get_crop_support",
        "normalize_crop_name",
        "supported_crop_names",
        "threshold_supported_crop_names",
    }:
        from .registry import (
            CropSupport as _CropSupport,
            calendar_supported_crop_names as _calendar_supported_crop_names,
            get_crop_support as _get_crop_support,
            normalize_crop_name as _normalize_crop_name,
            supported_crop_names as _supported_crop_names,
            threshold_supported_crop_names as _threshold_supported_crop_names,
        )

        exports = {
            "CropSupport": _CropSupport,
            "calendar_supported_crop_names": _calendar_supported_crop_names,
            "get_crop_support": _get_crop_support,
            "normalize_crop_name": _normalize_crop_name,
            "supported_crop_names": _supported_crop_names,
            "threshold_supported_crop_names": _threshold_supported_crop_names,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
