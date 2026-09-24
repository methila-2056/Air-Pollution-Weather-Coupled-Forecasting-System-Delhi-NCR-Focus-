"""Tests for coupling-state persistence — SIH26082 Phase 30 (allow_add).

The seeded "Anand Vihar" station has wind 1.6 m/s, PBL 180 m, 12h of pollution
and 5 stored fires, so all nine coupling features are computable: the
write-through snapshot must be persisted on every coupling-features call and
be retrievable via the new state endpoints.
"""


def _feature_body(client):
    resp = client.get("/api/coupling/features/Anand Vihar")
    assert resp.status_code == 200
    return resp.json()


def test_features_endpoint_carries_state_labels(client, db_session):
    body = _feature_body(client)
    assert body["coupling_state"] in {"NONE", "LOW", "MODERATE", "HIGH"}
    assert body["data_quality"] == "GOOD"
    assert isinstance(body["coupling_domains"], str) and len(body["coupling_domains"]) > 0


def test_features_compute_persists_snapshot(client, db_session):
    body = _feature_body(client)
    resp = client.get("/api/coupling/state/Anand Vihar")
    assert resp.status_code == 200
    state = resp.json()
    assert state["station"] == "Anand Vihar"
    assert state["computed_at"] is not None
    assert state["coupling_state"] == body["coupling_state"]
    assert state["data_quality"] == body["data_quality"]
    assert state["coupling_domains"] == body["coupling_domains"]
    assert state["dispersion_potential"] == body["features"]["dispersion_potential"]["value"]
    assert state["accumulation_potential"] == body["features"]["accumulation_potential"]["value"]
    assert state["fire_transport_influence"] == body["features"]["fire_transport_influence"]["value"]
    assert state["meteorology_pollution_interaction"] == body["features"]["meteorology_pollution_interaction"]["value"]


def test_persisted_snapshot_reflects_stored_observations(client, db_session):
    body = _feature_body(client)
    state = client.get("/api/coupling/state/Anand Vihar").json()
    assert state["pbl_height_m"] == 180.0
    assert state["wind_speed_mps"] == 1.6
    assert state["fire_count"] == body["inputs"]["fire_count"] and state["fire_count"] > 0
    assert state["inversion_detected"] in (True, False)
    assert state["dispersion_potential"] < 0.5
    assert state["accumulation_potential"] > 0.5


def test_state_list_lists_persisted_stations(client, db_session):
    _feature_body(client)
    resp = client.get("/api/coupling/state")
    assert resp.status_code == 200
    list_body = resp.json()
    assert list_body["count"] >= 1
    names = {s["station"] for s in list_body["states"]}
    assert "Anand Vihar" in names
    first = list_body["states"][0]
    assert first["coupling_state"] in {"NONE", "LOW", "MODERATE", "HIGH"}
    assert first["data_quality"] in {"UNAVAILABLE", "SPARSE", "PARTIAL", "GOOD"}


def test_state_missing_station_404(client, db_session):
    assert client.get("/api/coupling/state/Not A Station").status_code == 404


def test_state_absent_until_features_computed(client, db_session):
    resp = client.get("/api/coupling/state/RK Puram")
    assert resp.status_code == 404
    body = _feature_body(client)
    assert body["data_quality"] == "GOOD"
