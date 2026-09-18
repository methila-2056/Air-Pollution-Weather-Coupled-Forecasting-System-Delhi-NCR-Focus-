"""Unit tests for the gated IMD weather API adapter (WS-3).

The official api.imd.gov.in gateway requires an API key / IP whitelist and
answers 401 otherwise — the adapter must report that honestly and never
fabricate IMD values. Valid-path parsing is asserted against the public
API-reference field names (Todays_Forecast_Max_Temp / Day_2_Max_Temp …).
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.app.api import imd as imd_api
from backend.app.services import imd_weather as imd


def _fake_settings(**overrides):
    class S:
        imd_api_key = ""
        imd_station_id = "42182"
        imd_api_base = "https://api.imd.gov.in/api/v1"

        def __init__(self):
            for k, v in overrides.items():
                setattr(self, k, v)

    return S()


def _resp(status=200, payload=None, text="ok"):
    class R:
        status_code = status

        def json(self):
            return payload

        @property
        def text(self):
            return text

    return R()


def _representative_payload():
    p = {
        "Todays_Forecast_Max_Temp": 28.0,
        "Todays_Forecast_Min_temp": 12.5,
        "Todays_Forecast": "Partly cloudy sky",
        "Date": "17-09-2026",
    }
    for k in range(2, 8):
        p[f"Day_{k}_Max_Temp"] = 27.0 + k * 0.5
        p[f"Day_{k}_Min_temp"] = 11.0
        p[f"Day_{k}_Forecast"] = f"Mainly clear sky (day {k})"
    return p


def _stub_get(monkeypatch, status=200, payload=None, text="ok"):
    resp = _resp(status, payload, text)
    monkeypatch.setattr(imd.requests, "get", lambda *a, **k: resp)


def test_no_key_is_honest_reason(monkeypatch):
    _stub_get(monkeypatch, status=401)
    reasons = imd.imd_reasons(_fake_settings())
    assert any("401" in r for r in reasons)
    assert any("IMD_API_KEY" in r for r in reasons)


def test_fetch_401_raises(monkeypatch):
    _stub_get(monkeypatch, status=401)
    with pytest.raises(imd.IMDApiUnavailable):
        imd.fetch_city_forecast(settings=_fake_settings())


def test_fetch_http_error_raises(monkeypatch):
    _stub_get(monkeypatch, status=500)
    with pytest.raises(imd.IMDApiUnavailable):
        imd.fetch_city_forecast(settings=_fake_settings())


def test_fetch_non_json_raises(monkeypatch):
    _stub_get(monkeypatch, status=200, text="<html>")
    with pytest.raises(imd.IMDApiUnavailable):
        imd.fetch_city_forecast(settings=_fake_settings())


def test_fetch_garbage_payload_raises(monkeypatch):
    _stub_get(monkeypatch, payload={"unrelated": 1})
    with pytest.raises(imd.IMDApiUnavailable):
        imd.fetch_city_forecast(settings=_fake_settings())


def test_parse_real_shaped_payload(monkeypatch):
    _stub_get(monkeypatch, payload=_representative_payload())
    result = imd.fetch_city_forecast(settings=_fake_settings(imd_api_key="k"))
    assert result["station_id"] == "42182"
    assert result["station_name"] == "Delhi/Safdarjung"
    assert result["fetched_at"]
    days = result["days"]
    assert len(days) == 7
    assert days[0]["max_temp_c"] == 28.0
    assert days[0]["min_temp_c"] == 12.5
    assert "cloudy" in days[0]["condition"]
    assert days[5]["day"] == 6
    assert days[5]["max_temp_c"] > 28.0


def test_dataframe_contract(monkeypatch):
    _stub_get(monkeypatch, payload=_representative_payload())
    df, reasons = imd.imd_forecast_dataframe(
        imd.fetch_city_forecast(settings=_fake_settings(imd_api_key="k"))
    )
    assert not df.empty
    assert not reasons
    assert {"time", "station", "imd_max_temp_c", "imd_min_temp_c",
            "imd_condition", "imd_source"}.issubset(df.columns)
    assert len(df) == 7


def test_nothing_returned_when_garbage(monkeypatch):
    _stub_get(monkeypatch, payload={"nope": 1})
    df, reasons = imd.imd_forecast_dataframe()
    assert df.empty
    assert reasons


def test_router_unavailable_reports_reasons(monkeypatch):
    _stub_get(monkeypatch, status=401)
    resp = imd_api.imd_forecast()
    assert resp.available is False
    assert any("401" in r for r in resp.reasons)


def test_router_success(monkeypatch):
    _stub_get(monkeypatch, payload=_representative_payload())
    resp = imd_api.imd_forecast()
    assert resp.available is True
    assert resp.station_id == "42182"
    assert len(resp.days) == 7
    assert resp.days[0].max_temp_c == 28.0


def test_build_dataset_glue_warns_when_missing(tmp_path, capsys):
    from scripts.build_dataset import load_imd

    assert load_imd(tmp_path).empty
    assert "IMD forecasts unavailable" in capsys.readouterr().out


def test_build_dataset_glue_loads_real_csv(tmp_path):
    from scripts.build_dataset import load_imd

    csv = tmp_path / "imd_forecast.csv"
    pd.DataFrame({
        "time": ["2026-09-17"],
        "station": ["Delhi/Safdarjung"],
        "imd_max_temp_c": [28.0],
        "imd_min_temp_c": [12.5],
        "imd_condition": ["Partly cloudy sky"],
        "imd_source": ["IMD city forecast (api.imd.gov.in)"],
    }).to_csv(csv, index=False)

    df = load_imd(tmp_path)
    assert not df.empty
    assert df["imd_max_temp_c"].iloc[0] == 28.0


def test_build_dataset_glue_merges_imd_columns():
    from scripts.build_dataset import merge_datasets

    base = pd.DataFrame({"time": ["2026-09-17"], "station": ["Anand_Vihar"],
                         "temp": [26.0]})
    imd_df = pd.DataFrame({"time": ["2026-09-17"], "station": ["Anand_Vihar"],
                           "imd_max_temp_c": [28.0], "imd_condition": ["cloudy"]})
    out = merge_datasets(base, pd.DataFrame(), pd.DataFrame(),
                         pd.DataFrame(), imd_df)
    assert out["imd_max_temp_c"].iloc[0] == 28.0
    assert "imd_condition" in out.columns
