"""Unit + API tests for the pollution-event detection engine and endpoint.

The rule engine (``detect_events_from_series``) is pure and deterministic —
no DB, no network — so the detection rules are tested directly on fabricated
forecast series. The API is tested with the service mocked so the endpoint's
routing / error translation is exercised without needing trained models.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services import pollution_event_service as svc

BASE = datetime(2026, 9, 12, 0, 0)


def _series(values, start=BASE, step_h=1, bounds=None):
    """Build an hourly forecast series of ``{timestamp, predicted_pm25, ...}``."""
    points = []
    for i, v in enumerate(values):
        pt = {
            "timestamp": start + timedelta(hours=i * step_h),
            "forecast_horizon": 1 + i,
            "predicted_pm25": v,
        }
        if bounds:
            lo, hi = bounds
            pt["pm25_lower_bound"] = lo
            pt["pm25_upper_bound"] = hi
        points.append(pt)
    return points


def _atm(**overrides):
    atm = {
        "wind": {"wind_speed_mps": 4.0},
        "pbl": {"pbl_height_m": 800.0},
        "ventilation": {"ventilation_coefficient_m2s": 3200.0},
        "inversion": {"detected": False, "source": "pbl_proxy", "strength": 0.1},
    }
    atm.update(overrides)
    return atm


def _good_dispersion_atm():
    return _atm(
        wind={"wind_speed_mps": 5.0},
        pbl={"pbl_height_m": 900.0},
        ventilation={"ventilation_coefficient_m2s": 4500.0},
        inversion={"detected": False, "source": "pbl_proxy", "strength": 0.0},
    )


def _poor_dispersion_atm():
    return _atm(
        wind={"wind_speed_mps": 1.0},
        pbl={"pbl_height_m": 120.0},
        ventilation={"ventilation_coefficient_m2s": 120.0},
        inversion={"detected": False, "source": "pbl_proxy", "strength": 0.0},
    )


def _run(points, baseline=None, atmosphere=None, **kwargs):
    return svc.detect_events_from_series(
        points,
        baseline,
        atmosphere if atmosphere is not None else _atm(),
        station_name="Anand Vihar",
        uncertainty_method="split-conformal",
        coverage_target=0.9,
        test_metrics={},
        now=points[-1]["timestamp"] + timedelta(hours=1),
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# pollution_surge
# ─────────────────────────────────────────────────────────────────────────────


class TestSurge:
    def test_detects_surge_above_baseline_and_naaqs(self):
        values = [40] * 12 + [100] * 12 + [40] * 12
        events = _run(_series(values, bounds=(95, 105)), baseline=50.0)
        surges = [e for e in events if e["event_type"] == "pollution_surge"]
        assert len(surges) == 1
        ev = surges[0]
        assert ev["expected_peak"] == 100.0
        assert ev["severity"] == "mild"  # < 121 µg/m3 'Very Poor' tier
        assert ev["confidence"]["label"] == "high"
        assert any(f["factor"] == "relative_increase" and f["status"] == "triggering"
                   for f in ev["contributing_factors"])

    def test_surge_marked_severe_when_peak_in_cpcb_severe_tier(self):
        values = [40] * 12 + [260] * 12 + [40] * 12
        events = _run(_series(values), baseline=50.0)
        surges = [e for e in events if e["event_type"] == "pollution_surge"]
        assert surges[0]["severity"] == "severe"

    def test_no_surge_when_baseline_missing(self):
        events = _run(_series([100] * 24), baseline=None)
        assert "pollution_surge" not in {e["event_type"] for e in events}
        assert events == []

    def test_no_surge_when_rise_below_relative_and_naaqs_thresholds(self):
        values = [50] * 24 + [58] * 12
        events = _run(_series(values), baseline=50.0)
        assert "pollution_surge" not in {e["event_type"] for e in events}


# ─────────────────────────────────────────────────────────────────────────────
# pollution_relief
# ─────────────────────────────────────────────────────────────────────────────


class TestRelief:
    def test_detects_relief_with_dispersion_support(self):
        values = [100] * 12 + [40] * 12 + [100] * 12
        events = _run(_series(values), baseline=100.0, atmosphere=_good_dispersion_atm())
        reliefs = [e for e in events if e["event_type"] == "pollution_relief"]
        assert len(reliefs) == 1
        ev = reliefs[0]
        assert ev["expected_trough"] == 40.0
        assert ev["severity"] == "significant"  # trough below 60 µg/m3 NAAQS
        assert any(f["factor"] == "relative_decrease" for f in ev["contributing_factors"])

    def test_relief_counts_as_washout_when_drop_45pct(self):
        # 100 -> 40 is a 60% drop: dispersion-support not required (washout rule).
        values = [100] * 12 + [40] * 12
        events = _run(_series(values), baseline=100.0, atmosphere=_poor_dispersion_atm())
        reliefs = [e for e in events if e["event_type"] == "pollution_relief"]
        assert len(reliefs) == 1

    def test_no_relief_without_dispersion_support_and_drop_below_45pct(self):
        values = [100] * 12 + [72] * 12
        events = _run(_series(values), baseline=100.0, atmosphere=_poor_dispersion_atm())
        assert "pollution_relief" not in {e["event_type"] for e in events}


# ─────────────────────────────────────────────────────────────────────────────
# high_risk_episode
# ─────────────────────────────────────────────────────────────────────────────


class TestEpisode:
    def test_detects_sustained_episode_with_active_risk_factor(self):
        values = [200] * 48
        events = _run(_series(values, bounds=(180, 220)), baseline=80.0, atmosphere=_poor_dispersion_atm())
        eps = [e for e in events if e["event_type"] == "high_risk_episode"]
        assert len(eps) == 1
        ev = eps[0]
        assert ev["expected_peak"] == 200.0
        # poor-dispersion atmosphere activates ventilation/PBL/wind factors.
        active = [f for f in ev["contributing_factors"] if f["status"] == "active"]
        assert len(active) >= 3
        assert ev["confidence"]["label"] == "high"
        assert ev["status"] == "active"

    def test_no_episode_when_fewer_than_24_hours(self):
        events = _run(_series([200] * 12), baseline=80.0, atmosphere=_poor_dispersion_atm())
        assert "high_risk_episode" not in {e["event_type"] for e in events}

    def test_no_episode_when_no_risk_factor_active(self):
        events = _run(_series([200] * 48), baseline=80.0, atmosphere=_good_dispersion_atm())
        assert "high_risk_episode" not in {e["event_type"] for e in events}


# ─────────────────────────────────────────────────────────────────────────────
# Methodology / sanity
# ─────────────────────────────────────────────────────────────────────────────


class TestMethodology:
    def test_methodology_documents_rules_and_threshold_sources(self):
        m = svc._methodology()
        rules = m["rules"]
        assert all(k in rules for k in svc.EVENT_TYPES)
        th = m["threshold_documentation"]
        assert th["standards"]["naaqs_pm25_24h_ugm3"] == 60.0
        assert th["standards"]["cpcb_aqi_pm25_very_poor_min_ugm3"] == 121.0
        assert th["operational_conventions"]["surge_relative_increase_pct"] == 30.0
        assert th["operational_conventions"]["relief_relative_decrease_pct"] == 25.0

    def test_empty_series_returns_no_events(self):
        assert svc.detect_events_from_series([], None, _atm()) == []


# ─────────────────────────────────────────────────────────────────────────────
# API layer
# ─────────────────────────────────────────────────────────────────────────────


def _payload(station="Anand Vihar"):
    now = datetime(2026, 9, 12, 12, 0)
    return {
        "station": station,
        "station_id": 1,
        "generated_at": now,
        "release_time": now,
        "data_as_of": now,
        "model": "xgboost",
        "forecast_strategy": "direct multi-horizon",
        "uncertainty_method": "split-conformal",
        "coverage_target": 0.9,
        "horizon_hours": 48,
        "baseline_pm25_ugm3": 72.0,
        "forecast_peak_pm25_ugm3": 210.0,
        "events": [{
            "event_type": "pollution_surge",
            "station": station,
            "status": "forecast",
            "start_time": now,
            "end_time": None,
            "expected_peak": 210.0,
            "expected_peak_time": now,
            "expected_trough": None,
            "expected_trough_time": None,
            "severity": "moderate",
            "severity_label": "Moderate surge",
            "confidence": {
                "label": "high",
                "basis": "Robust margin.",
                "margin_ugm3": 117.0,
                "conformal_half_width_ugm3": 10.0,
                "lower_bound_ugm3": 200.0,
                "upper_bound_ugm3": 220.0,
                "test_r2": 0.91,
                "coverage_target": 0.9,
                "uncertainty_method": "split-conformal",
            },
            "contributing_factors": [
                {"factor": "relative_increase", "status": "triggering", "value": 191.7,
                 "evidence": "baseline 72 -> peak 210", "description": "Forecast peak clears NAAQS."},
            ],
        }],
        "atmosphere": {"wind_speed_mps": 1.2},
        "methodology": {"version": "1.0.0", "rules": {}},
        "notes": [],
    }


class TestEventsApi:
    def test_current_events_for_named_station(self, client, db_session, monkeypatch):
        monkeypatch.setattr(svc, "detect_current_events", lambda *a, **k: _payload("Anand Vihar"))
        response = client.get("/api/events/current?station_name=Anand Vihar")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["station"] == "Anand Vihar"
        assert body["horizon_hours"] == 48
        assert len(body["events"]) == 1
        assert body["events"][0]["event_type"] == "pollution_surge"
        assert body["methodology"]["version"] == "1.0.0"

    def test_current_events_defaults_to_first_station(self, client, db_session, monkeypatch):
        captured = {}
        def fake(db, name, horizon_hours=48):
            captured["name"] = name
            return _payload(name)
        monkeypatch.setattr(svc, "detect_current_events", fake)
        response = client.get("/api/events/current")
        assert response.status_code == 200, response.text
        assert captured["name"] == "Anand Vihar"

    def test_passes_horizon_query(self, client, db_session, monkeypatch):
        captured = {}
        def fake(db, name, horizon_hours=48):
            captured["hours"] = horizon_hours
            return _payload(name)
        monkeypatch.setattr(svc, "detect_current_events", fake)
        client.get("/api/events/current?station_name=Anand Vihar&hours=24")
        assert captured["hours"] == 24

    def test_unknown_station_returns_404(self, client, db_session):
        response = client.get("/api/events/current?station_name=No Such Station")
        assert response.status_code == 404

    def test_service_station_not_found_translates_to_404(self, client, db_session, monkeypatch):
        def boom(db, name, horizon_hours=48):
            raise ValueError("station_not_found: nope")
        monkeypatch.setattr(svc, "detect_current_events", boom)
        response = client.get("/api/events/current?station_name=Anand Vihar")
        assert response.status_code == 404

    def test_service_runtime_failure_translates_to_503(self, client, db_session, monkeypatch):
        def boom(db, name, horizon_hours=48):
            raise RuntimeError("PM2.5 models not trained")
        monkeypatch.setattr(svc, "detect_current_events", boom)
        response = client.get("/api/events/current?station_name=Anand Vihar")
        assert response.status_code == 503

    def test_service_unexpected_value_error_translates_to_422(self, client, db_session, monkeypatch):
        def boom(db, name, horizon_hours=48):
            raise ValueError("malformed_feature_row")
        monkeypatch.setattr(svc, "detect_current_events", boom)
        response = client.get("/api/events/current?station_name=Anand Vihar")
        assert response.status_code == 422
