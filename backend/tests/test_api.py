from datetime import datetime


def test_health(client, db_session):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "AeroCast-NCR API"


def test_data_quality(client, db_session):
    response = client.get("/api/data-quality")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["station_count"] == 5
    assert "tables" in body
    assert "recommendations" in body
    assert body["tables"]["stations"]["total"] == 5
    assert body["tables"]["pollution_readings"]["total"] == 12
    assert "Anand Vihar" in body["forecast_coverage"]


def test_get_stations(client, db_session):
    response = client.get("/api/stations")
    assert response.status_code == 200
    bodies = response.json()
    assert isinstance(bodies, list)
    assert len(bodies) == 5
    names = {b["name"] for b in bodies}
    assert names == {"Anand Vihar", "RK Puram", "ITO", "Dwarka", "Punjabi Bagh"}
    for b in bodies:
        assert {"id", "name", "latitude", "longitude", "city"} <= set(b)
        assert isinstance(b["latitude"], float)
        assert isinstance(b["longitude"], float)


def test_get_station_by_name(client, db_session):
    response = client.get("/api/stations/Anand Vihar")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Anand Vihar"
    assert abs(body["latitude"] - 28.6492) < 0.0001
    assert abs(body["longitude"] - 77.2918) < 0.0001


def test_get_station_not_found(client, db_session):
    response = client.get("/api/stations/Noida Sector 62")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_current_aqi_by_station(client, db_session):
    response = client.get("/api/current/Anand Vihar")
    assert response.status_code == 200
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert body["timestamp"] is not None
    assert body["pm25"] is not None and body["pm25"] > 0
    assert body["pm10"] is not None and body["pm10"] > 0
    assert isinstance(body["aqi"], int) and body["aqi"] > 0
    assert body["aqi_category"] in {"Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"}
    assert body["dominant_pollutant"] in {"pm25", "pm10", "o3", "no2", "so2", "co"}


def test_get_current_aqi_station_not_found(client, db_session):
    response = client.get("/api/current/Noida Sector 62")
    assert response.status_code == 404


def test_get_forecast_by_station(client, db_session):
    response = client.get("/api/forecast/Anand Vihar")
    assert response.status_code == 200
    bodies = response.json()
    assert isinstance(bodies, list)
    assert len(bodies) >= 12
    for b in bodies:
        assert {"timestamp", "horizon_hours", "pm25_pred", "pm10_pred", "aqi_pred", "aqi_category"} <= set(b)


def test_get_forecast_station_not_found(client, db_session):
    response = client.get("/api/forecast/Gurugram")
    assert response.status_code == 404


def test_get_forecast_ncr(client, db_session):
    response = client.get("/api/forecast/ncr")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert set(body.keys()) == {"Anand Vihar", "RK Puram", "ITO", "Dwarka", "Punjabi Bagh"}
    assert isinstance(body["Anand Vihar"], list)


def test_generate_forecast_default(client, db_session):
    response = client.post("/api/forecast/generate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert body["horizons"] == [1, 6, 12, 24, 48, 72]
    assert len(body["forecasts"]) == 6
    for f in body["forecasts"]:
        assert f["pm25_pred"] is not None and f["pm25_pred"] > 0
        assert f["aqi_pred"] is not None and f["aqi_pred"] > 0
        assert f["aqi_category"] in {"Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"}
        assert f["horizon_hours"] in body["horizons"]


def test_generate_forecast_for_station(client, db_session):
    response = client.post(
        "/api/forecast/generate",
        json={"station_name": "Dwarka", "horizons": [3, 24]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["station"] == "Dwarka"
    assert body["horizons"] == [3, 24]
    assert {f["horizon_hours"] for f in body["forecasts"]} == {3, 24}
    generated = client.get("/api/forecast/Dwarka")
    assert generated.status_code == 200
    assert len(generated.json()) >= 2


def test_generate_forecast_persists_alerts(client, db_session):
    before = client.get("/api/alerts").json()
    client.post("/api/forecast/generate", json={"station_name": "Anand Vihar"})
    after = client.get("/api/alerts").json()
    assert len(after) > len(before)


def test_generate_forecast_station_not_found(client, db_session):
    response = client.post("/api/forecast/generate", json={"station_name": "Noida"})
    assert response.status_code == 404


def test_generate_forecast_invalid_horizon(client, db_session):
    response = client.post("/api/forecast/generate", json={"horizons": [100]})
    assert response.status_code == 400
    response = client.post("/api/forecast/generate", json={"horizons": []})
    assert response.status_code == 400


def test_forecast_comparison(client, db_session):
    response = client.get("/api/forecast/comparison/Anand Vihar", params={"hours": 72})
    assert response.status_code == 200
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert len(body["points"]) >= 12
    for p in body["points"]:
        assert {"timestamp", "actual_aqi", "predicted_aqi", "actual_pm25", "predicted_pm25", "delta"} <= set(p)
        assert p["actual_aqi"] is not None
        assert p["predicted_aqi"] is not None


def test_forecast_comparison_not_found(client, db_session):
    response = client.get("/api/forecast/comparison/Noida")
    assert response.status_code == 404


def test_forecast_comparison_no_data(client, db_session):
    response = client.get("/api/forecast/comparison/Punjabi Bagh")
    assert response.status_code == 404


def test_get_weather(client, db_session):
    response = client.get("/api/weather/Anand Vihar")
    assert response.status_code == 200
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert body["temperature"] is not None
    assert body["wind_speed"] is not None
    assert body["pbl_height"] == 180.0


def test_get_weather_not_found(client, db_session):
    response = client.get("/api/weather/Gurugram")
    assert response.status_code == 404


def test_get_weather_history(client, db_session):
    response = client.get("/api/weather/Anand Vihar/history", params={"hours": 24})
    assert response.status_code == 200
    bodies = response.json()
    assert isinstance(bodies, list)
    assert len(bodies) == 12
    for b in bodies:
        assert b["station"] == "Anand Vihar"
        assert b["pbl_height"] is not None


def test_get_weather_history_not_found(client, db_session):
    response = client.get("/api/weather/RK Puram/history")
    assert response.status_code == 404


def test_get_inversion(client, db_session):
    response = client.get("/api/inversion/Anand Vihar")
    assert response.status_code == 200
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert body["pbl_height"] == 180.0
    assert body["inversion_detected"] is True
    assert body["inversion_strength"] == "Moderate"


def test_get_inversion_not_found(client, db_session):
    response = client.get("/api/inversion/Faridabad")
    assert response.status_code == 404


def test_get_fire_activity(client, db_session):
    response = client.get("/api/fire-activity")
    assert response.status_code == 200
    body = response.json()
    assert body["total_fires"] >= 4
    assert body["high_confidence_fires"] >= 2
    assert body["mean_frp"] > 0


def test_get_fire_transport_direction(client, db_session):
    response = client.get("/api/fire/transport")
    assert response.status_code == 200
    body = response.json()
    assert body["from_direction"] == "NW"
    assert body["to_direction"] == "SE"
    assert "→" in body["label"]
    assert body["wind_speed"] is not None
    assert body["basis"] == "live weather data"


def test_get_plume_risk(client, db_session):
    response = client.get("/api/plume-risk")
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"LOW", "MODERATE", "HIGH"}
    assert 0 <= body["risk_score"] <= 1
    assert body["fire_count"] >= 4
    assert "→" in body["transport_direction"]
    assert body["wind_speed"] > 0
    assert body["distance_nearest_fire"] > 0
    assert len(body["factors"]) >= 2


def test_get_explanation(client, db_session):
    response = client.get("/api/explanation/Anand Vihar")
    assert response.status_code == 200
    body = response.json()
    assert body["station"] == "Anand Vihar"
    assert body["prediction"]["pm25_pred"] is not None
    assert body["prediction"]["aqi_pred"] is not None
    assert len(body["top_features"]) >= 3
    for feature in body["top_features"]:
        assert {"feature", "importance", "direction", "description"} <= set(feature)
    assert len(body["natural_language"]) >= 1


def test_get_explanation_not_found(client, db_session):
    response = client.get("/api/explanation/Ghaziabad")
    assert response.status_code == 404


def test_get_alerts(client, db_session):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    bodies = response.json()
    assert isinstance(bodies, list)
    assert len(bodies) >= 1
    for b in bodies:
        assert b["station"] == "Anand Vihar"
        assert b["alert_level"] in {"WATCH", "ADVISORY", "WARNING", "SEVERE"}
        assert b["title"]


def test_get_alerts_empty(client, db_session):
    from app.database import SessionLocal
    from app.models.db_models import Alert
    with SessionLocal() as session:
        session.query(Alert).delete()
        session.commit()
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert response.json() == []


def test_get_model_metrics(client, db_session):
    response = client.get("/api/model/metrics")
    assert response.status_code == 200
    bodies = response.json()
    assert isinstance(bodies, list)
    assert len(bodies) == 2
    for b in bodies:
        assert b["model_name"] in {"xgboost", "random_forest"}
        assert b["pollutant"] in {"pm25", "pm10"}
        assert b["mae"] > 0
        assert 0 < b["r2"] <= 1


def test_save_model_metrics(client, db_session):
    payload = {
        "model_name": "xgboost",
        "pollutant": "no2",
        "horizon_hours": 48,
        "mae": 8.2,
        "rmse": 12.7,
        "r2": 0.91,
        "mape": 11.3,
    }
    response = client.post("/api/model/metrics", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] is not None
    assert body["model_name"] == "xgboost"
    assert body["pollutant"] == "no2"
    assert body["r2"] == 0.91

    fetched = client.get("/api/model/metrics").json()
    assert any(m["pollutant"] == "no2" and m["horizon_hours"] == 48 for m in fetched)


def test_save_model_metrics_validation(client, db_session):
    response = client.post("/api/model/metrics", json={"model_name": "", "pollutant": "pm2", "horizon_hours": 24})
    assert response.status_code == 400
    response = client.post("/api/model/metrics", json={"model_name": "nn", "pollutant": "pm2"})
    assert response.status_code in (400, 422)


def test_unknown_route(client, db_session):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404