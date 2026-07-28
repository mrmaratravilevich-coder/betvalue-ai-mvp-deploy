from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.enums import MatchStatus
from app.models.match import Match
from app.schemas.match import MatchOut

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=list[MatchOut])
async def list_matches(
    league_id: int | None = Query(default=None),
    day: date | None = Query(default=None, description="Фильтр по дате матча"),
    status: MatchStatus | None = Query(default=None),
    upcoming_only: bool = Query(default=True, description="Только текущие и будущие матчи"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Match).options(selectinload(Match.home_team), selectinload(Match.away_team))
    if league_id is not None:
        stmt = stmt.where(Match.league_id == league_id)
    if status is not None:
        stmt = stmt.where(Match.status == status)
    if upcoming_only:
        stmt = stmt.where(Match.kickoff_at >= datetime.now(timezone.utc))
    if day is not None:
        stmt = stmt.where(func.date(Match.kickoff_at) == day)

    stmt = stmt.order_by(Match.kickoff_at).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
