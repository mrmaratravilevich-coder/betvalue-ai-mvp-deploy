"""Async client for API-SPORTS Basketball v1."""

from datetime import date

import httpx

from app.core.config import settings


class ApiBasketballError(RuntimeError):
    pass


async def _get(endpoint: str, params: dict | None = None) -> dict:
    if not settings.API_SPORTS_KEY:
        raise ApiBasketballError("API_SPORTS_KEY is not configured")
    url = f"{settings.API_SPORTS_BASKETBALL_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            params=params or {},
            headers={"x-apisports-key": settings.API_SPORTS_KEY},
        )
    response.raise_for_status()
    data = response.json()
    errors = data.get("errors")
    if errors:
        raise ApiBasketballError(f"API-SPORTS Basketball error: {errors}")
    return data


async def fetch_status() -> dict:
    return await _get("status")


async def fetch_games(game_date: date) -> list[dict]:
    data = await _get("games", {"date": game_date.isoformat()})
    return data.get("response", [])
