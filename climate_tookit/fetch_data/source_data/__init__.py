"""Lazy exports for source_data package."""

__all__ = ["SourceData"]


def __getattr__(name):
    if name == "SourceData":
        from .source_data import SourceData as _SourceData

        return _SourceData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
