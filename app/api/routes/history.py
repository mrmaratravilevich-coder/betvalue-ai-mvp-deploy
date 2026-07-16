from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.enums import BetStatus
from app.models.match import Match
from app.models.prediction import EVBet, Prediction
from app.models.user import BankTransaction, User
from app.schemas.bank import HistoryEntryOut

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryEntryOut])
async def get_history(
    status: BetStatus | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(EVBet)
        .where(EVBet.user_id == current_user.id)
        .options(
            selectinload(EVBet.prediction)
            .selectinload(Prediction.match)
            .selectinload(Match.home_team),
            selectinload(EVBet.prediction)
            .selectinload(Prediction.match)
            .selectinload(Match.away_team),
            selectinload(EVBet.odds_line),
        )
        .order_by(EVBet.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(EVBet.status == status)

    result = await db.execute(stmt)
    ev_bets = result.scalars().all()

    entries = []
    for b in ev_bets:
        settle_tx = await db.execute(
            select(BankTransaction)
            .where(BankTransaction.ev_bet_id == b.id)
            .order_by(BankTransaction.created_at.desc())
            .limit(1)
        )
        tx = settle_tx.scalar_one_or_none()
        match = b.prediction.match
        entries.append(
            HistoryEntryOut(
                ev_bet_id=b.id,
                match_label=f"{match.home_team.name} — {match.away_team.name}" if match else "",
                selection=b.odds_line.selection,
                odds=float(b.odds_line.price),
                ev=float(b.ev),
                status=b.status,
                stake=float(b.recommended_stake) if b.recommended_stake is not None else None,
                settled_at=tx.created_at if tx else None,
                bank_after=float(tx.balance_after) if tx else None,
            )
        )
    return entries
