"""Inventory persistent local cache files for climate-toolkit fetch paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .multi_site import CACHE_COORD_DECIMALS, normalize_cache_coord


DEFAULT_CACHE_ROOT = Path("outputs/cache")
SUPPORTED_DATASETS = ("nex_gddp_xee", "nex_gddp_batch")


def _normalize_dataset_filter(dataset: str | None) -> tuple[str, ...]:
    if dataset in (None, "all"):
        return SUPPORTED_DATASETS
    if dataset not in SUPPORTED_DATASETS:
        raise ValueError(
            f"Unsupported dataset '{dataset}'. Expected one of: "
            f"{', '.join(['all', *SUPPORTED_DATASETS])}"
        )
    return (dataset,)


def _safe_read_manifest(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _data_path_for_manifest(manifest_path: Path) -> Path:
    suffix = ".manifest.json"
    if manifest_path.name.endswith(suffix):
        return manifest_path.with_name(manifest_path.name[: -len(suffix)])
    return manifest_path


def _site_rows_from_manifest(
    *,
    dataset: str,
    manifest_path: Path,
    manifest: dict,
    data_path: Path,
) -> list[dict]:
    common = {
        "dataset": dataset,
        "scenario": manifest.get("scenario"),
        "model": manifest.get("model"),
        "selected_version": manifest.get("selected_version"),
        "start_date": manifest.get("start_date"),
        "end_date": manifest.get("end_date"),
        "bands": ",".join(manifest.get("bands") or []),
        "cache_schema_version": manifest.get("cache_schema_version"),
        "complete": (manifest.get("integrity") or {}).get("complete"),
        "row_count": (manifest.get("integrity") or {}).get("row_count"),
        "expected_rows": (manifest.get("integrity") or {}).get("expected_rows"),
        "data_path": str(data_path),
        "manifest_path": str(manifest_path),
        "file_size_bytes": data_path.stat().st_size if data_path.exists() else None,
    }

    if dataset == "nex_gddp_xee":
        return [
            {
                **common,
                "site_name": None,
                "site_count": 1,
                "site_label": f"lat={manifest.get('lat')},lon={manifest.get('lon')}",
                "lat": manifest.get("lat"),
                "lon": manifest.get("lon"),
            }
        ]

    rows = []
    sites = manifest.get("sites") or []
    for site in sites:
        rows.append(
            {
                **common,
                "site_name": site.get("name"),
                "site_count": manifest.get("site_count"),
                "site_label": site.get("name"),
                "lat": site.get("lat"),
                "lon": site.get("lon"),
            }
        )
    return rows or [
        {
            **common,
            "site_name": None,
            "site_count": manifest.get("site_count"),
            "site_label": None,
            "lat": None,
            "lon": None,
        }
    ]


def _manifest_record_from_manifest(
    *,
    dataset: str,
    manifest_path: Path,
    manifest: dict,
    data_path: Path,
) -> dict:
    sites = manifest.get("sites") or []
    if dataset == "nex_gddp_xee":
        normalized_sites = [
            {
                "name": None,
                "lat": normalize_cache_coord(manifest.get("lat")),
                "lon": normalize_cache_coord(manifest.get("lon")),
            }
        ]
    else:
        normalized_sites = [
            {
                "name": site.get("name"),
                "lat": normalize_cache_coord(site.get("lat")),
                "lon": normalize_cache_coord(site.get("lon")),
            }
            for site in sites
        ]

    normalized_sites = sorted(
        normalized_sites,
        key=lambda item: (
            "" if item.get("name") is None else str(item.get("name")),
            item.get("lat"),
            item.get("lon"),
        ),
    )
    site_signature = "|".join(
        (
            f"{item.get('name') or 'coord-only'}:"
            f"{item.get('lat'):.{CACHE_COORD_DECIMALS}f}:"
            f"{item.get('lon'):.{CACHE_COORD_DECIMALS}f}"
        )
        for item in normalized_sites
    )
    return {
        "dataset": dataset,
        "scenario": manifest.get("scenario"),
        "model": manifest.get("model"),
        "selected_version": manifest.get("selected_version"),
        "start_date": manifest.get("start_date"),
        "end_date": manifest.get("end_date"),
        "bands": ",".join(manifest.get("bands") or []),
        "cache_schema_version": manifest.get("cache_schema_version"),
        "complete": (manifest.get("integrity") or {}).get("complete"),
        "row_count": (manifest.get("integrity") or {}).get("row_count"),
        "expected_rows": (manifest.get("integrity") or {}).get("expected_rows"),
        "site_count": manifest.get("site_count") or (1 if dataset == "nex_gddp_xee" else len(sites)),
        "site_signature": site_signature,
        "normalized_sites_json": json.dumps(normalized_sites, sort_keys=True),
        "data_path": str(data_path),
        "manifest_path": str(manifest_path),
        "file_size_bytes": data_path.stat().st_size if data_path.exists() else None,
    }


def iter_cache_inventory(
    *,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    dataset: str | None = "all",
) -> Iterable[dict]:
    root = Path(cache_root)
    for dataset_name in _normalize_dataset_filter(dataset):
        dataset_root = root / dataset_name
        if not dataset_root.exists():
            continue
        for manifest_path in sorted(dataset_root.rglob("*.manifest.json")):
            manifest = _safe_read_manifest(manifest_path)
            if manifest is None:
                continue
            data_path = _data_path_for_manifest(manifest_path)
            for row in _site_rows_from_manifest(
                dataset=dataset_name,
                manifest_path=manifest_path,
                manifest=manifest,
                data_path=data_path,
            ):
                yield row


def iter_manifest_inventory(
    *,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    dataset: str | None = "all",
) -> Iterable[dict]:
    root = Path(cache_root)
    for dataset_name in _normalize_dataset_filter(dataset):
        dataset_root = root / dataset_name
        if not dataset_root.exists():
            continue
        for manifest_path in sorted(dataset_root.rglob("*.manifest.json")):
            manifest = _safe_read_manifest(manifest_path)
            if manifest is None:
                continue
            data_path = _data_path_for_manifest(manifest_path)
            yield _manifest_record_from_manifest(
                dataset=dataset_name,
                manifest_path=manifest_path,
                manifest=manifest,
                data_path=data_path,
            )


def cache_inventory(
    *,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    dataset: str | None = "all",
) -> pd.DataFrame:
    frame = pd.DataFrame(iter_cache_inventory(cache_root=cache_root, dataset=dataset))
    if frame.empty:
        return frame
    ordered = [
        "dataset",
        "scenario",
        "model",
        "site_name",
        "site_count",
        "lat",
        "lon",
        "start_date",
        "end_date",
        "row_count",
        "expected_rows",
        "complete",
        "selected_version",
        "bands",
        "file_size_bytes",
        "site_label",
        "data_path",
        "manifest_path",
        "cache_schema_version",
    ]
    available = [column for column in ordered if column in frame.columns]
    frame = frame[available].sort_values(
        ["dataset", "scenario", "model", "site_name", "lat", "lon", "start_date", "end_date"],
        na_position="last",
    )
    return frame.reset_index(drop=True)


def cache_summary(
    *,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    dataset: str | None = "all",
) -> pd.DataFrame:
    frame = pd.DataFrame(iter_manifest_inventory(cache_root=cache_root, dataset=dataset))
    if frame.empty:
        return frame

    summary = (
        frame.groupby(["dataset", "scenario", "model"], dropna=False, as_index=False)
        .agg(
            cache_files=("data_path", "nunique"),
            complete_files=("complete", lambda values: int(sum(bool(v) for v in values))),
            total_size_bytes=("file_size_bytes", "sum"),
            total_rows=("row_count", "sum"),
            min_start_date=("start_date", "min"),
            max_end_date=("end_date", "max"),
        )
    )
    summary["total_size_mb"] = (summary["total_size_bytes"] / (1024 ** 2)).round(3)
    summary["total_size_gb"] = (summary["total_size_bytes"] / (1024 ** 3)).round(6)
    return summary.sort_values(["dataset", "scenario", "model"]).reset_index(drop=True)


def cache_dedup_audit(
    *,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    dataset: str | None = "all",
) -> pd.DataFrame:
    frame = pd.DataFrame(iter_manifest_inventory(cache_root=cache_root, dataset=dataset))
    if frame.empty:
        return frame

    key_columns = [
        "dataset",
        "scenario",
        "model",
        "start_date",
        "end_date",
        "bands",
        "site_count",
        "site_signature",
    ]
    duplicated = frame.duplicated(subset=key_columns, keep=False)
    audit = frame.loc[duplicated].copy()
    if audit.empty:
        return audit

    audit["duplicate_group_size"] = (
        audit.groupby(key_columns, dropna=False)["data_path"].transform("count")
    )
    audit["duplicate_group_size_bytes"] = (
        audit.groupby(key_columns, dropna=False)["file_size_bytes"].transform("sum")
    )
    audit["duplicate_group_size_mb"] = (
        audit["duplicate_group_size_bytes"] / (1024 ** 2)
    ).round(3)
    ordered = key_columns + [
        "duplicate_group_size",
        "duplicate_group_size_bytes",
        "duplicate_group_size_mb",
        "selected_version",
        "complete",
        "row_count",
        "expected_rows",
        "data_path",
        "manifest_path",
    ]
    return audit[ordered].sort_values(key_columns + ["data_path"]).reset_index(drop=True)


def save_output(data: pd.DataFrame, output_path: str | Path, fmt: str) -> None:
    if fmt == "csv":
        data.to_csv(output_path, index=False)
    elif fmt == "json":
        data.to_json(output_path, orient="records", indent=2)
    else:
        raise ValueError(fmt)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List persistent local climate-toolkit cache entries."
    )
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT))
    parser.add_argument(
        "--dataset",
        choices=["all", *SUPPORTED_DATASETS],
        default="all",
        help="Restrict inventory to one cache family.",
    )
    parser.add_argument(
        "--view",
        choices=["entries", "summary", "dedup-audit"],
        default="entries",
        help="Inventory rows, storage summary, or duplicate-cache audit.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--format", choices=["print", "csv", "json"], default="print")
    args = parser.parse_args()

    if args.view == "summary":
        frame = cache_summary(cache_root=args.cache_root, dataset=args.dataset)
    elif args.view == "dedup-audit":
        frame = cache_dedup_audit(cache_root=args.cache_root, dataset=args.dataset)
    else:
        frame = cache_inventory(cache_root=args.cache_root, dataset=args.dataset)
    if args.format == "print" or not args.output:
        if frame.empty:
            print("(no cache entries found)")
        else:
            print(frame.to_string(index=False))
        return 0

    save_output(frame, args.output, args.format)
    print(f"Saved cache inventory to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
