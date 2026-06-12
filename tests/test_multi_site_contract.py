from datetime import date
import unittest

import pandas as pd

from climate_tookit.fetch_data import Site, load_sites, parse_site_spec
from climate_tookit.fetch_data.multi_site import (
    CACHE_COORD_DECIMALS,
    normalize_cache_coord,
    safe_coord_fragment,
    site_batch_digest,
    site_date_integrity_summary,
)


class MultiSiteContractTests(unittest.TestCase):
    def test_package_exports_shared_site_contract(self):
        site = parse_site_spec("Nairobi,-1.286,36.817")

        self.assertIsInstance(site, Site)
        self.assertEqual(site.name, "Nairobi")
        self.assertEqual(site.lat, -1.286)
        self.assertEqual(site.lon, 36.817)

    def test_load_sites_dedupes_by_normalized_coordinate_precision(self):
        sites = load_sites(
            sites=[
                ("Nairobi", -1.2860000001, 36.8171111111),
                ("Nairobi", -1.2860, 36.81711),
            ]
        )

        self.assertEqual(1, len(sites))

    def test_coordinate_normalization_and_fragment_are_shared(self):
        self.assertEqual(-1.286, normalize_cache_coord(-1.2860000001))
        self.assertEqual("m1p2860", safe_coord_fragment(-1.286))
        self.assertEqual(4, CACHE_COORD_DECIMALS)

    def test_site_batch_digest_uses_normalized_coordinates(self):
        left = [Site("Nairobi", -1.2860000001, 36.8171111111)]
        right = [Site("Nairobi", -1.2860, 36.81711)]

        self.assertEqual(site_batch_digest(left), site_batch_digest(right))

    def test_site_date_integrity_summary_flags_duplicate_and_missing_pairs(self):
        frame = pd.DataFrame(
            {
                "site": ["Nairobi", "Nairobi", "Nairobi"],
                "lat": [-1.286, -1.286, -1.286],
                "lon": [36.817, 36.817, 36.817],
                "date": pd.to_datetime(["2050-01-01", "2050-01-01", "2050-01-02"]),
            }
        )

        integrity = site_date_integrity_summary(
            frame=frame,
            start=date(2050, 1, 1),
            end=date(2050, 1, 3),
            sites=[Site("Nairobi", -1.286, 36.817)],
        )

        self.assertFalse(integrity["complete"])
        self.assertEqual(len(integrity["duplicate_site_dates"]), 1)
        self.assertEqual(len(integrity["missing_site_dates"]), 1)
        self.assertEqual(integrity["missing_site_dates"][0]["date"], "2050-01-03")

    def test_site_date_integrity_summary_accepts_explicit_datetime_index(self):
        frame = pd.DataFrame(
            {
                "site": ["Nairobi", "Nairobi"],
                "lat": [-1.286, -1.286],
                "lon": [36.817, 36.817],
                "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            }
        )

        integrity = site_date_integrity_summary(
            frame=frame,
            start=date(2020, 1, 1),
            end=date(2020, 1, 2),
            sites=[Site("Nairobi", -1.286, 36.817)],
            expected_dates=pd.date_range("2020-01-01", "2020-01-02", freq="D"),
        )

        self.assertTrue(integrity["complete"])


if __name__ == "__main__":
    unittest.main()
