"""Convert GGCMI Phase 3 NetCDF files into packaged parquet point-lookup asset."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from climate_tookit.crop_calendar.ggcmi import DATA_SOURCE_USED_LABELS
from climate_tookit.crop_calendar.registry import iter_crops


FILE_PATTERN = re.compile(
    r"(?P<code>[a-z0-9]+)_(?P<system>rf|ir)_ggcmi_crop_calendar_phase3_v(?P<version>[0-9.]+)\.nc4$"
)

DEFAULT_INPUT_DIR = Path("/private/tmp/ggcmi_phase3")
DEFAULT_OUTPUT_DIR = Path("climate_tookit/data/ggcmi_phase3")
SOURCE_RECORD_URL = "https://zenodo.org/records/5062513"


def _season_id_for_code(crop_code: str) -> int:
    if crop_code == "ri1":
        return 1
    if crop_code == "ri2":
        return 2
    return 1


def _crop_name_for_code(crop_code: str) -> str:
    for crop in iter_crops():
        if crop_code in crop.ggcmi_codes:
            return crop.canonical_name
    raise ValueError(f"Unmapped GGCMI crop code: {crop_code}")


def _timedelta_days(series: pd.Series) -> pd.Series:
    return (series / pd.Timedelta(days=1)).round().astype("Int16")


def convert_file(path: Path) -> pd.DataFrame:
    match = FILE_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"Unexpected GGCMI filename: {path.name}")
    crop_code = match.group("code")
    system = match.group("system")
    version = match.group("version")
    crop_name = _crop_name_for_code(crop_code)

    ds = xr.open_dataset(path, decode_timedelta=True)
    try:
        frame = ds.to_dataframe().reset_index()
    finally:
        ds.close()

    frame = frame.rename(
        columns={
            "growing_season_length": "growing_season_length_days",
            "data_source_used": "data_source_used_code",
            "fraction_of_harvested_area": "season_area_fraction",
        }
    )
    if "growing_season_length_days" in frame.columns:
        frame["growing_season_length_days"] = _timedelta_days(frame["growing_season_length_days"])
    else:
        frame["growing_season_length_days"] = pd.Series(pd.array([pd.NA] * len(frame), dtype="Int16"))
    if "season_area_fraction" not in frame.columns:
        frame["season_area_fraction"] = pd.Series([pd.NA] * len(frame), dtype="Float32")

    frame = frame.loc[
        ~(
            frame["planting_day"].isna()
            & frame["maturity_day"].isna()
            & frame["growing_season_length_days"].isna()
        )
    ].copy()

    frame["crop_code"] = crop_code
    frame["crop_name"] = crop_name
    frame["system"] = system
    frame["season_id"] = _season_id_for_code(crop_code)
    frame["is_multi_season_crop"] = crop_name == "Rice"
    frame["calendar_version"] = version
    frame["source_record_url"] = SOURCE_RECORD_URL
    frame["data_source_used_code"] = frame["data_source_used_code"].round().astype("Int8")
    frame["data_source_used_label"] = frame["data_source_used_code"].map(DATA_SOURCE_USED_LABELS).fillna("Unknown")
    frame["lat"] = frame["lat"].astype("Float32")
    frame["lon"] = frame["lon"].astype("Float32")
    frame["planting_day"] = frame["planting_day"].round().astype("Int16")
    frame["maturity_day"] = frame["maturity_day"].round().astype("Int16")
    frame["season_area_fraction"] = frame["season_area_fraction"].astype("Float32")
    frame["distance_deg"] = pd.Series([pd.NA] * len(frame), dtype="Float32")

    columns = [
        "crop_code",
        "crop_name",
        "system",
        "season_id",
        "is_multi_season_crop",
        "lat",
        "lon",
        "planting_day",
        "maturity_day",
        "growing_season_length_days",
        "data_source_used_code",
        "data_source_used_label",
        "season_area_fraction",
        "calendar_version",
        "source_record_url",
    ]
    return frame[columns]


def build_asset(input_dir: Path, output_dir: Path) -> tuple[Path, Path, int]:
    nc_files = sorted(input_dir.glob("*.nc4"))
    if not nc_files:
        raise FileNotFoundError(f"No .nc4 files found under {input_dir}")

    frames = [convert_file(path) for path in nc_files]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["crop_name", "system", "season_id", "lat", "lon"]).reset_index(drop=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "crop_calendar.parquet"
    manifest_path = output_dir / "crop_calendar_manifest.json"

    combined.to_parquet(parquet_path, index=False, compression="zstd")

    manifest = {
        "dataset": "GGCMI Phase 3 crop calendar",
        "source_record_url": SOURCE_RECORD_URL,
        "article_url": "https://www.nature.com/articles/s43016-021-00400-y",
        "license": "CC-BY-4.0",
        "notes": [
            "Packaged point-extraction asset derived from published GGCMI Phase 3 gridded NetCDF files.",
            "Preserves rainfed and irrigated calendars separately.",
            "Preserves separate rice seasons and season_area_fraction where provided.",
        ],
        "format": "parquet",
        "row_count": int(len(combined)),
        "crop_count": int(combined["crop_name"].nunique()),
        "systems": sorted(combined["system"].dropna().unique().tolist()),
        "season_ids": sorted(int(v) for v in combined["season_id"].dropna().unique().tolist()),
        "columns": combined.columns.tolist(),
        "calendar_versions": sorted(combined["calendar_version"].dropna().unique().tolist()),
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return parquet_path, manifest_path, len(combined)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    parquet_path, manifest_path, row_count = build_asset(
        Path(args.input_dir),
        Path(args.output_dir),
    )
    print(f"Built GGCMI parquet asset: {parquet_path}")
    print(f"Built GGCMI manifest: {manifest_path}")
    print(f"Rows: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
