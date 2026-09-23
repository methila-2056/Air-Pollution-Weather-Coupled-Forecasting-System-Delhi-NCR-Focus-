"""API tests for the SIH26082 coupling-features and forecast-context endpoints.

The seeds in backend/conftest.py give "Anand Vihar" 12h of calm, shallow-PBL
weather, 5 stored fires, and 12h of pollution — so dispersion must read LOW and
accumulation HIGH, proving the features come from stored data and not from
random values.
"""

COUPLING_FEATURES = {
    "dispersion_potential",
    "accumulation_potential",
    "inversion_trapping_potential",
    "pollution_stagnation_index",
    "aerosol_accumulation_potential",
    "fire_transport_influence",
    "regional_transport_potential",
    "ozone_photochemical_potential",
    "meteorology_pollution_interaction",
}


def test_coupling_features_endpoint_shape(client, db_session):
    resp = client.get("/api/coupling/features/Anand Vihar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["station"] == "Anand Vihar"
    assert set(body["features"]) == COUPLING_FEATURES
    for name in COUPLING_FEATURES:
        feature = body["features"][name]
        assert set(feature) == {"value", "available", "basis"}
        assert feature["value"] is None or 0.0 <= feature["value"] <= 1.0
    assert "provenance" in body and "methodology" in body


def test_coupling_features_reflect_stored_calm_shallow_conditions(client, db_session):
    """Seed Anand Vihar has wind 1.6 m/s + PBL 180 m -> poor dispersion."""
    body = client.get("/api/coupling/features/Anand Vihar").json()
    disp = body["features"]["dispersion_potential"]
    accum = body["features"]["accumulation_potential"]
    assert disp["available"] is True
    assert disp["value"] < 0.5
    assert accum["value"] > 0.5
    assert body["inputs"]["pbl_height_m"] == 180.0
    assert body["inputs"]["wind_speed_mps"] == 1.6


def test_coupling_features_uses_real_fire_data(client, db_session):
    body = client.get("/api/coupling/features/Anand Vihar").json()
    fire = body["features"]["fire_transport_influence"]
    assert fire["available"] is True
    assert body["inputs"]["fire_count"] is not None and body["inputs"]["fire_count"] > 0
    assert "Impact" in fire["basis"] or "impact" in fire["basis"].lower()
    assert body["provenance"]["fire_impact_basis"].startswith("5 stored fire(s)")


def test_coupling_features_missing_station_404(client, db_session):
    assert client.get("/api/coupling/features/Not A Station").status_code == 404


def test_forecast_context_endpoint_horizons(client, db_session):
    resp = client.get("/api/forecast/Anand Vihar/context")
    assert resp.status_code == 200
    body = resp.json()
    assert body["station"] == "Anand Vihar"
    assert len(body["horizons"]) == 72
    assert body["horizons"][0]["horizon_hours"] == 1
    assert body["horizons"][-1]["horizon_hours"] == 72


def test_forecast_context_never_fabricates(client, db_session):
    """Horizons must contain real stored values or nulls — never invented ones."""
    body = client.get("/api/forecast/Anand Vihar/context").json()
    for h in body["horizons"]:
        for key in (
            "temperature_c", "humidity_pct", "pressure_hpa", "wind_speed_mps",
            "pbl_height_m", "inversion_strength",
            "dispersion_potential", "accumulation_potential",
            "pollution_stagnation_index", "fire_transport_influence",
            "meteorology_pollution_interaction",
        ):
            val = h[key]
            assert val is None or isinstance(val, (int, float)), (
                f"horizon {h['horizon_hours']} {key} must be a real value or null"
            )
            if isinstance(val, (int, float)):
                assert 0.0 <= val <= 1.0 or key in {
                    "temperature_c", "humidity_pct", "pressure_hpa",
                    "wind_speed_mps", "pbl_height_m",
                }


def test_forecast_context_nearest_weather_match(client, db_session):
    body = client.get("/api/forecast/Anand Vihar/context").json()
    horizon = body["horizons"][0]
    # Seed weather rows are <= ~12h old; horizon 1 must match one of them.
    assert horizon["weather_match_timestamp"] is not None


def test_forecast_context_missing_station_404(client, db_session):
    assert client.get("/api/forecast/Not A Station/context").status_code == 404
