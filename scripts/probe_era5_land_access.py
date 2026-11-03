"""Check candidate ERA5-Land store metadata without fetching climate arrays.

Anonymous by default. --cds-auth uses CDSAPI_KEY or ~/.cdsapirc for the official
CDS host only. No login prompts, credential changes, or production routing.
Reports never include credentials, request headers, or remote error bodies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import requests
import yaml


CDS_ROOT = "https://arco.datastores.ecmwf.int"
CDS_GROUPS = {
    "temperature": ("007", "sfc-2m-temperature", ["t2m", "d2m"]),
    "wind": ("008", "sfc-wind", ["u10", "v10"]),
    "precipitation": ("009", "sfc-pressure-precipitation", ["tp"]),
    "radiation": ("010", "sfc-radiation-heat", ["ssrd"]),
}
EDH_DAILY = "https://data.earthdatahub.destine.eu/era5/era5-land-daily-utc-v1.zarr/zarr.json"
MAX_METADATA_BYTES = 2 * 1024**2


def cds_key():
    """Read existing credentials only; never return a configuration error body."""
    key = os.getenv("CDSAPI_KEY")
    if key:
        return key.strip()
    try:
        config = yaml.safe_load(Path.home().joinpath(".cdsapirc").read_text())
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(config, dict) or not isinstance(config.get("key"), str):
        return None
    return config["key"].strip() or None


def probe_metadata(url, *, key=None, expected_variables=()):
    if key and not url.startswith(CDS_ROOT + "/"):
        raise ValueError("CDS credentials may only be sent to the official CDS ARCO host")
    result = {"url": url, "credential_used": bool(key), "attempts": 0, "response_body_bytes": 0}
    start = time.monotonic()
    # Explicit credentials only. Do not silently use .netrc on anonymous probes.
    with requests.Session() as session:
        session.trust_env = False
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        for attempt in range(2):
            result["attempts"] += 1
            try:
                with session.get(
                    url, headers=headers, timeout=(5, 15), allow_redirects=False, stream=True
                ) as response:
                    result["http_status"] = response.status_code
                    if response.status_code in {401, 403}:
                        result["status"] = (
                            "authentication_rejected" if key else "authentication_required"
                        )
                        break
                    if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                        time.sleep(1)
                        continue
                    if response.status_code != 200:
                        result["status"] = "http_error"
                        break
                    body = bytearray()
                    for part in response.iter_content(65536):
                        result["response_body_bytes"] += len(part)
                        body.extend(part)
                        if len(body) > MAX_METADATA_BYTES:
                            raise ValueError("Metadata size limit exceeded")
                    metadata = json.loads(body)
                    if not isinstance(metadata, dict):
                        raise ValueError("Metadata must be an object")
                    result["metadata_sha256"] = hashlib.sha256(body).hexdigest()
                    if url.endswith("/.zmetadata"):
                        entries = metadata["metadata"]
                        arrays = {}
                        for variable in expected_variables:
                            array = entries.get(f"{variable}/.zarray")
                            if array is None:
                                continue
                            attrs = entries.get(f"{variable}/.zattrs", {})
                            arrays[variable] = {
                                "shape": array.get("shape"),
                                "chunks": array.get("chunks"),
                                "dtype": array.get("dtype"),
                                "units": attrs.get("units"),
                                "dimensions": attrs.get("_ARRAY_DIMENSIONS"),
                            }
                        result["arrays"] = arrays
                        result["missing_variables"] = sorted(
                            set(expected_variables) - arrays.keys()
                        )
                        result["status"] = (
                            "missing_variables"
                            if result["missing_variables"]
                            else "metadata_available"
                        )
                    else:
                        if metadata.get("zarr_format") != 3 or metadata.get("node_type") != "group":
                            raise ValueError("Expected a Zarr v3 group")
                        result["status"] = "metadata_available"
                    break
            except (requests.Timeout, requests.ConnectionError):
                result["status"] = "transport_error"
                if attempt == 0:
                    time.sleep(1)
                    continue
            except requests.RequestException:
                result["status"] = "transport_error"
                break
            except (ValueError, KeyError, TypeError, AttributeError):
                result["status"] = "invalid_metadata"
                break
    result["seconds"] = round(time.monotonic() - start, 3)
    return result


def run(authenticated=False):
    key = cds_key() if authenticated else None
    report = {
        "measured_utc": datetime.now(timezone.utc).isoformat(),
        "cds_auth_requested": authenticated,
        "cds_key_configured": bool(key),
        "scope": "Metadata access only; no climate values, live coverage or throughput verified.",
        "cases": [],
    }
    for name, (bucket, group, variables) in CDS_GROUPS.items():
        url = f"{CDS_ROOT}/cadl-arco-geo-{bucket}/arco/reanalysis_era5_land/{group}/geoChunked.zarr/.zmetadata"
        if authenticated and not key:
            result = {"url": url, "status": "missing_credentials", "attempts": 0}
        else:
            result = probe_metadata(url, key=key, expected_variables=variables)
        report["cases"].append({"provider": "cds_arco", "group": name, **result})
    # Separate service: never forward the CDS key to EDH.
    report["cases"].append(
        {"provider": "earth_data_hub", "group": "daily", **probe_metadata(EDH_DAILY)}
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cds-auth", action="store_true")
    parser.add_argument("--output", default="outputs/era5_land_access_probe.json")
    args = parser.parse_args()
    report = run(args.cds_auth)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if all(c["status"] == "metadata_available" for c in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
