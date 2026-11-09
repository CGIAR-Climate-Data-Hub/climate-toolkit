"""Check the opt-in benchmark meter against known HTTP bodies on loopback."""

import asyncio
from contextlib import AsyncExitStack
import gzip
from pathlib import Path

import pytest


def test_count_encoded_body_redirect_head_and_range(monkeypatch):
    pytest.importorskip("aiohttp")
    pytest.importorskip("psutil")
    from aiohttp import ClientSession, TraceConfig, web
    from aiohttp.test_utils import TestServer

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from benchmark_chirps_transport import Meter

    async def exercise():
        compressed = gzip.compress(b"precipitation" * 2000, mtime=0)

        async def serve(request):
            if request.path == "/redirect":
                return web.Response(
                    status=302, body=b"302", headers={"Location": "https://cdn-lfs.hf.co/data"}
                )
            if request.path == "/data":
                return web.Response(body=compressed, headers={"Content-Encoding": "gzip"})
            assert request.headers["Range"] == "bytes=0-3"
            return web.Response(status=206, body=b"rain", headers={"Content-Range": "bytes 0-3/8"})

        async with AsyncExitStack() as stack:
            upstream = web.Application()
            upstream.router.add_route("*", "/{path}", serve)
            server = await stack.enter_async_context(TestServer(upstream))
            meter = Meter()
            trace = TraceConfig()
            trace.on_request_headers_sent.append(meter.sent)
            client = await stack.enter_async_context(
                ClientSession(auto_decompress=False, trace_configs=[trace])
            )

            class LoopbackClient:
                def request(self, method, url, **kwargs):
                    return client.request(method, server.make_url("/" + url.name), **kwargs)

            meter.client = LoopbackClient()
            app = web.Application()
            app.router.add_route("*", "/https/{path:.*}", meter.relay)
            app.router.add_post("/warm", meter.begin_warm)
            relay = await stack.enter_async_context(TestServer(app))
            reader = await stack.enter_async_context(ClientSession(auto_decompress=False))
            prefix = "/https/huggingface.co/datasets/aaguilar90/chirps-v3-daily-rnl/"
            async with reader.get(relay.make_url(prefix + "redirect")) as response:
                assert await response.read() == compressed
            async with reader.head(relay.make_url(prefix + "redirect")) as response:
                assert await response.read() == b""
            async with reader.post(relay.make_url("/warm")) as response:
                assert response.status == 200
            async with reader.get(
                relay.make_url(prefix + "range"), headers={"Range": "bytes=0-3"}
            ) as response:
                assert response.status == 206 and await response.read() == b"rain"
            assert meter.counts["cold"]["requests"] == 4
            assert meter.counts["cold"]["body_bytes"] == 3 + len(compressed)
            assert meter.counts["warm"]["requests"] == 1
            assert meter.counts["warm"]["body_bytes"] == 4

    asyncio.run(exercise())
