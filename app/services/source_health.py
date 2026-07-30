"""Read-only health checks for the MVP sports-data providers."""

import asyncio

from app.services.sources import api_basketball, api_hockey, football_data


async def check_mvp_sources() -> dict:
    football_result, hockey_result, basketball_result = await asyncio.gather(
        football_data.fetch_competition_matches("PL"),
        api_hockey.fetch_status(),
        api_basketball.fetch_status(),
        return_exceptions=True,
    )

    football = (
        {"ok": False, "error": type(football_result).__name__}
        if isinstance(football_result, Exception)
        else {"ok": True, "competition": "PL", "matches": len(football_result)}
    )
    hockey = (
        {"ok": False, "error": type(hockey_result).__name__}
        if isinstance(hockey_result, Exception)
        else {"ok": True, "provider": "API-SPORTS"}
    )
    basketball = (
        {"ok": False, "error": type(basketball_result).__name__}
        if isinstance(basketball_result, Exception)
        else {"ok": True, "provider": "API-SPORTS"}
    )
    return {"football": football, "hockey": hockey, "basketball": basketball}
