"""Lazy exports for source_data package."""

from importlib import import_module

__all__ = ["SourceData"]


def __getattr__(name):
    if name in {"source_data", "sources"}:
        return import_module(f"{__name__}.{name}")
    if name == "SourceData":
        from .source_data import SourceData as _SourceData

        return _SourceData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
