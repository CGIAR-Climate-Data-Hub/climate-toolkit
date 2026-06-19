"""Climate statistics public subpackage API."""

from __future__ import annotations

from importlib import import_module

__all__ = ["analyze_climate_statistics"]


def __getattr__(name: str):
    if name == "analyze_climate_statistics":
        module = import_module(".statistics", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
