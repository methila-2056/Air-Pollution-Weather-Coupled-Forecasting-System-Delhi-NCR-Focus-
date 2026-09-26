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
    # Cold-start cache pre-warm (Render free tier). When enabled, a background
    # task populates the TTL cache with the control room's heavy read-only
    # payloads right after startup, so the first dashboard load after a ~76 s
    # cold wake is served from cache instead of serialising ~12 s aggregations on
    # 0.5 CPU.
    #
    # Tri-state on purpose. `None` means "follow the default for this
    # environment" (on in production, off everywhere else), and an explicit
    # true/false always wins. It used to be a plain `bool = False`, which meant
    # the feature was silently off in production: Render does not push newly
    # added `render.yaml` env vars to an already-created service, so the sweep
    # never ran on the live deployment and `/api/system` reported
    # `{"enabled": false}` for the whole life of the release. A cold-start fix
    # that quietly depends on a manual dashboard toggle is not a fix.
    control_room_prewarm: bool | None = None
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

    @property
    def prewarm_enabled(self) -> bool:
        """Whether the cold-start cache sweep should run.

        An explicit ``CONTROL_ROOM_PREWARM`` always wins. Unset, the sweep
        follows the environment: production is exactly where a 76 s cold wake
        makes it worth ~75 s of off-request-path CPU, and local dev / pytest /
        CI are exactly where nobody wants it. The sweep is best-effort,
        cancellable and never blocks readiness, so the production default is
        safe; ``CONTROL_ROOM_PREWARM=false`` turns it off if a deployment would
        rather not pay for it.
        """
        if self.control_room_prewarm is not None:
            return self.control_room_prewarm
        return self.environment.strip().lower() == "production"

@lru_cache
def get_settings() -> Settings:
    return Settings()
