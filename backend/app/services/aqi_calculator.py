import math

IAQI_BREAKPOINTS = {
    "pm25": [
        (0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200),
        (91, 120, 201, 300), (121, 250, 301, 400), (251, 500, 401, 500),
    ],
    "pm10": [
        (0, 50, 0, 50), (51, 100, 51, 100), (101, 250, 101, 200),
        (251, 350, 201, 300), (351, 430, 301, 400), (431, 600, 401, 500),
    ],
    "o3": [
        (0, 50, 0, 50), (51, 100, 51, 100), (101, 168, 101, 200),
        (169, 208, 201, 300), (209, 748, 301, 400), (749, 1200, 401, 500),
    ],
    "no2": [
        (0, 40, 0, 50), (41, 80, 51, 100), (81, 180, 101, 200),
        (181, 280, 201, 300), (281, 400, 301, 400), (401, 800, 401, 500),
    ],
    "so2": [
        (0, 40, 0, 50), (41, 80, 51, 100), (81, 380, 101, 200),
        (381, 800, 201, 300), (801, 1600, 301, 400), (1601, 2100, 401, 500),
    ],
    "co": [
        (0, 1, 0, 50), (1.1, 2, 51, 100), (2.1, 10, 101, 200),
        (10.1, 17, 201, 300), (17.1, 34, 301, 400), (34.1, 50, 401, 500),
    ],
}

AQI_CATEGORIES = [
    (0, 50, "Good", 1),
    (51, 100, "Satisfactory", 2),
    (101, 200, "Moderate", 3),
    (201, 300, "Poor", 4),
    (301, 400, "Very Poor", 5),
    (401, 500, "Severe", 6),
]

def calculate_iaqi(pollutant: str, concentration: float) -> float:
    if concentration is None or math.isnan(concentration):
        return 0
    breakpoints = IAQI_BREAKPOINTS.get(pollutant)
    if not breakpoints:
        return 0
    for bp_lo, bp_hi, iaqi_lo, iaqi_hi in breakpoints:
        if bp_lo <= concentration <= bp_hi:
            return ((iaqi_hi - iaqi_lo) / (bp_hi - bp_lo)) * (concentration - bp_lo) + iaqi_lo
    return 500

def get_aqi_category(aqi: int) -> tuple[str, int]:
    for lo, hi, category, level in AQI_CATEGORIES:
        if lo <= aqi <= hi:
            return category, level
    return "Severe", 6

def get_dominant_pollutant(pm25, pm10, o3, no2, so2, co) -> str:
    iaqis = {}
    for name, val in [("pm25", pm25), ("pm10", pm10), ("o3", o3), ("no2", no2), ("so2", so2), ("co", co)]:
        if val is not None:
            iaqis[name] = calculate_iaqi(name, val)
    if not iaqis:
        return "pm25"
    return max(iaqis, key=iaqis.get)

def calculate_aqi(pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None) -> tuple[int, str, str]:
    iaqis = {}
    for name, val in [("pm25", pm25), ("pm10", pm10), ("o3", o3), ("no2", no2), ("so2", so2), ("co", co)]:
        if val is not None:
            iaqis[name] = calculate_iaqi(name, val)
    if not iaqis:
        return 0, "Unknown", "pm25"
    aqi = int(max(iaqis.values()))
    dominant = max(iaqis, key=iaqis.get)
    category, _ = get_aqi_category(aqi)
    return aqi, category, dominant
