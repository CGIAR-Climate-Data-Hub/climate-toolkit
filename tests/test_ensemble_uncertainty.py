"""Verify pairing, model coverage and period/season separation in uncertainty plots."""

import base64
import io
import re
import sys

import pandas as pd
import pytest

from climate_toolkit.visualization.ensemble import write_ensemble_uncertainty


def _model(name, baseline, future, change):
    block = {
        "precipitation": {
            "total_mm": {"baseline_avg": baseline, "future_avg": future, "diff": change}
        }
    }
    return {
        "model": name,
        "overall_statistics": block,
        "season_statistics": {
            "windows": [{"window": "03-01:05-31", "season_number": 1, "diff": block}]
        },
    }


def _result():
    return {
        "baseline_period": "1991-2010",
        "future_period": "2041-2060",
        "scenario": "ssp245",
        "models_used": ["A", "B", "C"],
        "models_failed": [{"model": "D", "error": "<offline>"}],
        "fixed_season": "03-01:05-31,10-01:12-31",
        "per_model_results": [
            _model("A", 5.0, 0.0, -5.0),
            _model("B", 99.0, 103.0, 4.0),
            _model("C", 0.0, float("inf"), None),
        ],
    }


def test_report_retains_pairs_failed_models_and_absent_window(tmp_path):
    path = tmp_path / "out" / "uncertainty.html"
    write_ensemble_uncertainty(
        {
            "ssp245": _result(),
            "ssp585": {
                "error": "All models failed.",
                "failed_models": [{"model": "D", "error": "<fetch>"}],
            },
        },
        path,
    )
    html = path.read_text()
    assert html.count("data:image/png;base64,") == 3
    assert "&lt;offline&gt;" in html and "&lt;fetch&gt;" in html
    assert "ssp585" in html
    encoded = re.search(r'href="data:text/csv;base64,([^"]+)"', html)[1]
    rows = pd.read_csv(io.BytesIO(base64.b64decode(encoded)))
    assert len(rows) == 4 * 4 * 3
    precip = rows[rows.metric == "Precipitation"]
    annual = precip[precip.window == "Annual"].set_index("model")
    assert annual.status.to_dict() == {"A": "paired", "B": "paired", "C": "missing", "D": "failed"}
    assert annual.loc["A", ["baseline", "future", "change"]].tolist() == [5.0, 0.0, -5.0]
    assert annual.loc["B", "change"] == 4
    assert annual.loc[["C", "D"], ["baseline", "future", "change"]].isna().all().all()
    assert set(precip[precip.window.str.startswith("Season 2")].status) == {"missing", "failed"}


def test_single_model_and_detected_season(tmp_path):
    report = _result()
    m = report["per_model_results"][0]
    m["season_statistics"] = {"diff": m["overall_statistics"]}
    report.update(fixed_season=None, models_used=["A"], models_failed=[], per_model_results=[m])
    path = tmp_path / "single.html"
    write_ensemble_uncertainty(report, path)
    assert "Detected seasons (pooled)" in path.read_text()
    with pytest.raises(ValueError, match="periods-ensemble"):
        write_ensemble_uncertainty({"baseline_period": "bad"}, path)
    assert "Detected seasons (pooled)" in path.read_text()


def test_cli_keeps_failed_scenario_visible(tmp_path, monkeypatch):
    from climate_toolkit.compare_periods import ensemble_periods as ep

    html = tmp_path / "report.html"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "periods-ensemble",
            "--location=0,0",
            "--baseline-start=1991",
            "--baseline-end=2010",
            "--future-start=2041",
            "--future-end=2060",
            "--scenarios=ssp245,ssp585",
            "--quiet",
            "--uncertainty-html",
            str(html),
        ],
    )
    monkeypatch.setattr(
        ep,
        "ensemble_compare",
        lambda **kw: _result() if kw["scenario"] == "ssp245" else {"error": "scenario unavailable"},
    )
    monkeypatch.setattr(ep, "print_report", lambda *args, **kw: None)
    assert ep.main() == 0
    assert "scenario unavailable" in html.read_text()


def test_interval_matches_empirical_percentiles_and_hides_singleton_spread():
    from matplotlib.figure import Figure
    from climate_toolkit.visualization.ensemble import _interval

    axes = Figure().subplots(1, 2)
    _interval(axes[0], pd.Series([-10.0, 0.0, 10.0]), 1, "blue")
    assert [list(c.get_segments()[0][:, 0]) for c in axes[0].collections[1:]] == [
        [-8.0, 8.0],
        [-5.0, 5.0],
    ]
    assert list(axes[0].lines[0].get_xdata()) == [0.0]
    _interval(axes[1], pd.Series([0.0]), 1, "blue")
    assert len(axes[1].collections) == 1
    assert not axes[1].lines
