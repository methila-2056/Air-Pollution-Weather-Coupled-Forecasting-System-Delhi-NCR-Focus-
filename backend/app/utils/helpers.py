import math
import pathlib
from datetime import datetime

_MODELS_DIR = "models"


def repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """Walk up from ``start`` to the repository root that holds ``models/pm25``.

    The backend may run from a bare-metal checkout (backend/app/services -> repo)
    or from a container where the source sits at /app/app/services and the
    models volume mounts at /app/models. Walking up until a parent containing
    ``models/pm25`` is found keeps the model directory resolvable in both
    layouts. ``pyproject.toml`` is used as a fallback marker (it is absent in
    the container image, where only the mounted ML ``models/`` directory is
    guaranteed to travel).
    """
    current = (start or pathlib.Path(__file__).resolve().parent).resolve()
    for parent in [current, *current.parents]:
        if (parent / _MODELS_DIR / "pm25").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return current.parents[min(2, len(current.parents) - 1)]


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
