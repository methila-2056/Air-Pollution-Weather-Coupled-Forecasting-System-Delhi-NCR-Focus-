import math
from datetime import datetime


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def wind_components(speed: float, direction_deg: float) -> tuple[float, float]:
    direction_rad = math.radians(direction_deg)
    u = -speed * math.sin(direction_rad)
    v = -speed * math.cos(direction_rad)
    return u, v

def is_winter(dt: datetime) -> bool:
    return dt.month in [10, 11, 12, 1, 2]

def get_season(dt: datetime) -> str:
    month = dt.month
    if month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "monsoon"
    elif month in [9, 10]:
        return "post_monsoon"
    else:
        return "winter"
