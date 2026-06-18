"""Period-comparison public subpackage API."""

from __future__ import annotations

from importlib import import_module

__all__ = ["compare"]


def __getattr__(name: str):
    if name == "compare":
        module = import_module(".periods", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
