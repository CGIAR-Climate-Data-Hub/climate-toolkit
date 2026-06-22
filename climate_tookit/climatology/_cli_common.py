"""Internal helpers for climatology CLI/report entrypoints."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from climate_tookit.season_analysis.seasons import get_climate_data


def parse_location(location: str) -> tuple[float, float]:
    try:
        lat_text, lon_text = [part.strip() for part in location.split(",", 1)]
        return float(lat_text), float(lon_text)
    except Exception as exc:
        raise ValueError("location must be 'lat,lon'") from exc


def fetch_standardized_climate_frame(
    *,
    location: str,
    source: str,
    start: str,
    end: str,
    precip_source: Optional[str] = None,
    temp_source: Optional[str] = None,
    model: Optional[str] = None,
    scenario: Optional[str] = None,
) -> pd.DataFrame:
    lat, lon = parse_location(location)
    return get_climate_data(
        lat,
        lon,
        start,
        end,
        force_source=source,
        precip_source=precip_source,
        temp_source=temp_source,
        model=model,
        scenario=scenario,
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value) if not isinstance(value, (str, bytes, dict, list, tuple)) else False:
        return None
    return value


def build_frame_payload(
    *,
    tool: str,
    mode: str,
    frame: pd.DataFrame,
    metadata: Optional[dict[str, Any]] = None,
    location: Optional[str] = None,
    source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool,
        "mode": mode,
        "rows": int(len(frame)),
        "records": _json_ready(frame.to_dict(orient="records")),
        "metadata": _json_ready(metadata or {}),
    }
    if location:
        lat, lon = parse_location(location)
        payload["location"] = {"lat": lat, "lon": lon}
    if source:
        payload["source"] = source
    if start or end:
        payload["period"] = {"start": start, "end": end}
    if extra:
        payload.update(_json_ready(extra))
    return payload


def build_status_payload(
    *,
    tool: str,
    mode: str,
    ready: bool,
    message: Optional[str],
    location: Optional[str] = None,
    source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool,
        "mode": mode,
        "ready": bool(ready),
        "message": message,
    }
    if location:
        lat, lon = parse_location(location)
        payload["location"] = {"lat": lat, "lon": lon}
    if source:
        payload["source"] = source
    if start or end:
        payload["period"] = {"start": start, "end": end}
    if extra:
        payload.update(_json_ready(extra))
    return payload


def save_payload(
    *,
    payload: dict[str, Any],
    frame: Optional[pd.DataFrame],
    output_format: str,
    output_path: str,
) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    elif output_format == "csv":
        if frame is None:
            pd.DataFrame([payload]).to_csv(path, index=False)
        else:
            frame.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")
    return str(path)


def render_frame_text(
    *,
    title: str,
    frame: pd.DataFrame,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    lines = [title]
    if metadata:
        lines.append(f"metadata={_json_ready(metadata)}")
    if frame.empty:
        lines.append("(no rows)")
    else:
        lines.append(frame.to_string(index=False))
    return "\n".join(lines)


def render_status_text(
    *,
    title: str,
    ready: bool,
    message: Optional[str],
    extra: Optional[dict[str, Any]] = None,
) -> str:
    lines = [title, f"ready={'yes' if ready else 'no'}"]
    if message:
        lines.append(f"message={message}")
    if extra:
        lines.append(f"details={_json_ready(extra)}")
    return "\n".join(lines)
