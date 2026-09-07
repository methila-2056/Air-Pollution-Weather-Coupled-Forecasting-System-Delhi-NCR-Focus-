"""End-to-end integration tests for AeroCast-NCR.

These tests exercise the full stack: DB seed -> backend services -> API
responses, verifying that machine-learning predictions flow through to the
REST layer with consistent structure and values.
"""

import pytest


class TestForecastPipeline:
    def test_forecast_generate_to_api(self, client, db_session):
        resp = client.post("/api/forecast/generate", json={"station_name": "Anand Vihar"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert len(body["forecasts"]) == 6
        for f in body["forecasts"]:
            assert f["horizon_hours"] in (1, 6, 12, 24, 48, 72)
            assert f["pm25_pred"] > 0
            assert f["aqi_pred"] > 0
            assert f["aqi_category"] in {"Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"}

    def test_forecast_persists_to_db(self, client, db_session):
        client.post("/api/forecast/generate", json={"station_name": "Anand Vihar"})
        resp = client.get("/api/forecast/Anand Vihar")
        assert resp.status_code == 200
        forecasts = resp.json()
        assert len(forecasts) >= 12 + 6
        horizons = {f["horizon_hours"] for f in forecasts[:6]}
        assert 1 in horizons or 6 in horizons

    def test_ncr_aggregate(self, client, db_session):
        resp = client.get("/api/forecast/ncr")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"Anand Vihar", "RK Puram", "ITO", "Dwarka", "Punjabi Bagh"}
        for station, forecasts in body.items():
            assert isinstance(forecasts, list)

    def test_forecast_comparison_flow(self, client, db_session):
        resp = client.get("/api/forecast/comparison/Anand Vihar", params={"hours": 72})
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert len(body["points"]) >= 12
        for p in body["points"]:
            assert {"timestamp", "actual_aqi", "predicted_aqi", "actual_pm25", "predicted_pm25", "delta"} <= set(p)


class TestWeatherAndAtmosphere:
    def test_weather_latest(self, client, db_session):
        resp = client.get("/api/weather/Anand Vihar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert body["pbl_height"] is not None
        assert body["temperature"] is not None
        assert body["wind_speed"] is not None

    def test_weather_history(self, client, db_session):
        resp = client.get("/api/weather/Anand Vihar/history", params={"hours": 24})
        assert resp.status_code == 200
        bodies = resp.json()
        assert len(bodies) == 12
        for b in bodies:
            assert b["station"] == "Anand Vihar"
            assert b["pbl_height"] == 180.0

    def test_inversion_detection(self, client, db_session):
        resp = client.get("/api/inversion/Anand Vihar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert body["pbl_height"] == 180.0
        assert body["inversion_detected"] is True
        assert body["inversion_strength"] == "Moderate"


class TestFireAndPlume:
    def test_fire_activity(self, client, db_session):
        resp = client.get("/api/fire-activity")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_fires"] == 5
        assert body["high_confidence_fires"] == 3
        assert body["mean_frp"] > 0

    def test_transport_direction_station_specific(self, client, db_session):
        resp = client.get("/api/fire/transport", params={"station_name": "Anand Vihar"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert "\u2192" in body["label"]

    def test_plume_risk(self, client, db_session):
        resp = client.get("/api/plume-risk")
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] in {"LOW", "MODERATE", "HIGH"}
        assert 0 <= body["risk_score"] <= 1
        assert body["fire_count"] == 5
        assert body["wind_speed"] > 0
        assert len(body["factors"]) >= 2


class TestExplainability:
    def test_explanation_endpoint(self, client, db_session):
        resp = client.get("/api/explanation/Anand Vihar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        assert len(body["top_features"]) >= 3
        assert len(body["natural_language"]) >= 1
        for ft in body["top_features"]:
            assert {"feature", "importance", "direction", "description"} <= set(ft)

    def test_explanation_fallback_for_other_station(self, client, db_session):
        resp = client.get("/api/explanation/RK Puram")
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "RK Puram"
        assert len(body["top_features"]) >= 3


class TestAlerts:
    def test_alerts_generated_from_forecast(self, client, db_session):
        before = len(client.get("/api/alerts").json())
        client.post("/api/forecast/generate", json={"station_name": "Anand Vihar"})
        after = len(client.get("/api/alerts").json())
        assert after > before

    def test_alert_structure(self, client, db_session):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) >= 1
        for alert in alerts:
            assert alert["station"] == "Anand Vihar"
            assert alert["alert_level"] in {"WATCH", "ADVISORY", "WARNING", "SEVERE"}
            assert alert["title"]


class TestModelMetricsAPI:
    def test_metrics_list(self, client, db_session):
        resp = client.get("/api/model/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert len(metrics) == 2
        for m in metrics:
            assert m["model_name"] in {"xgboost", "random_forest"}
            assert m["pollutant"] in {"pm25", "pm10"}
            assert m["mae"] > 0

    def test_metrics_save_and_retrieve(self, client, db_session):
        payload = {
            "model_name": "xgboost", "pollutant": "o3",
            "horizon_hours": 24, "mae": 7.5, "rmse": 11.0,
            "r2": 0.88, "mape": 9.5,
        }
        resp = client.post("/api/model/metrics", json=payload)
        assert resp.status_code == 201
        fetched = client.get("/api/model/metrics").json()
        assert any(m["pollutant"] == "o3" and m["horizon_hours"] == 24 for m in fetched)


class TestDataQuality:
    def test_data_quality_report(self, client, db_session):
        resp = client.get("/api/data-quality")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["station_count"] == 5
        assert "tables" in body
        assert "recommendations" in body


class TestCouplingFeedback:
    def test_coupling_endpoint_structure(self, client, db_session):
        resp = client.get("/api/coupling/Anand Vihar")
        assert resp.status_code == 200
        body = resp.json()
        assert body["station"] == "Anand Vihar"
        diag = body["diag"]
        assert {"aod_est", "radiation_transmittance", "pbl_suppression_factor",
                "corrected_pbl_height", "stability_coupling_index",
                "feedback_multiplier", "coupling_strength"} <= set(diag)
        assert 0 <= diag["aod_est"] <= 2.5
        assert 0 < diag["pbl_suppression_factor"] <= 1.0
        assert 0 <= diag["stability_coupling_index"] <= 1.0
        assert isinstance(body["narrative"], list) and body["narrative"]

    def test_coupling_high_pm25_drives_stronger_feedback(self):
        from ml.features.coupling import coupling_feedback_score
        heavy = coupling_feedback_score(pm25=250, pbl_height=400, wind_speed=1, hour=13)
        light = coupling_feedback_score(pm25=30, pbl_height=800, wind_speed=6, hour=13)
        assert heavy["stability_coupling_index"] > light["stability_coupling_index"]
        assert heavy["pbl_suppression_factor"] < light["pbl_suppression_factor"]
        assert heavy["feedback_multiplier"] > light["feedback_multiplier"]

    def test_coupling_features_in_feature_vector(self, client, db_session):
        from app.database import SessionLocal
        from app.models.db_models import Station
        from app.services.forecast_service import build_features_from_db
        with SessionLocal() as session:
            station = session.query(Station).filter(Station.name == "Anand Vihar").first()
            features = build_features_from_db(session, station.id)
            assert features["stability_coupling_index"] != 0.0
            assert 0.0 <= features["pbl_suppression_factor"] <= 1.0
            assert features["feedback_multiplier"] > 1.0
            assert 0.0 <= features["aod_est"] <= 2.5
        session.close()
