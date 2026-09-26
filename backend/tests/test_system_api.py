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
    for _key, engine in body["engines"].items():
        assert {"source", "status", "note"} <= set(engine)
    assert set(body["run_mode"]) >= {
        "environment",
        "live_refresh_enabled",
        "demo_hydrate_empty_db",
        "explanation",
    }
    # The pre-warm state has to be readable over HTTP: it is the only way to tell
    # a working cache warm-up from a dead one without hand-timing requests, and
    # `setting`/`default_applied` say whether it is on because of the environment
    # default or because it was configured explicitly.
    assert isinstance(body["prewarm"]["enabled"], bool)
    assert body["prewarm"]["setting"] in {True, False, None}
    assert isinstance(body["prewarm"]["default_applied"], bool)
    assert body["prewarm"]["state"] in {"disabled", "scheduled", "running", "complete", "cancelled"}


def test_system_status_reports_the_prewarm_sweep(client, monkeypatch):
    from app.services import prewarm

    monkeypatch.setattr(
        prewarm, "_STATUS",
        {"enabled": True, "state": "complete", "entries_warmed": 13, "entries_failed": 0, "seconds": 71.4},
    )
    body = client.get("/api/system").json()
    assert body["prewarm"]["state"] == "complete"
    assert body["prewarm"]["entries_warmed"] == 13
    assert body["prewarm"]["seconds"] == 71.4


def test_system_status_reports_disconnected_db(client, monkeypatch):
    monkeypatch.setattr("app.api.system.database_reachable", lambda: False)
    response = client.get("/api/system")
    assert response.status_code == 200
    assert response.json()["database"] == "disconnected"
