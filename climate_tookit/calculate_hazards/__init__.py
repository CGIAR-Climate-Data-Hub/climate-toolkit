"""Hazard analysis public subpackage API."""

from __future__ import annotations

from importlib import import_module

__all__ = ["calculate_hazards"]


def __getattr__(name: str):
    if name == "calculate_hazards":
        module = import_module(".hazards", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
