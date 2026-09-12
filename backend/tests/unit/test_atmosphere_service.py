"""Unit tests for the atmospheric-condition analysis layer."""

from datetime import datetime, timedelta

import pytest
from app.models.db_models import Station, WeatherReading
from app.services import atmosphere_service as ats


def _first_station(db_session) -> Station:
    return db_session.query(Station).order_by(Station.name).first()


class TestClassifyWind:
    def test_bands(self):
        assert ats.classify_wind(0.3)["category"] == "calm"
        assert ats.classify_wind(1.6)["category"] == "light"
        assert ats.classify_wind(3.0)["category"] == "moderate"
        assert ats.classify_wind(5.0)["category"] == "brisk"
        assert ats.classify_wind(8.0)["category"] == "strong"

    def test_normalized_in_unit_interval(self):
        for speed in (0.0, 0.5, 2.0, 7.0, 15.0):
            assert 0.0 <= ats.classify_wind(speed)["normalized"] <= 1.0
        assert ats.classify_wind(None)["category"] == "unavailable"

    def test_provenance(self):
        assert ats.classify_wind(2.0)["provenance"] == "DERIVED"


class TestClassifyPbl:
    def test_categories(self):
        assert ats.classify_pbl(100)["category"] == "strong_trapping"
        assert ats.classify_pbl(180)["category"] == "moderate_trapping"
        assert ats.classify_pbl(400)["category"] == "weak_trapping"
        assert ats.classify_pbl(1200)["category"] == "good_dispersion"

    def test_estimated_provenance(self):
        assert ats.classify_pbl(400)["provenance"] == "ESTIMATED"
        assert ats.classify_pbl(None)["category"] == "unavailable"


class TestVentilation:
    def test_coefficient_formula(self):
        vent = ats.ventilation_condition(2.0, 500.0)
        assert vent["ventilation_coefficient_m2s"] == 1000.0
        assert vent["category"] == "poor"

        vent = ats.ventilation_condition(3.0, 1500.0)
        assert vent["ventilation_coefficient_m2s"] == 4500.0
        assert vent["category"] == "moderate"

        vent = ats.ventilation_condition(4.0, 2000.0)
        assert vent["ventilation_coefficient_m2s"] == 8000.0
        assert vent["category"] == "good"

    def test_provenance_derived(self):
        assert ats.ventilation_condition(2.0, 500.0)["provenance"] == "DERIVED"
        assert ats.ventilation_condition(None, 500.0)["category"] == "unavailable"


def _add_latest_weather(db_session, station, **kwargs):
    base = datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(minutes=1)
    row = WeatherReading(
        station_id=station.id,
        timestamp=base,
        temperature=kwargs.get("temperature", 22.0),
        humidity=kwargs.get("humidity", 60.0),
        wind_speed=kwargs.get("wind_speed", 2.0),
        wind_direction=kwargs.get("wind_direction", 315.0),
        pbl_height=kwargs.get("pbl_height", 400.0),
        pressure_msl=1013.0,
        surface_pressure=993.0,
    )
    for level in (1000, 925, 850, 700):
        key = f"temperature_{level}hPa"
        if key in kwargs:
            setattr(row, key, kwargs[key])
    db_session.add(row)
    db_session.commit()
    return row


class TestInversion:
    def test_lapse_rate_when_vertical_profile_available(self, db_session):
        station = _first_station(db_session)
        # Positive gradient 1000->925 hPa (20 -> 23 degC) = 4.0 K/100 hPa.
        _add_latest_weather(
            db_session, station, pbl_height=1500.0,
            temperature_1000hPa=20.0, temperature_925hPa=23.0,
        )
        result = ats.analyze_station(db_session, station)
        inv = result["inversion"]
        assert inv["source"] == "lapse_rate"
        assert inv["provenance"] == "DERIVED"
        assert inv["category"] == "strong"
        assert inv["detected"] is True
        assert inv["base_pressure_hpa"] == 1000
        assert inv["top_pressure_hpa"] == 925
        assert inv["strongest_gradient_k100hpa"] == pytest.approx(4.0, abs=0.01)

    def test_pbl_proxy_used_when_profile_unavailable(self, db_session):
        station = _first_station(db_session)
        _add_latest_weather(db_session, station, pbl_height=180.0)
        result = ats.analyze_station(db_session, station)
        inv = result["inversion"]
        assert inv["source"] == "pbl_proxy"
        assert inv["provenance"] == "ESTIMATED"
        assert inv["profile_available"] is False
        assert any("PROXY" in lim.upper() for lim in inv["limitations"])

    def test_proxy_is_never_a_surface_temp_threshold(self, db_session):
        # Identical PBL with wildly different surface temperature must give the
        # same proxy result (no temperature threshold is ever applied).
        station = _first_station(db_session)
        r1 = ats.analyze_station(db_session, station)
        old = db_session.query(WeatherReading).filter(
            WeatherReading.station_id == station.id
        ).order_by(WeatherReading.timestamp.desc()).first()
        old.temperature = -5.0  # extreme surface temp, same PBL
        db_session.commit()
        r2 = ats.analyze_station(db_session, station)
        assert r2["inversion"]["strength"] == r1["inversion"]["strength"]
        assert r2["inversion"]["category"] == r1["inversion"]["category"]


class TestTrapping:
    def test_formula_with_pm25(self):
        wind = ats.classify_wind(1.6)
        pbl = ats.classify_pbl(180.0)
        vent = ats.ventilation_condition(1.6, 180.0)
        inv = {"normalized": 0.64, "category": "moderate", "source": "pbl_proxy",
               "strength": 0.64}
        trap = ats.trapping_index(wind, pbl, vent, inv, pm25=95.0)
        # q = .5*(288/6000) + .2*(180/1500) + .3*(.36) = .024+.024+.108 = .156
        # trap_meteo = .844; pm25_norm = (95-35)/265=.226 ; score=.7*.844+.3*.226
        assert trap["score"] == pytest.approx(0.6587, abs=0.01)
        assert trap["category"] == "high"
        assert trap["provenance"] == "DERIVED"

    def test_meteorology_only_when_pm25_missing(self):
        wind = ats.classify_wind(7.0)
        pbl = ats.classify_pbl(1000.0)
        vent = ats.ventilation_condition(7.0, 1000.0)
        inv = {"normalized": 0.0, "category": "none"}
        trap = ats.trapping_index(wind, pbl, vent, inv, pm25=None)
        assert trap["score"] is not None
        assert trap["category"] == "low"
        assert any("PM2.5" in f for f in trap["factors"])


class TestAnalyzeStation:
    def test_full_structure_and_features(self, db_session):
        station = _first_station(db_session)
        result = ats.analyze_station(db_session, station)
        assert result["station"] == station.name
        assert result["wind"]["provenance"] == "DERIVED"
        assert result["ventilation"]["provenance"] == "DERIVED"
        assert result["pbl"]["provenance"] == "ESTIMATED"
        assert result["inversion"]["provenance"] == "ESTIMATED"
        assert result["trapping"]["provenance"] == "DERIVED"
        for key in ("wind", "pbl", "ventilation", "inversion", "trapping"):
            val = result["features"][key]
            assert val is None or 0.0 <= val <= 1.0
        assert result["inputs"]["vertical_temperature_profile_c"] == {}

    def test_ventilation_uses_latest_weather(self, db_session):
        station = _first_station(db_session)
        result = ats.analyze_station(db_session, station)
        # Seeded weather: wind 1.6 m/s, pbl 180 m.
        assert result["wind"]["category"] == "light"
        assert result["ventilation"]["ventilation_coefficient_m2s"] == pytest.approx(288.0, abs=0.1)


class TestGetCurrent:
    def test_summary_and_stations(self, db_session):
        result = ats.get_current_atmosphere(db_session)
        n_stations = len(db_session.query(Station).all())
        assert result["stations"] and len(result["stations"]) == n_stations
        assert result["summary"]["stations_analyzed"] == n_stations
        assert result["methodology"]["version"]
        assert result["methodology"]["formulas"]["inversion_gradient_k100hpa"]
        assert "inversion_strength" in result["methodology"]["formulas"]
        with_data = [s for s in result["stations"] if s["weather_timestamp"] is not None]
        assert with_data  # Anand Vihar is seeded with weather
        assert all(s["inversion"]["source"] in {"lapse_rate", "pbl_proxy"} for s in with_data)
        assert result["summary"]["inversion_sources_seen"] == ["pbl_proxy"]
        for s in result["stations"]:
            for key in ("wind", "pbl", "ventilation"):
                assert s[key]["provenance"] in {"OBSERVED", "DERIVED", "ESTIMATED"}
            if s["weather_timestamp"] is None:
                assert s["inversion"] is None  # no data -> honestly unavailable

    def test_data_age_reported(self, db_session):
        result = ats.get_current_atmosphere(db_session)
        with_data = [s for s in result["stations"] if s["weather_timestamp"] is not None]
        assert all(s["weather_age_hours"] is not None for s in with_data)
        assert all(s["pollution_age_hours"] is not None for s in with_data)
