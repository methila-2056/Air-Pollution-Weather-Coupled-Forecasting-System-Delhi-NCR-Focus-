import math

import pytest
from app.services.aqi_calculator import (
    IAQI_BREAKPOINTS,
    calculate_aqi,
    calculate_iaqi,
    get_aqi_category,
    get_dominant_pollutant,
)


@pytest.mark.parametrize("pollutant,conc,expected", [
    ("pm25", 0, 0),
    ("pm25", 30, 50),
    ("pm25", 60, 100),
    ("pm25", 250, 400),
    ("pm25", 500, 500),
    ("pm10", 0, 0),
    ("pm10", 600, 500),
    ("o3", 50, 50),
    ("o3", 748, 400),
    ("o3", 1200, 500),
    ("no2", 400, 400),
    ("so2", 2100, 500),
    ("co", 1, 50),
    ("co", 50, 500),
])
def test_calculate_iaqi_boundaries(pollutant, conc, expected):
    assert calculate_iaqi(pollutant, conc) == pytest.approx(expected, abs=0.5)


def test_calculate_iaqi_interpolation():
    assert calculate_iaqi("pm25", 15) == pytest.approx(25, abs=0.5)
    assert calculate_iaqi("pm25", 45) == pytest.approx(74.655, abs=0.5)
    assert calculate_iaqi("pm25", 31) == pytest.approx(51, abs=0.5)


def test_calculate_iaqi_below_zero_clamped():
    assert calculate_iaqi("pm25", -10) == 500


def test_calculate_iaqi_above_max_clamped():
    assert calculate_iaqi("pm25", 9999) == 500
    assert calculate_iaqi("co", 200) == 500


def test_calculate_iaqi_none_and_nan():
    for poll in ("pm25", "pm10", "o3", "no2", "so2", "co"):
        assert calculate_iaqi(poll, None) == 0
        assert calculate_iaqi(poll, float("nan")) == 0


def test_calculate_iaqi_unknown_pollutant():
    assert calculate_iaqi("nope", 100) == 0


def test_all_breakpoints_monotonic_cover():
    for pollutant, bps in IAQI_BREAKPOINTS.items():
        iaqi_values = [bp[2] for bp in bps]
        assert iaqi_values == sorted(iaqi_values)
        lo, hi = bps[0][0], bps[-1][1]
        mid = calculate_iaqi(pollutant, (lo + hi) / 2)
        assert 0 <= mid <= 500


@pytest.mark.parametrize("aqi,expected", [
    (0, ("Good", 1)),
    (50, ("Good", 1)),
    (51, ("Satisfactory", 2)),
    (100, ("Satisfactory", 2)),
    (101, ("Moderate", 3)),
    (200, ("Moderate", 3)),
    (201, ("Poor", 4)),
    (300, ("Poor", 4)),
    (301, ("Very Poor", 5)),
    (400, ("Very Poor", 5)),
    (401, ("Severe", 6)),
    (500, ("Severe", 6)),
])
def test_get_aqi_category_boundaries(aqi, expected):
    assert get_aqi_category(aqi) == expected


def test_get_aqi_category_out_of_range():
    assert get_aqi_category(600) == ("Severe", 6)
    assert get_aqi_category(-1) == ("Severe", 6)


@pytest.mark.parametrize("kwargs", [
    {"pm25": 10},
    {"pm25": 10, "pm10": 20},
    {"pm25": 10, "pm10": 20, "o3": 3},
    {"pm25": 10, "pm10": 20, "o3": 3, "no2": 2},
    {"pm25": 10, "pm10": 20, "o3": 3, "no2": 2, "so2": 1},
    {"pm25": 10, "pm10": 20, "o3": 3, "no2": 2, "so2": 1, "co": 0.1},
])
def test_calculate_aqi_with_subsets(kwargs):
    aqi, category, dominant = calculate_aqi(**kwargs)
    assert aqi >= 0
    assert category != "Unknown"
    assert dominant


def test_calculate_aqi_no_data():
    assert calculate_aqi() == (0, "Unknown", "pm25")


def test_calculate_aqi_equals_dominant_iaqi():
    aqi, category, dominant = calculate_aqi(pm25=45, pm10=1000)
    assert aqi == 500  # pm10 dominates
    assert dominant == "pm10"
    aqi2, _, dominant2 = calculate_aqi(pm25=45, pm10=40)
    assert aqi2 == int(calculate_iaqi("pm25", 45))
    assert dominant2 == "pm25"


def test_calculate_aqi_ignores_nan_values():
    aqi, category, dominant = calculate_aqi(pm25=math.nan, pm10=50)
    assert aqi == 50
    assert dominant == "pm10"


@pytest.mark.parametrize("kwargs,expected", [
    ({"pm25": 400, "pm10": 100, "o3": 10, "no2": 10, "so2": 5, "co": 0.5}, "pm25"),
    ({"pm25": 60, "pm10": 500, "o3": 10, "no2": 10, "so2": 5, "co": 0.5}, "pm10"),
    ({"pm25": 60, "pm10": 100, "o3": 800, "no2": 10, "so2": 5, "co": 0.5}, "o3"),
    ({"pm25": 60, "pm10": 100, "o3": 10, "no2": 500, "so2": 5, "co": 0.5}, "no2"),
    ({"pm25": 60, "pm10": 100, "o3": 10, "no2": 30, "so2": 1500, "co": 0.5}, "so2"),
    ({"pm25": 60, "pm10": 100, "o3": 10, "no2": 30, "so2": 10, "co": 40}, "co"),
])
def test_dominant_pollutant_detection(kwargs, expected):
    assert get_dominant_pollutant(**kwargs) == expected


def test_dominant_pollutant_all_none():
    assert get_dominant_pollutant(None, None, None, None, None, None) == "pm25"


def test_dominant_pollutant_tie_prefers_first():
    assert get_dominant_pollutant(500, 600, None, None, None, None) == "pm25"


def test_calculate_aqi_returns_int():
    aqi, _, _ = calculate_aqi(pm25=120, pm10=180)
    assert isinstance(aqi, int)


def test_roundtrip_category_consistency():
    for value in (45, 120, 250, 350, 450):
        aqi, category, _ = calculate_aqi(pm25=value)
        assert get_aqi_category(aqi)[0] == category
        assert aqi >= 0
