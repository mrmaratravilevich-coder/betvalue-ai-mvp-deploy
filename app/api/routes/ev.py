from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.enums import BetStatus
from app.models.match import Match
from app.models.odds import Market, OddsLine
from app.models.prediction import EVBet, Prediction
from app.schemas.ev import EVBetOut

router = APIRouter(prefix="/ev", tags=["ev"])


@router.get("", response_model=list[EVBetOut])
async def list_ev_bets(
    min_ev: float = Query(default=settings.MIN_EV_THRESHOLD, ge=0),
    max_odds: float = Query(default=settings.MAX_ODDS, gt=1),
    league_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Возвращает только ставки, прошедшие фильтры (EV >= min_ev, коэфф. <= max_odds).
    Сама фильтрация "неизвестный состав / подозрительное движение линии / высокая
    неопределённость" выполняется на этапе формирования EVBet сервисом ML-пайплайна
    (см. app/services/ev_engine.py) — сюда попадают уже отфильтрованные записи.
    """
    stmt = (
        select(EVBet)
        .join(EVBet.prediction)
        .join(Prediction.match)
        .join(EVBet.odds_line)
        .options(
            selectinload(EVBet.prediction).selectinload(Prediction.match).selectinload(Match.home_team),
            selectinload(EVBet.prediction).selectinload(Prediction.match).selectinload(Match.away_team),
            selectinload(EVBet.prediction).selectinload(Prediction.match).selectinload(Match.league),
            selectinload(EVBet.prediction).selectinload(Prediction.market),
            selectinload(EVBet.odds_line).selectinload(OddsLine.market),
        )
        .where(EVBet.status == BetStatus.PENDING)
        .where(EVBet.ev >= min_ev)
        .where(EVBet.odds_line.has(OddsLine.price <= max_odds))
    )
    if league_id is not None:
        stmt = stmt.where(Prediction.match.has(Match.league_id == league_id))

    stmt = stmt.order_by(EVBet.ev.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    ev_bets = result.scalars().all()

    return [
        EVBetOut(
            id=b.id,
            match_id=b.prediction.match_id,
            league_name=b.prediction.match.league.name if b.prediction.match.league else "",
            home_team=b.prediction.match.home_team.name,
            away_team=b.prediction.match.away_team.name,
            kickoff_at=b.prediction.match.kickoff_at,
            market=b.odds_line.market.name,
            selection=b.odds_line.selection,
            model_probability=float(b.prediction.model_probability),
            market_probability=b.odds_line.implied_probability,
            odds=float(b.odds_line.price),
            ev=float(b.ev),
            kelly_fraction=float(b.kelly_fraction),
            recommended_stake=float(b.recommended_stake) if b.recommended_stake is not None else None,
            confidence=float(b.confidence) if b.confidence is not None else None,
            reasoning=b.reasoning,
            status=b.status,
        )
        for b in ev_bets
    ]
