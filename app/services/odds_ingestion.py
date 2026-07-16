"""
Загрузка котировок Betfair Exchange и запись в OddsLine.

Betfair отдаёт свои события (eventId, названия команд, marketId) — прямого
соответствия с Match.external_id из football-data.org/StatsBomb нет, поэтому
матч определяется эвристически: по времени начала (окно +-3ч от kickoff_at)
и похожести названий команд (см. _match_similarity). Это MVP-уровень;
надёжнее было бы вести отдельную таблицу маппинга betfair_event_id -> match_id,
заполняемую один раз при первом успешном сопоставлении — см. TODO ниже.

Цена (`OddsLine.price`) — лучшая доступная цена "back" (availableToBack[0]) для
каждого исхода: с точки зрения "какой коэффициент я реально могу получить,
поставив на этот исход", это прямой аналог коэффициента букмекера.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import MarketCode, MatchStatus, OddsSourceType
from app.models.match import Match
from app.models.odds import OddsLine, OddsSource
from app.services.markets import get_or_create_market
from app.services.sources import betfair

logger = logging.getLogger(__name__)

SOURCE_NAME = "Betfair Exchange"

MATCH_ODDS = "MATCH_ODDS"
OVER_UNDER_25 = "OVER_UNDER_25"
BTTS = "BOTH_TEAMS_TO_SCORE"
MARKET_TYPE_CODES = [MATCH_ODDS, OVER_UNDER_25, BTTS]

TEAM_NAME_MATCH_THRESHOLD = 0.5
KICKOFF_WINDOW = timedelta(hours=3)
BOOK_BATCH_SIZE = 40  # Betfair рекомендует не более ~40 marketId за один listMarketBook


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio()


def _split_event_name(event_name: str) -> tuple[str, str] | None:
    """Betfair называет событие 'Home Team v Away Team'."""
    for sep in (" v ", " vs "):
        if sep in event_name:
            home, away = event_name.split(sep, 1)
            return home.strip(), away.strip()
    return None


async def get_or_create_betfair_source(db: AsyncSession) -> OddsSource:
    result = await db.execute(select(OddsSource).where(OddsSource.name == SOURCE_NAME))
    source = result.scalar_one_or_none()
    if source is None:
        source = OddsSource(
            name=SOURCE_NAME, type=OddsSourceType.EXCHANGE, is_active=True, base_url="https://api.betfair.com"
        )
        db.add(source)
        await db.flush()
    return source


async def _find_matching_db_match(
    db: AsyncSession, home_name: str, away_name: str, kickoff_at: datetime
) -> Match | None:
    """
    TODO: как только появится первое успешное сопоставление для пары
    (источник, betfair event_id), стоит закэшировать его в отдельной таблице
    вместо пересчёта fuzzy-схожести на каждый синк — но для MVP это лишнее.
    """
    result = await db.execute(
        select(Match)
        .options(selectinload(Match.home_team), selectinload(Match.away_team))
        .where(
            Match.status == MatchStatus.SCHEDULED,
            Match.kickoff_at.between(kickoff_at - KICKOFF_WINDOW, kickoff_at + KICKOFF_WINDOW),
        )
    )
    candidates = result.scalars().all()
    if not candidates:
        return None

    best_match, best_score = None, 0.0
    for candidate in candidates:
        score = (
            _name_similarity(home_name, candidate.home_team.name)
            + _name_similarity(away_name, candidate.away_team.name)
        ) / 2
        if score > best_score:
            best_match, best_score = candidate, score

    if best_score >= TEAM_NAME_MATCH_THRESHOLD:
        return best_match

    logger.debug(
        "Не удалось сопоставить событие Betfair '%s vs %s' (%s) с БД (лучшее совпадение %.2f)",
        home_name, away_name, kickoff_at, best_score,
    )
    return None


@dataclass
class _RunnerPrice:
    runner_name: str
    selection_id: int
    best_back_price: float | None


def _extract_runner_prices(catalogue_entry: dict, book_by_market_id: dict[str, dict]) -> list[_RunnerPrice]:
    market_id = catalogue_entry["marketId"]
    book = book_by_market_id.get(market_id)
    if book is None:
        return []

    prices_by_selection = {}
    for runner_book in book.get("runners", []):
        backs = runner_book.get("ex", {}).get("availableToBack", [])
        prices_by_selection[runner_book["selectionId"]] = backs[0]["price"] if backs else None

    return [
        _RunnerPrice(
            runner_name=r["runnerName"],
            selection_id=r["selectionId"],
            best_back_price=prices_by_selection.get(r["selectionId"]),
        )
        for r in catalogue_entry.get("runners", [])
    ]


async def _store_match_odds(
    db: AsyncSession, match: Match, runners: list[_RunnerPrice], source: OddsSource
) -> int:
    market = await get_or_create_market(db, MarketCode.MATCH_WINNER)
    count = 0
    for runner in runners:
        if runner.best_back_price is None:
            continue

        is_draw = runner.runner_name.strip().lower() in ("the draw", "draw")
        home_score = 0.0 if is_draw else _name_similarity(runner.runner_name, match.home_team.name)
        away_score = 0.0 if is_draw else _name_similarity(runner.runner_name, match.away_team.name)

        if is_draw:
            selection = "draw"
        elif home_score >= away_score and home_score > 0.7:
            selection = "home"
        elif away_score > home_score and away_score > 0.7:
            selection = "away"
        else:
            continue

        db.add(OddsLine(match_id=match.id, market_id=market.id, source_id=source.id,
                         selection=selection, price=runner.best_back_price))
        count += 1
    return count


async def _store_total_odds(
    db: AsyncSession, match: Match, runners: list[_RunnerPrice], source: OddsSource, total_line: float = 2.5
) -> int:
    count = 0
    for runner in runners:
        if runner.best_back_price is None:
            continue
        name = runner.runner_name.strip().lower()
        if name.startswith("over"):
            market = await get_or_create_market(db, MarketCode.TOTAL_OVER)
            selection = f"over_{total_line}"
        elif name.startswith("under"):
            market = await get_or_create_market(db, MarketCode.TOTAL_UNDER)
            selection = f"under_{total_line}"
        else:
            continue
        db.add(OddsLine(match_id=match.id, market_id=market.id, source_id=source.id,
                         selection=selection, price=runner.best_back_price, line_value=total_line))
        count += 1
    return count


async def _store_btts_odds(db: AsyncSession, match: Match, runners: list[_RunnerPrice], source: OddsSource) -> int:
    market = await get_or_create_market(db, MarketCode.BTTS)
    count = 0
    for runner in runners:
        if runner.best_back_price is None:
            continue
        name = runner.runner_name.strip().lower()
        if name not in ("yes", "no"):
            continue
        db.add(OddsLine(match_id=match.id, market_id=market.id, source_id=source.id,
                         selection=name, price=runner.best_back_price))
        count += 1
    return count


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def sync_betfair_odds(
    db: AsyncSession,
    competition_ids: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, int]:
    """
    Точка входа для ежедневного цикла (07:00 "Получение коэффициентов" +
    почасовое обновление линии, см. ТЗ). Тянет MATCH_ODDS / OVER_UNDER_25 /
    BOTH_TEAMS_TO_SCORE на предстоящие матчи, сопоставляет с БД, пишет OddsLine.

    competition_ids не задан -> тянет ВСЕ футбольные события в мире в окне дат.
    Это дорого по квоте и почти всегда лишнее — предпочтительно вызывать через
    sync_all_betfair_leagues(), которая фильтрует по turniram из app/core/leagues.py.
    """
    date_from = date_from or datetime.now(timezone.utc)
    date_to = date_to or (date_from + timedelta(days=7))

    session = await betfair.login()
    source = await get_or_create_betfair_source(db)

    catalogue = await betfair.list_market_catalogue(
        session, MARKET_TYPE_CODES, date_from, date_to, competition_ids=competition_ids
    )
    if not catalogue:
        return {"events": 0, "matched": 0, "odds_lines": 0}

    market_ids = [entry["marketId"] for entry in catalogue]
    book_by_market_id: dict[str, dict] = {}
    for batch in _chunk(market_ids, BOOK_BATCH_SIZE):
        books = await betfair.list_market_book(session, batch)
        book_by_market_id.update({b["marketId"]: b for b in books})

    # Группируем рынки по событию Betfair (одно событие -> до 3 рынков: MATCH_ODDS/OU2.5/BTTS)
    entries_by_event: dict[str, list[dict]] = {}
    for entry in catalogue:
        event_id = entry["event"]["id"]
        entries_by_event.setdefault(event_id, []).append(entry)

    matched_events = 0
    odds_lines_created = 0

    for event_id, entries in entries_by_event.items():
        event = entries[0]["event"]
        names = _split_event_name(event["name"])
        if names is None:
            logger.debug("Не удалось разобрать название события Betfair: %s", event["name"])
            continue
        home_name, away_name = names
        kickoff_at = datetime.fromisoformat(event["openDate"].replace("Z", "+00:00"))

        match = await _find_matching_db_match(db, home_name, away_name, kickoff_at)
        if match is None:
            continue
        matched_events += 1

        for entry in entries:
            runners = _extract_runner_prices(entry, book_by_market_id)
            # marketTypeCode не возвращается напрямую в listMarketCatalogue — определяем рынок по marketName
            market_name = entry.get("marketName", "")
            if market_name == "Match Odds":
                odds_lines_created += await _store_match_odds(db, match, runners, source)
            elif "Over/Under 2.5" in market_name:
                odds_lines_created += await _store_total_odds(db, match, runners, source)
            elif "Both teams to Score" in market_name or "Both Teams to Score" in market_name:
                odds_lines_created += await _store_btts_odds(db, match, runners, source)

    await db.commit()
    logger.info(
        "Betfair: события=%s, сопоставлено с БД=%s, записано котировок=%s",
        len(entries_by_event), matched_events, odds_lines_created,
    )
    return {"events": len(entries_by_event), "matched": matched_events, "odds_lines": odds_lines_created}


async def sync_all_betfair_leagues(
    db: AsyncSession, date_from: datetime | None = None, date_to: datetime | None = None
) -> dict[str, dict[str, int]]:
    """
    Синкает котировки только по турнирам с заполненным betfair_competition_id
    в app/core/leagues.py. Если ни у одного турнира id не заполнен — вернёт {}
    (см. `python -m app.cli list-betfair-competitions`, чтобы их найти).
    """
    from app.core.leagues import SUPPORTED_LEAGUES

    configured = [lc for lc in SUPPORTED_LEAGUES if lc.betfair_competition_id]
    if not configured:
        logger.warning(
            "Ни у одной лиги в app/core/leagues.py не задан betfair_competition_id — "
            "запустите 'python -m app.cli list-betfair-competitions' и заполните вручную"
        )
        return {}

    results: dict[str, dict[str, int]] = {}
    for league_config in configured:
        results[league_config.name] = await sync_betfair_odds(
            db, competition_ids=[league_config.betfair_competition_id], date_from=date_from, date_to=date_to
        )
    return results
