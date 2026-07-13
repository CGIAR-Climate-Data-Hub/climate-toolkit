"""Shared pytest hooks for the test suite."""

import sys
from importlib.machinery import PathFinder


def pytest_collection_finish(session):
    """Undo leaked ``matplotlib`` stubs installed during collection.

    Several test modules install a lightweight ``matplotlib`` stub via
    ``sys.modules.setdefault(...)`` at import time so they can import package
    modules without the real dependency. Those stubs are never removed, so they
    shadow the real ``matplotlib`` for any test collected afterwards that
    actually needs it (e.g. code calling ``matplotlib.use``).

    Once collection is done — so every stub-installing module has already used
    its stub — drop the stub, but only when it really is a stub and the real
    ``matplotlib`` is installed on disk. Tests never use matplotlib at run time,
    so removing it here is safe and lets later imports resolve the real module.
    """
    mpl = sys.modules.get("matplotlib")
    if mpl is None or hasattr(mpl, "use"):
        return  # nothing stubbed, or the real module is already loaded
    if PathFinder.find_spec("matplotlib") is None:
        return  # real matplotlib genuinely unavailable; keep the stub
    for name in [m for m in sys.modules if m == "matplotlib" or m.startswith("matplotlib.")]:
        del sys.modules[name]
