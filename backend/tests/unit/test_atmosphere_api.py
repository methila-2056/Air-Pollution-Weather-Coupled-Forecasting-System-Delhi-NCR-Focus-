"""API tests for /api/atmosphere/current."""



def test_atmosphere_current_shape(client, db_session):
    response = client.get("/api/atmosphere/current")
    assert response.status_code == 200
    body = response.json()
    assert body["region"]
    assert body["generated_at"]
    assert body["summary"]["stations_analyzed"] >= 5
    assert body["methodology"]["formulas"]["ventilation_coefficient_m2s"]
    assert "1 - dispersion_quality" in body["methodology"]["formulas"]["trapping_index"]
    assert "surface-temperature" not in body["methodology"]["formulas"].get("inversion_strength", "").lower()


def test_atmosphere_current_indicators(client, db_session):
    body = client.get("/api/atmosphere/current").json()
    station = body["stations"][0]
    for key, prov in (
        ("wind", "DERIVED"),
        ("pbl", "ESTIMATED"),
        ("ventilation", "DERIVED"),
        ("inversion", "ESTIMATED"),
        ("trapping", "DERIVED"),
    ):
        assert station[key]["provenance"] == prov
    assert station["inversion"]["source"] in {"lapse_rate", "pbl_proxy"}
    for feat_key in ("wind", "pbl", "ventilation", "inversion", "trapping"):
        val = station["features"][feat_key]
        assert val is None or 0.0 <= val <= 1.0


def test_atmosphere_current_station_filter(client, db_session):
    body = client.get("/api/atmosphere/current", params={"station_name": "Anand Vihar"}).json()
    assert body["summary"]["stations_analyzed"] == 1
    assert body["stations"][0]["station"] == "Anand Vihar"


def test_atmosphere_current_features_within_bounds_all_stations(client, db_session):
    body = client.get("/api/atmosphere/current").json()
    for station in body["stations"]:
        for key in ("wind", "pbl", "ventilation", "inversion", "trapping"):
            val = station["features"][key]
            assert val is None or 0.0 <= val <= 1.0, f"{station['station']}.{key}={val}"
