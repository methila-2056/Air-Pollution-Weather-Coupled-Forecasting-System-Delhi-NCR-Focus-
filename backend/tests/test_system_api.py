def test_system_status(client):
    response = client.get("/api/system")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "AeroCast-NCR"
    assert body["database"] in {"connected", "disconnected"}
    assert "weather_forecast" in body["engines"]
    assert "ctm_hysplit" in body["engines"]
    assert "ctm_wrf_chem" in body["engines"]
    assert "imd" in body["engines"]
    assert "cpcb" in body["engines"]
    assert "firms" in body["engines"]
    for key, engine in body["engines"].items():
        assert {"source", "status", "note"} <= set(engine)
    assert set(body["run_mode"]) >= {
        "environment",
        "live_refresh_enabled",
        "demo_hydrate_empty_db",
        "explanation",
    }