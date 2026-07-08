"""Lazy exports for transform_data package."""

__all__ = ["default_variables", "load_variable_mappings", "transform_data"]


def __getattr__(name):
    if name in {"default_variables", "load_variable_mappings", "transform_data"}:
        from .transform_data import (
            default_variables as _default_variables,
            load_variable_mappings as _load_variable_mappings,
            transform_data as _transform_data,
        )

        exports = {
            "default_variables": _default_variables,
            "load_variable_mappings": _load_variable_mappings,
            "transform_data": _transform_data,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
