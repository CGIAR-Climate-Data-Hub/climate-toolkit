"""ERA5-Land migration preserves the product, units and existing cache data."""

from datetime import date
import importlib
import json
import warnings

import pandas as pd
import pytest

from climate_toolkit.fetch_data.fetch_data import fetch_data
from climate_toolkit.fetch_data import gee_xee_batch as batch
from climate_toolkit.fetch_data.multi_site import Site
from climate_toolkit.fetch_data.source_data.sources.utils.models import (
    ClimateDataset,
    ClimateVariable,
    accepted_climate_dataset_names,
    normalize_climate_dataset_name,
)
from climate_toolkit.fetch_data.source_data.sources.utils.settings import Settings


@pytest.mark.parametrize("alias", ["agera_5", "agera5", "AGERA_5"])
def test_deprecated_names_warn_and_resolve_to_same_product(alias):
    with pytest.warns(FutureWarning, match="not AgERA5.*era5_land"):
        assert normalize_climate_dataset_name(alias) == "era5_land"
    assert ClimateDataset.agera_5 is ClimateDataset.era5_land
    assert {"era5_land", "agera_5", "agera5"} <= set(accepted_climate_dataset_names())


def test_canonical_name_and_legacy_configuration():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert normalize_climate_dataset_name("era5_land") == "era5_land"
    assert not caught
    settings = Settings.load()
    assert settings.era5_land.gee_image == "ECMWF/ERA5_LAND/DAILY_AGGR"
    assert settings.agera_5 is settings.era5_land
    old_config = settings.model_dump()
    old_config["agera_5"] = old_config.pop("era5_land")
    assert Settings(**old_config).era5_land == settings.era5_land


@pytest.mark.parametrize("stage", ["raw", "transformed", "preprocessed"])
def test_fetch_alias_matches_canonical_units_at_every_stage(monkeypatch, stage):
    raw = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
        "temperature_2m_max": [300.0, 301.0],
        "total_precipitation_sum": [0.001, 0.002],
    })

    class Source:
        def __init__(self, **kwargs):
            assert kwargs["source"] is ClimateDataset.era5_land
            assert kwargs["settings"].era5_land.gee_image == "ECMWF/ERA5_LAND/DAILY_AGGR"

        def download(self):
            return raw.copy()

    for module in ("fetch_data", "transform_data.transform_data"):
        target = importlib.import_module(f"climate_toolkit.fetch_data.{module}")
        monkeypatch.setattr(target, "SourceData", Source)
    options = dict(
        location_coord=(-1.286, 36.817), date_from=date(2020, 1, 1),
        date_to=date(2020, 1, 2), stage=stage, verbose=False,
        variables=[ClimateVariable.max_temperature, ClimateVariable.precipitation],
    )
    canonical = fetch_data(source="era5_land", **options)
    with pytest.warns(FutureWarning, match="deprecated"):
        legacy = fetch_data(source="agera_5", **options)
    pd.testing.assert_frame_equal(canonical, legacy)
    if stage == "preprocessed":
        assert canonical.precipitation.tolist() == [1.0, 2.0]
        assert canonical.max_temperature.tolist() == pytest.approx([26.85, 27.85])


def test_existing_agera_cache_is_reused_without_rewriting(tmp_path):
    site = Site(name="site", lat=-1.286, lon=36.817)
    start = end = date(2020, 1, 1)
    data_path, manifest_path = batch._cache_paths(
        cache_dir=tmp_path, source=ClimateDataset.era5_land, site=site,
        start=start, end=end, bands=["total_precipitation_sum"],
    )
    assert "agera_5" in data_path.parts
    dates = pd.date_range(start, end)
    frame = pd.DataFrame({
        "site": ["site"], "lat": [site.lat], "lon": [site.lon],
        "date": dates, "total_precipitation_sum": [0.001],
    })
    manifest = batch._build_manifest(
        frame=frame, source=ClimateDataset.era5_land, site=site,
        bands=["total_precipitation_sum"], start=start, end=end, expected_dates=dates,
    )
    manifest["source"] = "agera_5"  # An existing, pre-migration record.
    batch._write_cached_frame(data_path, manifest_path, frame, manifest)
    cached, _ = batch._load_valid_cached_chunk(
        data_path, manifest_path, start=start, end=end, site=site,
        expected_dates=dates, refresh_cache=False, verbose=False,
    )
    assert cached is not None
    pd.testing.assert_frame_equal(cached, frame)
    assert json.loads(manifest_path.read_text())["source"] == "agera_5"


@pytest.mark.parametrize("source", ["era5_land", "agera_5"])
def test_no_gee_guard_cannot_be_bypassed_by_either_name(source):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        with pytest.raises(ValueError, match="GEE"):
            fetch_data(source=source, location_coord=(0, 0), allow_gee=False)
