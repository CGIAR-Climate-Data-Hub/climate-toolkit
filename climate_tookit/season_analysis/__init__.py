"""Season-analysis public subpackage API."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "detect_onset_cessation",
    "fetch_and_analyze_years",
    "fetch_and_analyze_years_fixed",
    "parse_fixed_seasons",
]


def __getattr__(name: str):
    if name in {
        "detect_onset_cessation",
        "fetch_and_analyze_years",
        "fetch_and_analyze_years_fixed",
        "parse_fixed_seasons",
    }:
        module = import_module(".seasons", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
