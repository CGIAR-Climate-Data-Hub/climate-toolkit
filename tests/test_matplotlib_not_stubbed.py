"""Regression guard: the real matplotlib must survive the test session.

Some test modules install a lightweight ``matplotlib`` stub in ``sys.modules``
during collection. If such a stub leaks, ``import matplotlib`` here returns the
stub (which lacks ``matplotlib.use``) and this test fails. The
``pytest_collection_finish`` hook in ``tests/conftest.py`` sweeps leaked stubs,
so with real matplotlib installed this should always pass.
"""

import unittest


class MatplotlibNotStubbedTests(unittest.TestCase):
    def test_real_matplotlib_is_importable(self):
        import matplotlib

        self.assertTrue(
            hasattr(matplotlib, "use"),
            "matplotlib is a stub (leaked from another test) rather than the real module",
        )
        # The real module exposes a filesystem path; the hand-built stub does not.
        self.assertTrue(getattr(matplotlib, "__file__", None))


if __name__ == "__main__":
    unittest.main()
