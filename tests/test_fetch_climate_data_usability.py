"""Regression tests for two fetch_climate_data getting-started papercuts.

1. The NASA POWER cache filename is built from the requested variable names.
   With the default (all-variables) set that string overflowed the filesystem's
   per-component length limit, so the first thing a new user tried crashed with
   ``OSError: File name too long``.
2. The Python API only accepted ``ClimateVariable``/``SoilVariable`` enum
   members; passing plain strings raised ``AttributeError: 'str' object has no
   attribute 'name'``.
"""

import unittest
from datetime import date

from climate_toolkit.fetch_data.fetch_data import _coerce_variable_list
from climate_toolkit.fetch_data.source_data.sources.nasa_power import (
    MAX_VARIABLE_FRAGMENT_LEN,
    DownloadData,
)
from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    SoilVariable,
)
from climate_toolkit.fetch_data.source_data.sources.utils.settings import Settings


class NasaPowerCacheFilenameTests(unittest.TestCase):
    def _downloader(self, variables):
        return DownloadData(
            location_coord=(-1.286, 36.817),
            date_from_utc=date(2020, 1, 1),
            date_to_utc=date(2020, 1, 3),
            variables=variables,
            settings=Settings.load(),
            source=ClimateDataset.nasa_power,
            verbose=False,
            cache_dir="outputs/cache",
        )

    def test_large_variable_set_yields_bounded_stable_filename(self):
        # The full climate + soil set is what overflowed the 255-byte limit.
        dl = self._downloader(list(ClimateVariable) + list(SoilVariable))
        data_path, manifest_path = dl._cache_paths()

        # Worst case is the manifest name plus the ``.part`` temp suffix.
        for name in (data_path.name, manifest_path.name + ".part"):
            self.assertLessEqual(len(name.encode("utf-8")), 255)

        # The readable form was too long, so the digest fallback is used...
        self.assertIn("vars_", data_path.name)
        # ...and it is deterministic across calls (so cache hits still work).
        self.assertEqual(dl._cache_paths()[0], data_path)

    def test_different_sets_get_different_fragments(self):
        a = self._downloader(list(ClimateVariable) + list(SoilVariable))._variable_fragment()
        smaller = list(ClimateVariable) + list(SoilVariable)[:-1]
        b = self._downloader(smaller)._variable_fragment()
        self.assertNotEqual(a, b)

    def test_short_variable_set_keeps_readable_names(self):
        dl = self._downloader([ClimateVariable.precipitation, ClimateVariable.max_temperature])
        name = dl._cache_paths()[0].name
        self.assertLessEqual(len("-".join(sorted(["precipitation", "max_temperature"]))),
                             MAX_VARIABLE_FRAGMENT_LEN)
        self.assertIn("precipitation", name)
        self.assertIn("max_temperature", name)


class VariableCoercionTests(unittest.TestCase):
    def test_string_list_becomes_enum_members(self):
        out = _coerce_variable_list(["precipitation", "max_temperature"])
        self.assertEqual(out, [ClimateVariable.precipitation, ClimateVariable.max_temperature])

    def test_comma_separated_string(self):
        out = _coerce_variable_list("precipitation,max_temperature")
        self.assertEqual([v.name for v in out], ["precipitation", "max_temperature"])

    def test_enum_members_pass_through(self):
        members = [ClimateVariable.precipitation, ClimateVariable.min_temperature]
        self.assertEqual(_coerce_variable_list(members), members)

    def test_mixed_strings_and_enums(self):
        out = _coerce_variable_list([ClimateVariable.precipitation, "max_temperature"])
        self.assertEqual(out, [ClimateVariable.precipitation, ClimateVariable.max_temperature])


if __name__ == "__main__":
    unittest.main()
