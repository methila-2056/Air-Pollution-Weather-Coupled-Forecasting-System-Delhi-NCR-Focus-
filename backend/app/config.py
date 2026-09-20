import pathlib
from functools import lru_cache

from pydantic_settings import BaseSettings

_ENV_CANDIDATES = [
    pathlib.Path(__file__).resolve().parents[2] / ".env",
    pathlib.Path(__file__).resolve().parents[1] / ".env",
    pathlib.Path.cwd() / ".env",
]
_ENV_FILE = next((str(p) for p in _ENV_CANDIDATES if p.exists()), ".env")

class Settings(BaseSettings):
    database_url: str = "sqlite:///./aerocast_ncr.db"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    environment: str = "development"
    log_level: str = "INFO"
    nasa_firms_map_key: str = ""
    live_refresh_enabled: bool = False
    live_refresh_interval_hours: int = 3
    # Optional demo self-hydration: when true, the app loads the bundled coupled
    # dataset + model metrics + alerts and re-stamps recent observations into the
    # last 24h whenever pollution or weather has no reading in that window. This
    # makes a brand-new or stale database render a live-looking demo with no
    # manual steps (see backend/app/services/demo_hydration.py).
    demo_hydrate_empty_db: bool = False
    # Public URL of the deployed frontend (Vercel). When set, `GET /` on the
    # API redirects the browser there instead of answering a bare 404.
    frontend_url: str = ""
    # data.gov.in / CPCB "Real time Air Quality Index from various locations"
    data_gov_api_key: str = ""
    data_gov_api_url: str = "https://api.data.gov.in"
    data_gov_resource_id: str = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
    data_gov_ncr_cities: str = "Delhi,Gurugram,Noida,Ghaziabad,Faridabad"
    data_gov_timeout: int = 30

    # --- Chemical transport model (CTM) engines (SIH26082 R6) ---
    # Physical copy of NOAA HYSPLIT (e.g. C:\hysplit4). When set and a real
    # `exec/hycs_std(.exe)` plus GDAS/EDAS met files exist, dispersion runs use
    # genuine HYSPLIT output; otherwise the analytic surrogate stays active.
    hysplit_home: str = ""
    hysplit_met_dir: str = ""
    # Directory holding genuine WRF-Chem `wrfout_d01_*.nc` output from an
    # external run to be absorbed as the CTM surface (never fabricated).
    wrf_output_dir: str = ""

    # --- IMD official weather API (SIH26082 R9) ---
    # api.imd.gov.in requires registration + key/IP whitelisting (returns 401
    # otherwise). When set, `/api/imd/forecast` fetches *real* IMD outputs;
    # otherwise it reports honest reasons and the Open-Meteo path stays.
    imd_api_key: str = ""
    # Delhi/Safdarjung (the anchor IMD city for the NCR domain).
    imd_station_id: str = "42182"
    imd_api_base: str = "https://api.imd.gov.in/api/v1"

    # --- Authentication (SIH26082 UI login layer) ---
    secret_key: str = "aerocast-dev-secret-change-me-in-production"
    access_token_expire_minutes: int = 480  # 8 hours — one operational shift
    # Demo account seeded at startup; override via DEMO_USER_* env vars.
    demo_user_email: str = "analyst@aerocast.in"
    demo_user_name: str = "Demo Analyst"
    demo_user_role: str = "Analyst"
    demo_user_password: str = "AeroCast@2026"

    model_config = {"env_file": _ENV_FILE}

@lru_cache
def get_settings() -> Settings:
    return Settings()
