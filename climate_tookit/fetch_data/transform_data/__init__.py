"""Internal transform helpers.

This package is importable and tested under installed-package shape, but it is
not end-user stable CLI surface. Prefer top-level APIs or public console
scripts for user workflows.
"""

__all__ = ["default_variables", "load_variable_mappings", "transform_data", "run_transform_data"]


def run_transform_data(*args, **kwargs):
    from .transform_data import transform_data as _transform_data

    return _transform_data(*args, **kwargs)


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


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
