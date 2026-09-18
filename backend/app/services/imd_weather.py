"""Gated adapter for the official India Meteorological Department weather API (WS-3).

``api.imd.gov.in`` (the MoES/IMD API gateway) exposes city weather forecasts,
station-wise nowcasts, district/subdivision rainfall forecasts and bulletins.
IMD requires registration and **API-key / IP-whitelisting**, so without
credentials the gateway answers ``401 Unauthorized`` — verified live.

Honesty contract (same as HYSPLIT / WRF-Chem / ERA5):

- ``imd_reasons()`` reports exactly what is missing (no key configured, 401,
  network failure, malformed payload). Nothing synthetic is ever produced.
- ``fetch_city_forecast()`` returns a parsed view of the **real** IMD JSON or
  raises ``IMDApiUnavailable``; the callers keep using Open-Meteo otherwise.
- Response parsing is defensive: field names follow the public API reference
  (``Todays_Forecast_Max_Temp`` / ``Day_2_Max_Temp`` …), unknown keys are
  simply not exposed.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

import requests

from ..config import get_settings

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 15
STATION_DEFAULTS = {
    # Delhi/Safdarjung is the anchor IMD city for the whole NCR domain; the
    # 17 curated monitors sit within ~30 km of it, so they share this bulletin.
    "42182": ("Delhi/Safdarjung", 28.5845, 77.2375),
}
IMD_SOURCE = "IMD city forecast (api.imd.gov.in)"


class IMDApiUnavailable(RuntimeError):
    """Raised when a genuine IMD response could not be obtained."""


def _build_url(settings: Any) -> str:
    return f"{settings.imd_api_base.rstrip('/')}/cityforecast"


def _auth_headers(settings: Any) -> dict[str, str]:
    headers = {"User-Agent": "AeroCast-NCR/1.7 (SIH26082)"}
    if settings.imd_api_key:
        # The gateway's accepted header name is not officially documented; send
        # both common spellings — harmless if one is ignored.
        headers["X-API-KEY"] = settings.imd_api_key
        headers["apikey"] = settings.imd_api_key
    return headers


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_payload(raw: Any, station_id: str, station_name: str) -> list[dict[str, Any]]:
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raise IMDApiUnavailable(f"IMD returned an unexpected payload of type {type(raw).__name__}")

    rows: list[dict[str, Any]] = []
    for k in range(1, 8):
        if k == 1:
            prefix = next(
                (p for p in ("Todays_Forecast", "Today_Forecast")
                 if f"{p}_Max_Temp" in raw),
                None,
            )
            if prefix is None:
                break  # day-1 keys absent → treat as malformed
            max_c = _to_float(raw.get(f"{prefix}_Max_Temp"))
            min_c = _to_float(raw.get(f"{prefix}_Min_temp"))
            cond = raw.get(prefix, "") or ""  # API reference: "Todays_Forecast"
            date_key = next(
                (d for d in ("Today_Date", "Todays_Forecast_Date", "Date", "Today")
                 if d in raw),
                None,
            )
        else:
            max_c = _to_float(raw.get(f"Day_{k}_Max_Temp"))
            min_c = _to_float(raw.get(f"Day_{k}_Min_temp"))
            cond = raw.get(f"Day_{k}_Forecast", "") or ""
            date_key = raw.get(f"Day_{k}_Date")

        rows.append({
            "day": k,
            "date": date_key,
            "max_temp_c": max_c,
            "min_temp_c": min_c,
            "condition": str(cond).strip(),
            "station_id": station_id,
            "station_name": station_name,
        })
    if not rows:
        raise IMDApiUnavailable("IMD payload had no parseable forecast fields")
    return rows


def fetch_city_forecast(
    station_id: str | None = None,
    *,
    settings: Any | None = None,
    timeout: int = HTTP_TIMEOUT,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch the genuine 7-day city forecast from api.imd.gov.in.

    Returns ``{station_id, station_name, fetched_at, days: [...]}`` or raises
    :class:`IMDApiUnavailable` (never fabricates).
    """
    settings = settings or get_settings()
    station_id = station_id or settings.imd_station_id
    station_name = STATION_DEFAULTS.get(station_id, (station_id,))[0]

    try:
        if session is not None:
            resp = session.get(
                _build_url(settings), params={"id": station_id},
                headers=_auth_headers(settings), timeout=timeout,
            )
        else:
            resp = requests.get(
                _build_url(settings), params={"id": station_id},
                headers=_auth_headers(settings), timeout=timeout,
            )
    except requests.RequestException as exc:
        raise IMDApiUnavailable(f"api.imd.gov.in unreachable: {exc}")  # noqa: B904

    if resp.status_code == 401:
        raise IMDApiUnavailable(
            "api.imd.gov.in returned 401 Unauthorized — set IMD_API_KEY and/or "
            "get your IP whitelisted on the IMD API platform"
        )
    if resp.status_code != 200:
        raise IMDApiUnavailable(f"api.imd.gov.in returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError:
        raise IMDApiUnavailable("api.imd.gov.in returned non-JSON content")  # noqa: B904

    days = _parse_payload(payload, station_id, station_name)
    return {
        "station_id": station_id,
        "station_name": station_name,
        "fetched_at": _dt.datetime.now(tz=_dt.UTC).isoformat(),
        "days": days,
    }


def imd_reasons(settings: Any | None = None) -> list[str]:
    """Explain why a genuine IMD forecast is currently unavailable."""
    settings = settings or get_settings()
    reasons: list[str] = []
    if not settings.imd_api_key:
        reasons.append(
            "IMD_API_KEY is not configured (register at api.imd.gov.in and get "
            "your IP whitelisted)"
        )
    try:
        fetch_city_forecast(settings=settings, timeout=HTTP_TIMEOUT)
    except IMDApiUnavailable as exc:
        reasons.append(str(exc))
    return reasons


def imd_forecast_dataframe(
    result: dict[str, Any] | None = None,
    *,
    settings: Any | None = None,
) -> tuple[Any, list[str]]:
    """Convenience: (DataFrame with ``imd_*`` columns | empty, reasons).

    Real data only — an absent/failed fetch returns an empty DataFrame plus the
    honest reasons list, mirroring the ERA5 reader contract.
    """
    import pandas as pd

    reasons: list[str] = []
    if result is None:
        try:
            result = fetch_city_forecast(settings=settings)
        except IMDApiUnavailable as exc:
            reasons = [str(exc)]
            return pd.DataFrame(), reasons
    rows = []
    for d in result["days"]:
        rows.append({
            "time": d["date"] or pd.NaT,
            "station": result["station_name"],
            "imd_max_temp_c": d["max_temp_c"],
            "imd_min_temp_c": d["min_temp_c"],
            "imd_condition": d["condition"],
            "imd_source": IMD_SOURCE,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        reasons.append("IMD forecast produced no rows")
    return df, reasons
