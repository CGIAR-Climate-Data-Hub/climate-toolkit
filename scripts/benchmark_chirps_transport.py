"""Opt-in anonymous CHIRPS transport benchmark. Run with the published cloud extra.

Use macOS or Linux. Install psutil alongside the cloud extra for memory sampling.
A loopback relay counts HTTP response-body bytes and request attempts
at the public providers. Only the two store URLs and catalogue reads are routed
through it. Nothing is installed in the system trust store.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic
from unittest.mock import patch
from urllib.parse import urlsplit

import aiohttp
import psutil
from aiohttp import web
from yarl import URL

from benchmark_direct_cloud import ROOT, worker


OUTPUT = ROOT / "outputs/validation/issue-177/transport"
HF = "huggingface.co"
STAC = "stac.dynamical.org"
S3 = "dynamical-ucsb-chc-chirps.s3.us-west-2.amazonaws.com"
METHODS = {"GET", "HEAD"}
HEADERS = {"accept", "accept-encoding", "range", "if-match", "if-none-match", "user-agent"}
RESPONSE_HEADERS = {
    "content-encoding",
    "content-length",
    "content-range",
    "content-type",
    "accept-ranges",
    "etag",
    "last-modified",
    "retry-after",
}


def start_url(raw):
    url = URL("https://" + raw, encoded=True)
    allowed = {
        HF: (
            "/api/datasets/aaguilar90/chirps-v3-daily-rnl",
            "/datasets/aaguilar90/chirps-v3-daily-rnl/",
        ),
        STAC: ("/ucsb-chc-chirps-analysis-final/",),
        S3: ("/ucsb-chc-chirps-analysis-final/",),
    }
    if (
        url.user is not None
        or url.port != 443
        or not url.path.startswith(allowed.get(url.host, ()))
    ):
        raise web.HTTPForbidden()
    return url


class Meter:
    def __init__(self):
        self.phase = "cold"
        self.counts = {phase: Counter(requests=0, body_bytes=0) for phase in ("cold", "warm")}
        self.status = {phase: Counter() for phase in self.counts}

    async def sent(self, session, context, params):
        self.counts[context.trace_request_ctx]["requests"] += 1

    async def begin_warm(self, request):
        self.phase = "warm"
        return web.Response()

    async def relay(self, request):
        if request.method not in METHODS:
            raise web.HTTPForbidden()
        target = start_url(request.raw_path.removeprefix("/https/"))
        phase = self.phase
        counts = self.counts[phase]
        headers = {k: v for k, v in request.headers.items() if k.lower() in HEADERS}
        # Follow provider-issued CDN redirects. Count each redirect and consume
        # its response body. Downloaded payloads and signed URLs are never logged.
        for _ in range(10):
            counts["logical_requests"] += 1
            async with self.client.request(
                request.method,
                target,
                headers=headers,
                allow_redirects=False,
                trace_request_ctx=phase,
            ) as upstream:
                self.status[phase][str(upstream.status)] += 1
                if upstream.status in (301, 302, 303, 307, 308) and "Location" in upstream.headers:
                    counts["body_bytes"] += len(await upstream.read())
                    target = target.join(URL(upstream.headers["Location"], encoded=True))
                    if (
                        target.scheme != "https"
                        or target.user is not None
                        or target.port != 443
                        or not (
                            target.host in (HF, STAC, S3)
                            or target.host.endswith((".hf.co", ".huggingface.co"))
                        )
                    ):
                        raise web.HTTPBadGateway(reason="Unexpected provider redirect")
                    continue
                response = web.StreamResponse(
                    status=upstream.status,
                    headers={
                        k: v for k, v in upstream.headers.items() if k.lower() in RESPONSE_HEADERS
                    },
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(65536):
                    counts["body_bytes"] += len(chunk)
                    await response.write(chunk)
                await response.write_eof()
                return response
        raise web.HTTPBadGateway(reason="Provider redirect limit exceeded")


def measured_worker(case, base):
    # benchmark_direct_cloud also supports development checkouts. This benchmark
    # deliberately imports the installed wheel, even when launched from the repo.
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != ROOT]
    import requests
    import icechunk
    import xarray as xr
    from climate_toolkit.fetch_data import direct_cloud

    metadata, http_storage, open_zarr = direct_cloud._json_get, icechunk.http_storage, xr.open_zarr

    def route(url):
        if urlsplit(url).scheme != "https":
            raise ValueError("Expected a public HTTPS provider URL")
        return base + "/https/" + url.removeprefix("https://")

    def measured_storage(url, **kwargs):
        opts = {**kwargs["opts"], "allow_http": "true"}
        return http_storage(route(url), opts=opts)

    def measured_zarr(store, **kwargs):
        return open_zarr(route(store) if isinstance(store, str) else store, **kwargs)

    def warm():
        requests.post(base + "/warm", timeout=5).raise_for_status()

    with (
        patch.object(direct_cloud, "_json_get", lambda url: metadata(route(url))),
        patch.object(icechunk, "http_storage", measured_storage),
        patch.object(xr, "open_zarr", measured_zarr),
    ):
        worker(case, before_warm=warm)


async def measure(case, deadline, cache_root):
    timeout = aiohttp.ClientTimeout(total=55)
    meter = Meter()
    trace = aiohttp.TraceConfig()
    trace.on_request_headers_sent.append(meter.sent)
    async with aiohttp.ClientSession(
        auto_decompress=False,
        timeout=timeout,
        cookie_jar=aiohttp.DummyCookieJar(),
        trace_configs=[trace],
        skip_auto_headers={"Accept-Encoding"},
    ) as client:
        meter.client = client
        app = web.Application()
        app.router.add_post("/warm", meter.begin_warm)
        app.router.add_route("*", "/https/{path:.*}", meter.relay)
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=1, handler_cancellation=True)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        base = f"http://127.0.0.1:{runner.addresses[0][1]}"
        try:
            with tempfile.TemporaryDirectory(dir=cache_root) as tmp:
                env = dict(
                    os.environ,
                    TMPDIR=tmp,
                    NO_PROXY="127.0.0.1,localhost",
                    no_proxy="127.0.0.1,localhost",
                    CLIMATE_TOOLKIT_MAX_DECODED_BYTES=str(4 * 1024**3),
                )
                begin = monotonic()
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    __file__,
                    "--worker",
                    json.dumps(case),
                    base,
                    cwd=tmp,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                peak = 0
                child = psutil.Process(proc.pid)

                async def sample_memory():
                    nonlocal peak
                    while proc.returncode is None:
                        try:
                            peak = max(peak, child.memory_info().rss)
                        except psutil.NoSuchProcess:
                            return
                        await asyncio.sleep(0.2)

                rss = asyncio.create_task(sample_memory())
                task = asyncio.create_task(proc.communicate())
                try:
                    stdout, stderr = await asyncio.wait_for(asyncio.shield(task), deadline)
                    if proc.returncode:
                        raise RuntimeError(
                            "Benchmark worker exited without a result: " + stderr.decode()[-500:]
                        )
                    result = json.loads(stdout.splitlines()[-1])
                except asyncio.TimeoutError:
                    result = {"status": "deadline_exceeded"}
                finally:
                    if proc.returncode is None:
                        proc.kill()
                    await task
                    await rss
                result["sampled_peak_rss_bytes"] = peak
                result["wall_seconds"] = round(monotonic() - begin, 3)
        finally:
            await runner.cleanup()
        return dict(
            case=case,
            **result,
            http={
                phase: (
                    dict(**counts, statuses=meter.status[phase])
                    if phase == "cold" or meter.phase == "warm"
                    else None
                )
                for phase, counts in meter.counts.items()
            },
        )


async def run(args):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ["chirps_v3_daily_rnl", provider, n, layout, years]
        for years in ([args.one_site_years] if args.one_site_years else [1, 30])
        for n in ([1] if args.one_site_years else [1, 10, 100])
        for layout in (["clustered"] if n == 1 else ["clustered", "dispersed"])
        for provider in ["dynamical", "huggingface"]
    ]
    report = dict(
        measured_utc=datetime.now(timezone.utc).isoformat(),
        python=sys.version.split()[0],
        versions={
            k: version(k)
            for k in ["climate-toolkit", "aiohttp", "icechunk", "zarr", "fsspec", "xarray"]
        },
        deadline_seconds=args.deadline,
        workers=2,
        decoded_budget_bytes=4 * 1024**3,
        results=[],
    )
    path = OUTPUT / (
        f"one-site-{args.one_site_years}y.json" if args.one_site_years else "matrix.json"
    )
    for case in cases:
        result = await measure(case, args.deadline, OUTPUT)
        report["results"].append(result)
        with tempfile.NamedTemporaryFile(mode="w", dir=OUTPUT, delete=False) as out:
            json.dump(report, out, indent=2)
            out.write("\n")
        os.replace(out.name, path)
        print(case[1:], result["status"], result["http"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--one-site-years",
        type=int,
        choices=(1, 30),
        help="Run just the two Nairobi cases for this window",
    )
    parser.add_argument("--deadline", type=int, default=60)
    parser.add_argument("--worker", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        measured_worker(json.loads(args.worker[0]), args.worker[1])
    else:
        asyncio.run(run(args))
