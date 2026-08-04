from collections import OrderedDict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.enums import MatchStatus
from app.models.match import Match
from app.models.odds import OddsLine, OddsSource
from app.models.team import League
from app.services.name_localization import localize_name

router = APIRouter(prefix="/line", tags=["line"])


@router.get("")
async def public_line(
    limit: int = Query(default=40, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return the latest official-feed prices grouped by current match."""
    stmt = (
        select(OddsLine)
        .join(OddsLine.source)
        .join(OddsLine.match)
        .options(
            selectinload(OddsLine.market),
            selectinload(OddsLine.source),
            selectinload(OddsLine.match).selectinload(Match.home_team),
            selectinload(OddsLine.match).selectinload(Match.away_team),
            selectinload(OddsLine.match).selectinload(Match.league).selectinload(League.sport),
        )
        .where(
            OddsSource.name == "MELBET Official Feed",
            or_(
                Match.status == MatchStatus.LIVE,
                Match.kickoff_at >= datetime.now(timezone.utc),
            ),
        )
        .order_by(OddsLine.created_at.desc())
        .limit(limit * 20)
    )
    lines = (await db.execute(stmt)).scalars().all()

    matches: OrderedDict[int, dict] = OrderedDict()
    seen_quotes: set[tuple[int, int, str, float | None]] = set()
    for line in lines:
        match = line.match
        line_value = float(line.line_value) if line.line_value is not None else None
        quote_key = (match.id, line.market_id, line.selection, line_value)
        if quote_key in seen_quotes:
            continue
        seen_quotes.add(quote_key)

        item = matches.setdefault(
            match.id,
            {
                "match_id": match.id,
                "sport": localize_name(match.league.sport.name),
                "league": localize_name(match.league.name),
                "home_team": localize_name(match.home_team.name),
                "away_team": localize_name(match.away_team.name),
                "kickoff_at": match.kickoff_at,
                "status": match.status.value,
                "updated_at": line.created_at,
                "quotes": [],
            },
        )
        item["quotes"].append(
            {
                "market": line.market.code.value,
                "market_name": line.market.name,
                "selection": line.selection,
                "price": float(line.price),
                "line_value": line_value,
            }
        )
        if len(matches) >= limit:
            break

    return list(matches.values())
