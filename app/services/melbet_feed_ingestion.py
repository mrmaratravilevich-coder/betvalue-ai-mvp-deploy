"""Normalize and store official MELBET prematch events and odds."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, settings
from app.models.enums import MarketCode, MatchStatus, OddsSourceType
from app.models.match import Match
from app.models.odds import OddsLine, OddsSource
from app.services.markets import get_or_create_market
from app.services.match_ingestion import get_or_create_league, get_or_create_sport, get_or_create_team, upsert_match
from app.services.sources.melbet_feed import (
    MelbetFeedClient,
    messagepack_value,
    translated_name,
    unix_ticks_to_datetime,
)

logger = logging.getLogger(__name__)

SOURCE_CODE = "melbet_feed"
SOURCE_NAME = "MELBET Official Feed"
MATCH_WINDOW = timedelta(hours=3)

SPORTS: dict[int, tuple[str, str]] = {
    1: ("football", "Футбол"),
    3: ("tennis", "Теннис"),
    4: ("basketball", "Баскетбол"),
    5: ("baseball", "Бейсбол"),
    10: ("hockey", "Хоккей"),
}


@dataclass(frozen=True, slots=True)
class MelbetQuote:
    market: MarketCode
    selection: str
    price: float
    line_value: float | None = None


@dataclass(frozen=True, slots=True)
class MelbetEvent:
    event_id: str
    sport_id: int
    tournament_id: int
    tournament_name: str
    championship_name: str | None
    home_name: str
    away_name: str
    kickoff_at: datetime
    home_score: int | None
    away_score: int | None
    quotes: tuple[MelbetQuote, ...]


def _normalized(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]", "", value.casefold())


def _selection_from_stake(
    stake_type_id: int,
    stake_name: str,
    home_name: str,
    away_name: str,
    argument: float | None,
) -> tuple[MarketCode, str, float | None] | None:
    name = stake_name.casefold().strip()
    compact = _normalized(name)
    home = _normalized(home_name)
    away = _normalized(away_name)

    if stake_type_id == 1:
        if compact == home or name in {"1", "home", "team 1", "п1"}:
            return MarketCode.MATCH_WINNER, "home", None
        if compact == away or name in {"2", "away", "team 2", "п2"}:
            return MarketCode.MATCH_WINNER, "away", None
        if name in {"x", "draw", "ничья"}:
            return MarketCode.MATCH_WINNER, "draw", None
    elif stake_type_id == 2:
        if compact == home or "team 1" in name or "команда 1" in name:
            return MarketCode.HANDICAP, "home", argument
        if compact == away or "team 2" in name or "команда 2" in name:
            return MarketCode.HANDICAP, "away", argument
    elif stake_type_id == 3:
        if "over" in name or "больше" in name:
            return MarketCode.TOTAL_OVER, f"over_{argument:g}" if argument is not None else "over", argument
        if "under" in name or "меньше" in name:
            return MarketCode.TOTAL_UNDER, f"under_{argument:g}" if argument is not None else "under", argument
    elif stake_type_id == 26:
        if name in {"yes", "да"}:
            return MarketCode.BTTS, "yes", None
        if name in {"no", "нет"}:
            return MarketCode.BTTS, "no", None
    elif stake_type_id == 37:
        token = name.upper().replace(" ", "")
        if token in {"1X", "X2", "12"}:
            return MarketCode.DOUBLE_CHANCE, token.lower(), None
    return None


def normalize_prematch_event(raw: Any) -> MelbetEvent:
    home_ru = translated_name(messagepack_value(raw, 2), 1)
    away_ru = translated_name(messagepack_value(raw, 3), 1)
    home_en = translated_name(messagepack_value(raw, 2), 2) or home_ru
    away_en = translated_name(messagepack_value(raw, 3), 2) or away_ru
    quotes: list[MelbetQuote] = []
    for stake in messagepack_value(raw, 11, []) or []:
        price = messagepack_value(stake, 4)
        if price is None or float(price) <= 1:
            continue
        stake_type_id = int(messagepack_value(stake, 1))
        stake_name = translated_name(messagepack_value(stake, 3), 2)
        argument_value = messagepack_value(stake, 5)
        argument = float(argument_value) if argument_value is not None else None
        mapped = _selection_from_stake(stake_type_id, stake_name, home_en, away_en, argument)
        if mapped is None:
            continue
        market, selection, line_value = mapped
        quotes.append(MelbetQuote(market, selection, float(price), line_value))

    return MelbetEvent(
        event_id=str(messagepack_value(raw, 0)),
        sport_id=int(messagepack_value(raw, 35)),
        tournament_id=int(messagepack_value(raw, 5)),
        tournament_name=translated_name(messagepack_value(raw, 33), 1) or "MELBET",
        championship_name=translated_name(messagepack_value(raw, 34), 1) or None,
        home_name=home_ru,
        away_name=away_ru,
        kickoff_at=unix_ticks_to_datetime(int(messagepack_value(raw, 7))),
        home_score=messagepack_value(raw, 29),
        away_score=messagepack_value(raw, 30),
        quotes=tuple(quotes),
    )


async def _get_or_create_source(db: AsyncSession, base_url: str) -> OddsSource:
    result = await db.execute(select(OddsSource).where(OddsSource.name == SOURCE_NAME))
    source = result.scalar_one_or_none()
    if source is None:
        source = OddsSource(
            name=SOURCE_NAME,
            type=OddsSourceType.BOOKMAKER_OFFICIAL_API,
            is_active=True,
            base_url=base_url,
        )
        db.add(source)
        await db.flush()
    else:
        source.is_active = True
        source.base_url = base_url
    return source


async def _find_existing_match(db: AsyncSession, event: MelbetEvent) -> Match | None:
    result = await db.execute(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(
            Match.kickoff_at.between(event.kickoff_at - MATCH_WINDOW, event.kickoff_at + MATCH_WINDOW),
            Match.status.in_((MatchStatus.SCHEDULED, MatchStatus.LIVE)),
        )
    )
    best_match = None
    best_score = 0.0
    for candidate in result.scalars().all():
        direct = (
            SequenceMatcher(None, _normalized(event.home_name), _normalized(candidate.home_team.name)).ratio()
            + SequenceMatcher(None, _normalized(event.away_name), _normalized(candidate.away_team.name)).ratio()
        ) / 2
        if direct > best_score:
            best_match, best_score = candidate, direct
    return best_match if best_score >= 0.72 else None


async def _store_event(
    db: AsyncSession,
    event: MelbetEvent,
    source: OddsSource,
    status: MatchStatus,
) -> tuple[bool, int]:
    match = await _find_existing_match(db, event)
    created = match is None
    if match is None:
        sport_code, sport_name = SPORTS.get(event.sport_id, (f"sport_{event.sport_id}", "Спорт"))
        sport = await get_or_create_sport(db, sport_code, sport_name)
        league = await get_or_create_league(
            db,
            sport,
            event.tournament_name,
            event.championship_name,
            SOURCE_CODE,
            event.tournament_id,
        )
        home = await get_or_create_team(
            db, league, event.home_name, SOURCE_CODE, f"{event.sport_id}:{_normalized(event.home_name)}"
        )
        away = await get_or_create_team(
            db, league, event.away_name, SOURCE_CODE, f"{event.sport_id}:{_normalized(event.away_name)}"
        )
        match = await upsert_match(
            db,
            league,
            home,
            away,
            kickoff_at=event.kickoff_at,
            status=status,
            season=None,
            round_=None,
            home_score=event.home_score,
            away_score=event.away_score,
            source=SOURCE_CODE,
            external_id=event.event_id,
        )
    else:
        match.status = status
        if event.home_score is not None:
            match.home_score = int(event.home_score)
        if event.away_score is not None:
            match.away_score = int(event.away_score)

    lines = 0
    for quote in event.quotes:
        market = await get_or_create_market(db, quote.market)
        db.add(
            OddsLine(
                match_id=match.id,
                market_id=market.id,
                source_id=source.id,
                selection=quote.selection,
                price=quote.price,
                line_value=quote.line_value,
            )
        )
        lines += 1
    return created, lines


def _chunks(items: list[int], size: int = 10) -> list[list[int]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def sync_melbet_feed(
    db: AsyncSession,
    *,
    config: Settings = settings,
    client: MelbetFeedClient | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Load configured prematch events and their current official odds."""
    if not config.MELBET_FEED_ENABLED:
        return {"events": 0, "live_events": 0, "matches_created": 0, "odds_lines": 0}
    tournament_ids = config.melbet_feed_tournament_ids
    stake_type_ids = config.melbet_feed_stake_type_ids
    if not tournament_ids:
        raise ValueError("MELBET_FEED_TOURNAMENT_IDS is empty")

    feed = client or MelbetFeedClient(config)
    current = now or datetime.now(timezone.utc)
    source = await _get_or_create_source(db, config.MELBET_FEED_BASE_URL)
    events_count = live_events = matches_created = odds_lines = 0
    for tournament_batch in _chunks(tournament_ids):
        prematch_events = await feed.fetch_prematch_events(
            current - timedelta(hours=2),
            current + timedelta(days=config.MELBET_FEED_PREMATCH_DAYS),
            tournament_ids=tournament_batch,
            stake_type_ids=stake_type_ids,
            language_ids=config.melbet_feed_language_ids,
        )
        live_raw_events = await feed.fetch_live_events(
            tournament_ids=tournament_batch,
            stake_type_ids=stake_type_ids,
            language_ids=config.melbet_feed_language_ids,
        )
        raw_events: dict[str, tuple[Any, MatchStatus]] = {
            str(messagepack_value(raw, 0)): (raw, MatchStatus.SCHEDULED)
            for raw in prematch_events
        }
        for raw in live_raw_events:
            raw_events[str(messagepack_value(raw, 0))] = (raw, MatchStatus.LIVE)
        live_events += len(live_raw_events)
        for raw, status in raw_events.values():
            try:
                event = normalize_prematch_event(raw)
                created, stored_lines = await _store_event(db, event, source, status)
            except (TypeError, ValueError) as exc:
                logger.warning("MELBET feed: skipped malformed event: %s", exc)
                continue
            events_count += 1
            matches_created += int(created)
            odds_lines += stored_lines

    await db.commit()
    result = {
        "events": events_count,
        "live_events": live_events,
        "matches_created": matches_created,
        "odds_lines": odds_lines,
    }
    logger.info("MELBET feed sync completed: %s", result)
    return result
