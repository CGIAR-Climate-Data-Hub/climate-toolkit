"""Import/route smoke test for the optional FastAPI service layer.

Skips cleanly when the ``api`` extra is not installed (e.g. the default CI
sync), so it never breaks the base pipeline while still validating the app
wiring for anyone who installs ``.[api]``.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ApiSmokeTests(unittest.TestCase):
    def test_app_builds_and_exposes_core_routes(self):
        try:
            import fastapi  # noqa: F401
            import jinja2  # noqa: F401
        except ImportError:
            self.skipTest("api extra not installed; run `uv sync --extra api`")

        # Other tests install a lightweight ``matplotlib`` stub in sys.modules
        # and do not remove it; apis.main needs the real module for
        # ``matplotlib.use("Agg")``, so drop any stub before importing.
        import matplotlib

        if not hasattr(matplotlib, "use"):
            for name in [m for m in sys.modules if m == "matplotlib" or m.startswith("matplotlib.")]:
                del sys.modules[name]

        # apis/ is run from the repo root, not installed as a package.
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        from apis.main import app

        # The OpenAPI schema flattens mounted/included routers into one path map.
        paths = set(app.openapi()["paths"])
        # Health probe used by the container HEALTHCHECK, HTML landing page,
        # and at least one JSON API route under the /api/v1 prefix.
        self.assertIn("/health", paths)
        self.assertIn("/", paths)
        self.assertTrue(
            any(path.startswith("/api/v1/") for path in paths),
            f"expected /api/v1/* routes, got: {sorted(paths)}",
        )


if __name__ == "__main__":
    unittest.main()
