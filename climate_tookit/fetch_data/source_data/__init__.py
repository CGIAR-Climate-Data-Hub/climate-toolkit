"""Internal source-data helpers.

This package remains importable for toolkit internals and advanced development
workflows, but it is not stable end-user API surface.
"""

__all__ = ["SourceData"]


def __getattr__(name):
    if name == "SourceData":
        from .source_data import SourceData as _SourceData

        return _SourceData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
