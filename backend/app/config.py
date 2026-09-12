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
    # data.gov.in / CPCB "Real time Air Quality Index from various locations"
    data_gov_api_key: str = ""
    data_gov_api_url: str = "https://api.data.gov.in"
    data_gov_resource_id: str = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
    data_gov_ncr_cities: str = "Delhi,Gurugram,Noida,Ghaziabad,Faridabad"
    data_gov_timeout: int = 30

    model_config = {"env_file": _ENV_FILE}

@lru_cache
def get_settings() -> Settings:
    return Settings()
