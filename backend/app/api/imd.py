"""IMD official weather API endpoint (WS-3, SIH26082 R9).

`GET /api/imd/forecast` surfaces **genuine** IMD 7-day city forecasts from
api.imd.gov.in when credentials are configured and authorised; otherwise it
returns ``available: false`` with the honest reasons (never fabricated).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas.schemas import ImdForecastDay, ImdForecastResponse
from ..services import imd_weather as imd

router = APIRouter()


@router.get("/imd/forecast", response_model=ImdForecastResponse)
def imd_forecast(
    station_id: Annotated[
        str | None, Query(description="IMD station id, e.g. 42182 (Delhi/Safdarjung)")
    ] = None,
) -> ImdForecastResponse:
    try:
        result = imd.fetch_city_forecast(station_id)
    except imd.IMDApiUnavailable as exc:
        return ImdForecastResponse(
            available=False,
            reasons=imd.imd_reasons() or [str(exc)],
        )
    return ImdForecastResponse(
        available=True,
        station_id=result["station_id"],
        station_name=result["station_name"],
        fetched_at=result["fetched_at"],
        source=imd.IMD_SOURCE,
        days=[ImdForecastDay(**d) for d in result["days"]],
    )
