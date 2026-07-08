"""Lazy exports for preprocess_data package."""

__all__ = ["preprocess_data", "preprocess_transformed_data"]


def __getattr__(name):
    if name in {"preprocess_data", "preprocess_transformed_data"}:
        from .preprocess_data import (
            preprocess_data as _preprocess_data,
            preprocess_transformed_data as _preprocess_transformed_data,
        )

        exports = {
            "preprocess_data": _preprocess_data,
            "preprocess_transformed_data": _preprocess_transformed_data,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
