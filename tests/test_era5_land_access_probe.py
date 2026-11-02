"""Diagnostic credential isolation and bounded metadata regression checks."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


spec = importlib.util.spec_from_file_location(
    "era5_land_probe", Path(__file__).resolve().parents[1] / "scripts/probe_era5_land_access.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def transport(monkeypatch):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = [b'{"zarr_format":3,"node_type":"group"}']
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = response
    monkeypatch.setattr(probe.requests, "Session", lambda: session)
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)
    return session, response


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_auth_never_reads_or_reports_remote_error(transport, status):
    session, response = transport
    response.status_code = status
    response.iter_content.return_value = [b"echoed secret-token"]
    result = probe.probe_metadata(probe.CDS_ROOT + "/metadata", key="secret-token")
    assert result["status"] == "authentication_rejected"
    assert result["attempts"] == 1
    assert "secret-token" not in json.dumps(result)
    response.iter_content.assert_not_called()
    assert session.trust_env is False
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_anonymous_probe_does_not_inherit_credentials(transport):
    session, response = transport
    response.status_code = 401
    assert probe.probe_metadata(probe.EDH_DAILY)["status"] == "authentication_required"
    assert session.get.call_args.kwargs["headers"] == {}
    assert session.trust_env is False


@pytest.mark.parametrize("url", [probe.EDH_DAILY, probe.CDS_ROOT + ".example.org/metadata"])
def test_credentials_are_restricted_to_cds_host(transport, url):
    with pytest.raises(ValueError, match="official CDS"):
        probe.probe_metadata(url, key="secret-token")
    transport[0].get.assert_not_called()


def test_redirect_not_followed(transport):
    session, response = transport
    response.status_code = 302
    assert (
        probe.probe_metadata(probe.CDS_ROOT + "/metadata", key="secret")["status"] == "http_error"
    )
    response.iter_content.assert_not_called()
    session.get.assert_called_once()


def test_metadata_limit_is_enforced(transport, monkeypatch):
    monkeypatch.setattr(probe, "MAX_METADATA_BYTES", 4)
    result = probe.probe_metadata(probe.EDH_DAILY)
    assert result["status"] == "invalid_metadata"
    assert "metadata_sha256" not in result


def test_variable_contract_is_reported(transport):
    _, response = transport
    response.iter_content.return_value = [
        json.dumps(
            {
                "metadata": {
                    "t2m/.zarray": {"shape": [24, 4, 8], "chunks": [24, 4, 8], "dtype": "<f4"},
                    "t2m/.zattrs": {
                        "units": "K",
                        "_ARRAY_DIMENSIONS": ["time", "latitude", "longitude"],
                    },
                }
            }
        ).encode()
    ]
    result = probe.probe_metadata(probe.CDS_ROOT + "/.zmetadata", expected_variables=["t2m", "d2m"])
    assert result["status"] == "missing_variables"
    assert result["missing_variables"] == ["d2m"]
    assert result["arrays"]["t2m"]["units"] == "K"
    assert len(result["metadata_sha256"]) == 64


def test_transient_server_failure_retries_once(transport):
    session, response = transport
    response.status_code = 503
    result = probe.probe_metadata(probe.EDH_DAILY)
    assert result["status"] == "http_error"
    assert session.get.call_count == 2
    response.iter_content.assert_not_called()


def test_missing_key_skips_cds_and_never_sends_it_to_edh(monkeypatch):
    monkeypatch.setattr(probe, "cds_key", lambda: None)
    calls = []

    def read(url, **kwargs):
        calls.append((url, kwargs))
        return {"status": "authentication_required"}

    monkeypatch.setattr(probe, "probe_metadata", read)
    result = probe.run(authenticated=True)
    assert all(c["status"] == "missing_credentials" for c in result["cases"][:4])
    assert calls == [(probe.EDH_DAILY, {})]


def test_cds_key_config_errors_do_not_escape(monkeypatch, tmp_path):
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.setattr(probe.Path, "home", lambda: tmp_path)
    (tmp_path / ".cdsapirc").write_text("key: [secret-token\n")
    assert probe.cds_key() is None
