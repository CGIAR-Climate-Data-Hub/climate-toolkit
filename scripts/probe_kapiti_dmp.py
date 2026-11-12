"""Check anonymous access to the DMP and QA rasters for three March 2025 dekads."""

import argparse
import json
from pathlib import Path
import time

import requests

COLLECTION = "clms_dmp_global_300m_10daily_v2_cog"
ITEMS = f"https://stac.opensearch.dataspace.copernicus.eu/collections/{COLLECTION}/items"
PERIOD = "2025-03-01T00:00:00Z/2025-03-31T23:59:59Z"


def probe(session, url):
    start = time.monotonic()
    with session.get(url, headers={"Range": "bytes=0-511"}, stream=True, timeout=30) as reply:
        prefix = next(reply.iter_content(512), b"")
        return dict(
            status=reply.status_code,
            elapsed_s=round(time.monotonic() - start, 3),
            body_bytes_sampled=len(prefix),
            content_range=reply.headers.get("Content-Range"),
            tiff=prefix[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"),
        )


def main(output):
    with requests.Session() as session:
        session.trust_env = False  # Probe anonymous routes, including on machines with a netrc.
        start = time.monotonic()
        reply = session.get(ITEMS, params={"datetime": PERIOD, "limit": 30}, timeout=30)
        reply.raise_for_status()
        page = reply.json()
        result = dict(
            catalogue_seconds=round(time.monotonic() - start, 3),
            catalogue_bytes=len(reply.content),
            probes=[],
        )
        items = sorted(
            (f for f in page["features"] if "DMP300-RT6_" in f["id"]), key=lambda item: item["id"]
        )
        if len(items) != 3 or any(link["rel"] == "next" for link in page["links"]):
            raise ValueError("Expected three consolidated global dekads")
        for item in items:
            for band in ("dmp", "qflag"):
                asset = item["assets"][band]
                path = asset["href"].removeprefix("s3://")
                routes = {
                    "odata_node": asset["alternate"]["https"]["href"],
                    "s3_object": "https://eodata.dataspace.copernicus.eu/" + path,
                }
                for route, url in routes.items():
                    result["probes"].append(
                        dict(
                            item=item["id"],
                            band=band,
                            route=route,
                            file_bytes=asset.get("file:size"),
                            **probe(session, url),
                        )
                    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/validation/issue-92/kapiti/dmp_probe.json")
    )
    main(parser.parse_args().output)
