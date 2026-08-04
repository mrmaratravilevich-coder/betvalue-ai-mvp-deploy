"""Read-only health checks for the MVP sports-data providers."""

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.services.sources import api_basketball, api_hockey, football_data
from app.services.sources.melbet_feed import MelbetFeedClient


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
    melbet: dict = {"ok": False, "configured": False}
    if settings.MELBET_FEED_ENABLED:
        try:
            now = datetime.now(timezone.utc)
            sports = await MelbetFeedClient().fetch_sports(now, now + timedelta(days=1))
            melbet = {"ok": True, "configured": True, "sports": len(sports)}
        except Exception as exc:  # noqa: BLE001 - health endpoint must stay available
            melbet = {"ok": False, "configured": True, "error": type(exc).__name__}
    return {
        "football": football,
        "hockey": hockey,
        "basketball": basketball,
        "melbet_feed": melbet,
    }
