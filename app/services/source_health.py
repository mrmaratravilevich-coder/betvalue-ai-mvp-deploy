"""Read-only health checks for the MVP sports-data providers."""

import asyncio

from app.services.sources import api_hockey, football_data


async def check_mvp_sources() -> dict:
    football_result, hockey_result = await asyncio.gather(
        football_data.fetch_competition_matches("PL"),
        api_hockey.fetch_status(),
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
    return {"football": football, "hockey": hockey}

