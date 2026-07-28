"""Fetch and normalize upcoming fixtures for lightweight bot output."""

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.services.sources import api_hockey, football_data

FOOTBALL_LOOKAHEAD_DAYS = 30
HOCKEY_LOOKAHEAD_DAYS = 3
FIXTURES_PER_SPORT = 5
CACHE_TTL_SECONDS = 300
MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")


@dataclass(frozen=True)
class UpcomingFixture:
    sport: str
    competition: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    source: str


@dataclass(frozen=True)
class UpcomingMatches:
    football: tuple[UpcomingFixture, ...]
    hockey: tuple[UpcomingFixture, ...]
    errors: dict[str, str]


_cache: tuple[float, UpcomingMatches] | None = None
_cache_lock = asyncio.Lock()


def _moscow_today() -> date:
    return datetime.now(MOSCOW_TZ).date()


def _utc_datetime(raw: str | int) -> datetime:
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


async def _fetch_football(today: date) -> tuple[UpcomingFixture, ...]:
    raw_matches = await football_data.fetch_competition_matches(
        "PL",
        date_from=today,
        date_to=today + timedelta(days=FOOTBALL_LOOKAHEAD_DAYS),
        status="SCHEDULED",
    )
    fixtures: list[UpcomingFixture] = []
    for raw in raw_matches:
        try:
            fixtures.append(
                UpcomingFixture(
                    sport="football",
                    competition=(raw.get("competition") or {}).get("name") or "Premier League",
                    home_team=(raw.get("homeTeam") or {})["name"],
                    away_team=(raw.get("awayTeam") or {})["name"],
                    kickoff_at=_utc_datetime(raw["utcDate"]),
                    source="football-data.org",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(sorted(fixtures, key=lambda item: item.kickoff_at)[:FIXTURES_PER_SPORT])


async def _fetch_hockey(today: date) -> tuple[UpcomingFixture, ...]:
    days = [today + timedelta(days=offset) for offset in range(HOCKEY_LOOKAHEAD_DAYS + 1)]
    responses = await asyncio.gather(
        *(api_hockey.fetch_games(day) for day in days),
        return_exceptions=True,
    )
    games: list[dict] = []
    first_error: Exception | None = None
    for response in responses:
        if isinstance(response, Exception):
            first_error = first_error or response
        else:
            games.extend(response)
    if not games and first_error:
        raise first_error

    now_utc = datetime.now(timezone.utc)
    fixtures: list[UpcomingFixture] = []
    for raw in games:
        try:
            status = raw.get("status") or {}
            short_status = status.get("short") if isinstance(status, dict) else str(status)
            if short_status not in {"NS", "TBD"}:
                continue
            teams = raw.get("teams") or {}
            kickoff_raw = raw.get("timestamp") if raw.get("timestamp") is not None else raw["date"]
            kickoff_at = _utc_datetime(kickoff_raw)
            if kickoff_at < now_utc:
                continue
            fixtures.append(
                UpcomingFixture(
                    sport="hockey",
                    competition=(raw.get("league") or {}).get("name") or "Hockey",
                    home_team=(teams.get("home") or {})["name"],
                    away_team=(teams.get("away") or {})["name"],
                    kickoff_at=kickoff_at,
                    source="API-SPORTS Hockey",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(sorted(fixtures, key=lambda item: item.kickoff_at)[:FIXTURES_PER_SPORT])


async def get_upcoming_matches(*, force_refresh: bool = False) -> UpcomingMatches:
    """Return cached upcoming football and hockey fixtures."""
    global _cache

    now = time.monotonic()
    if not force_refresh and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    async with _cache_lock:
        now = time.monotonic()
        if not force_refresh and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]

        football_result, hockey_result = await asyncio.gather(
            _fetch_football(_moscow_today()),
            _fetch_hockey(_moscow_today()),
            return_exceptions=True,
        )
        errors: dict[str, str] = {}
        if isinstance(football_result, Exception):
            errors["football"] = type(football_result).__name__
            football_result = ()
        if isinstance(hockey_result, Exception):
            errors["hockey"] = type(hockey_result).__name__
            hockey_result = ()

        result = UpcomingMatches(
            football=football_result,
            hockey=hockey_result,
            errors=errors,
        )
        _cache = (time.monotonic(), result)
        return result
