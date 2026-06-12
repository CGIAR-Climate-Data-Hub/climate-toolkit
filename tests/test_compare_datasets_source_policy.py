import unittest
from unittest import mock

from climate_tookit.compare_datasets.compare_datasets import (
    _validate_source_selection,
    compare_sources,
    main,
)


class CompareDatasetsSourcePolicyTests(unittest.TestCase):
    def test_validate_source_selection_rejects_mixed_nex_and_historical_sources(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_source_selection(["era_5", "nex_gddp"])

        self.assertIn("nex_gddp must be run on its own", str(ctx.exception))

    def test_compare_sources_rejects_mixed_nex_and_other_sources(self):
        with self.assertRaises(ValueError) as ctx:
            compare_sources(
                sources=["nex_gddp", "chirps"],
                lat=-1.286,
                lon=36.817,
                start="2015-01-01",
                end="2015-01-10",
            )

        self.assertIn("nex_gddp must be run on its own", str(ctx.exception))

    def test_main_rejects_mixed_nex_and_other_sources(self):
        argv = [
            "compare_datasets.py",
            "--sources",
            "nex_gddp",
            "chirps",
            "--lat",
            "-1.286",
            "--lon",
            "36.817",
            "--start",
            "2015-01-01",
            "--end",
            "2015-01-10",
        ]

        with mock.patch("sys.argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
