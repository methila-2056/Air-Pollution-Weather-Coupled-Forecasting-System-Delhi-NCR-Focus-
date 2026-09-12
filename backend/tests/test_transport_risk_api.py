"""API tests for the Estimated Regional Pollution Transport Risk endpoint."""


def test_transport_risk_current_shape(client):
    r = client.get("/api/transport-risk/current")
    assert r.status_code == 200
    body = r.json()
    assert "risk_score" in body
    assert "risk_level" in body
    assert "main_contributing_factors" in body
    assert "upwind_fire_count" in body
    assert "dominant_wind_direction" in body
    assert "atmospheric_condition" in body
    assert "disclaimer" in body
    assert body["risk_level"] in (
        "LOW", "MODERATE", "ELEVATED", "HIGH", "VERY HIGH", "UNAVAILABLE"
    )
    if body["risk_score"] is not None:
        assert isinstance(body["risk_score"], int)
        assert 0 <= body["risk_score"] <= 100


def test_transport_risk_current_window_param(client):
    r = client.get("/api/transport-risk/current", params={"hours": 720})
    assert r.status_code == 200

    bad = client.get("/api/transport-risk/current", params={"hours": 0})
    assert bad.status_code == 422
