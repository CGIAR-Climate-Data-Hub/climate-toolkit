"""Internal preprocess helpers.

This package is importable and tested under installed-package shape, but it is
not end-user stable CLI surface. Prefer top-level APIs or public console
scripts such as ``climate-toolkit-fetch`` for user workflows.
"""

__all__ = ["preprocess_data", "preprocess_transformed_data"]
__all__ += ["run_preprocess_data", "run_preprocess_transformed_data"]


def run_preprocess_data(*args, **kwargs):
    from .preprocess_data import preprocess_data as _preprocess_data

    return _preprocess_data(*args, **kwargs)


def run_preprocess_transformed_data(*args, **kwargs):
    from .preprocess_data import (
        preprocess_transformed_data as _preprocess_transformed_data,
    )

    return _preprocess_transformed_data(*args, **kwargs)


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


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
