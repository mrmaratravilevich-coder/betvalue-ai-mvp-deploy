"""Async client for api-tennis.com REST API."""

from datetime import date

import httpx

from app.core.config import settings


class ApiTennisError(RuntimeError):
    pass


async def _get(method: str, params: dict | None = None) -> object:
    if not settings.API_TENNIS_KEY:
        raise ApiTennisError("API_TENNIS_KEY is not configured")
    query = {"method": method, "APIkey": settings.API_TENNIS_KEY, **(params or {})}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(settings.API_TENNIS_BASE_URL, params=query)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and str(data.get("error", "0")) not in {"0", "", "None"}:
        result = data.get("result")
        detail = result[0].get("msg") if isinstance(result, list) and result and isinstance(result[0], dict) else result
        raise ApiTennisError(f"API Tennis error: {detail or data.get('error')}")
    return data


async def fetch_events() -> object:
    return await _get("get_events")


async def fetch_fixtures(date_start: date, date_stop: date | None = None) -> object:
    return await _get(
        "get_fixtures",
        {
            "date_start": date_start.isoformat(),
            "date_stop": (date_stop or date_start).isoformat(),
        },
    )
