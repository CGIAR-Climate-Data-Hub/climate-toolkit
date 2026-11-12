from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


def test_probe_pacing_honors_deadline_before_next_request(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from probe_chc_backup import RangeReader

    with RangeReader("https://example.test/data", 1024, 1, min_request_interval=3) as reader:
        reader.last_request = reader.deadline - 0.5
        monkeypatch.setattr(
            reader.session, "get", Mock(side_effect=AssertionError("unexpected HTTP"))
        )
        with pytest.raises(TimeoutError, match="budget exhausted"):
            reader.fetch(0, 1)
        assert reader.requests == reader.bytes == 0


def test_probe_stops_after_http_429(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from probe_chc_backup import RangeReader

    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "120"
    response.raw = Mock()
    with RangeReader("https://example.test/data", 1024, 5) as reader:
        get = Mock(return_value=response)
        monkeypatch.setattr(reader.session, "get", get)
        with pytest.raises(requests.HTTPError):
            reader.fetch(0, 1)
        with pytest.raises(RuntimeError, match="rate limited"):
            reader.fetch(2, 3)
        assert reader.retry_after == "120"
        assert reader.bytes == 0
        get.assert_called_once()
