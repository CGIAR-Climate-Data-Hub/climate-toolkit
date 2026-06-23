from datetime import date
import sys
import types
import unittest
from unittest import mock

import pandas as pd


def _install_test_stubs():
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    ee = types.ModuleType("ee")
    ee.Authenticate = lambda *args, **kwargs: None
    ee.Initialize = lambda *args, **kwargs: None
    sys.modules.setdefault("ee", ee)


_install_test_stubs()

from climate_tookit.fetch_data.nex_gddp_batch import (
    _integrity_summary,
    cache_paths_for_batch,
    fetch_nex_gddp_batch_data,
    load_sites,
    main,
    parse_args,
    run_batch_extraction,
)


class NexGddpBatchTests(unittest.TestCase):
    def test_parse_args_accepts_legacy_from_to_and_lat_lon(self):
        args = parse_args(
            [
                "--variables",
                "precipitation,max_temperature,min_temperature",
                "--from",
                "2050-01-01",
                "--to",
                "2050-01-10",
                "--lon",
                "36.817",
                "--lat",
                "-1.286",
                "--model",
                "GFDL-ESM4",
                "--scenario",
                "ssp245",
            ]
        )

        self.assertEqual(date(2050, 1, 1), args.start)
        self.assertEqual(date(2050, 1, 10), args.end)
        self.assertEqual(-1.286, args.single_lat)
        self.assertEqual(36.817, args.single_lon)
        self.assertEqual("GFDL-ESM4", args.model)

    def test_parse_args_accepts_station_lat_lon_aliases(self):
        args = parse_args(
            [
                "--variables",
                "precipitation,max_temperature,min_temperature",
                "--start",
                "2050-01-01",
                "--end",
                "2050-01-10",
                "--station-lon",
                "36.817",
                "--station-lat",
                "-1.286",
            ]
        )

        self.assertEqual(date(2050, 1, 1), args.start)
        self.assertEqual(date(2050, 1, 10), args.end)
        self.assertEqual(-1.286, args.single_lat)
        self.assertEqual(36.817, args.single_lon)

    def test_main_builds_single_site_from_scalar_coords(self):
        fake_data = pd.DataFrame({"date": pd.to_datetime(["2050-01-01"])})
        fake_summary = pd.DataFrame({"rows": [1]})
        fake_manifest = pd.DataFrame({"cache_hit": [False]})
        argv = [
            "nex_gddp_batch.py",
            "--start",
            "2050-01-01",
            "--end",
            "2050-01-01",
            "--station-lat",
            "-1.286",
            "--station-lon",
            "36.817",
            "--site-name",
            "Nairobi",
            "--quiet",
        ]

        with mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch.fetch_nex_gddp_batch_data",
            return_value=(fake_data, fake_summary, fake_manifest),
        ) as fetch_mock, mock.patch("sys.argv", argv):
            rc = main()

        self.assertEqual(0, rc)
        sites = fetch_mock.call_args.kwargs["sites"]
        self.assertEqual(1, len(sites))
        self.assertEqual("Nairobi", sites[0].name)
        self.assertEqual(-1.286, sites[0].lat)
        self.assertEqual(36.817, sites[0].lon)

    def test_run_batch_extraction_logs_single_compact_cache_hit_line_per_batch(self):
        cached_df = pd.DataFrame(
            {
                "site": ["Nairobi"],
                "lat": [-1.286],
                "lon": [36.817],
                "date": pd.to_datetime(["2050-01-01"]),
                "pr": [1.2],
                "tasmax": [25.0],
                "tasmin": [15.0],
                "model": ["MRI-ESM2-0"],
                "scenario": ["ssp245"],
            }
        )
        cached_manifest = {"selected_version": "1.1"}
        sites = load_sites(sites=[("Nairobi", -1.286, 36.817)])

        with mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch._requested_band_names",
            return_value=["pr", "tasmax", "tasmin"],
        ), mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch._load_valid_cached_batch",
            return_value=(cached_df, cached_manifest),
        ), mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch._log_progress",
        ) as progress_log:
            result, summary, manifest = run_batch_extraction(
                sites=sites,
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 1),
                verbose=True,
            )

        self.assertEqual(1, len(result))
        self.assertEqual(1, len(summary))
        self.assertEqual(1, len(manifest))

        messages = [call.args[0] for call in progress_log.call_args_list]
        self.assertTrue(
            any("batch 1/1 | 2050-01-01:2050-01-01 | Nairobi..Nairobi (1 sites) | cache hit |" in msg for msg in messages)
        )
        self.assertFalse(any("batch 1/1: 2050-01-01:2050-01-01" in msg for msg in messages))

    def test_load_sites_dedupes_same_site_after_cache_coord_rounding(self):
        sites = load_sites(
            sites=[
                ("Nairobi", -1.2860000001, 36.8171111111),
                ("Nairobi", -1.2860, 36.81711),
            ]
        )

        self.assertEqual(1, len(sites))

    def test_batch_cache_path_includes_human_readable_site_fragment(self):
        data_path, manifest_path = cache_paths_for_batch(
            cache_dir="outputs/cache/nex_gddp_batch",
            site_batch=[
                type("SiteStub", (), {"name": "Nairobi Hub", "lat": -1.286, "lon": 36.817})(),
                type("SiteStub", (), {"name": "Cusco Field", "lat": -13.5319, "lon": -71.9675})(),
            ],
            start=date(2050, 1, 1),
            end=date(2050, 1, 7),
            model="MRI-ESM2-0",
            scenario="ssp245",
            bands=["pr", "tasmax", "tasmin"],
        )

        self.assertIn("nairobi-hub_to_cusco-field", data_path.name)
        self.assertTrue(str(manifest_path).endswith(".manifest.json"))

    def test_integrity_summary_flags_missing_site_date_pairs(self):
        sites = [
            ("Nairobi", -1.286, 36.817),
            ("Cusco", -13.5319, -71.9675),
        ]
        frame = pd.DataFrame(
            {
                "site": ["Nairobi", "Nairobi", "Cusco"],
                "lat": [-1.286, -1.286, -13.5319],
                "lon": [36.817, 36.817, -71.9675],
                "date": pd.to_datetime(["2050-01-01", "2050-01-02", "2050-01-01"]),
            }
        )

        integrity = _integrity_summary(
            frame,
            start=date(2050, 1, 1),
            end=date(2050, 1, 2),
            sites=[type("SiteStub", (), {"name": name, "lat": lat, "lon": lon})() for name, lat, lon in sites],
        )

        self.assertFalse(integrity["complete"])
        self.assertEqual(len(integrity["missing_site_dates"]), 1)
        self.assertEqual(integrity["missing_site_dates"][0]["site"], "Cusco")
        self.assertEqual(integrity["missing_site_dates"][0]["date"], "2050-01-02")

    def test_fetch_nex_gddp_batch_transformed_stage_maps_hurs_to_humidity(self):
        raw_df = pd.DataFrame(
            {
                "site": ["Nairobi"],
                "lat": [-1.286],
                "lon": [36.817],
                "date": pd.to_datetime(["2050-01-01"]),
                "pr": [1.2],
                "tasmax": [25.0],
                "tasmin": [15.0],
                "hurs": [74.0],
                "model": ["MRI-ESM2-0"],
                "scenario": ["ssp245"],
            }
        )

        with mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch.run_batch_extraction",
            return_value=(raw_df, pd.DataFrame(), pd.DataFrame()),
        ):
            data_df, _, _ = fetch_nex_gddp_batch_data(
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 1),
                stage="transformed",
            )

        self.assertIn("humidity", data_df.columns)
        self.assertNotIn("hurs", data_df.columns)

    def test_transformed_stage_uses_package_variable_mapping(self):
        raw_df = pd.DataFrame(
            {
                "site": ["Nairobi"],
                "lat": [-1.286],
                "lon": [36.817],
                "date": pd.to_datetime(["2050-01-01"]),
                "pr": [1.2],
                "tasmax": [25.0],
                "tasmin": [15.0],
                "model": ["MRI-ESM2-0"],
                "scenario": ["ssp245"],
            }
        )
        summary_df = pd.DataFrame({"site": ["Nairobi"]})
        manifest_df = pd.DataFrame({"cache_hit": [False]})

        with mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch.run_batch_extraction",
            return_value=(raw_df, summary_df, manifest_df),
        ):
            data_df, returned_summary, returned_manifest = fetch_nex_gddp_batch_data(
                sites=[("Nairobi", -1.286, 36.817)],
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 1),
                stage="transformed",
                verbose=False,
            )

        self.assertEqual(
            list(data_df.columns),
            [
                "site",
                "lat",
                "lon",
                "date",
                "precipitation",
                "max_temperature",
                "min_temperature",
                "model",
                "scenario",
            ],
        )
        self.assertIs(returned_summary, summary_df)
        self.assertIs(returned_manifest, manifest_df)

    def test_preprocessed_stage_does_not_fill_across_sites(self):
        raw_df = pd.DataFrame(
            {
                "site": ["A", "A", "B", "B"],
                "lat": [0.0, 0.0, 1.0, 1.0],
                "lon": [36.0, 36.0, 37.0, 37.0],
                "date": pd.to_datetime(
                    ["2050-01-01", "2050-01-02", "2050-01-01", "2050-01-02"]
                ),
                "pr": [None, 2.0, 5.0, 6.0],
                "tasmax": [None, 20.0, 35.0, 36.0],
                "tasmin": [None, 10.0, 18.0, 19.0],
                "model": ["MRI-ESM2-0"] * 4,
                "scenario": ["ssp245"] * 4,
            }
        )

        with mock.patch(
            "climate_tookit.fetch_data.nex_gddp_batch.run_batch_extraction",
            return_value=(raw_df, pd.DataFrame(), pd.DataFrame()),
        ):
            data_df, _, _ = fetch_nex_gddp_batch_data(
                sites=[("A", 0.0, 36.0), ("B", 1.0, 37.0)],
                date_from=date(2050, 1, 1),
                date_to=date(2050, 1, 2),
                stage="preprocessed",
                verbose=False,
            )

        site_a = data_df.loc[data_df["site"] == "A"].sort_values("date").reset_index(drop=True)
        site_b = data_df.loc[data_df["site"] == "B"].sort_values("date").reset_index(drop=True)

        self.assertEqual(site_a.loc[0, "max_temperature"], 20.0)
        self.assertEqual(site_a.loc[0, "min_temperature"], 10.0)
        self.assertEqual(site_a.loc[0, "precipitation"], 0.0)
        self.assertEqual(site_b.loc[0, "max_temperature"], 35.0)


if __name__ == "__main__":
    unittest.main()
