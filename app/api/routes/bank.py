from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.enums import BetStatus
from app.models.prediction import EVBet
from app.models.user import BankTransaction, User
from app.schemas.bank import BankSummaryOut

router = APIRouter(prefix="/bank", tags=["bank"])


@router.get("", response_model=BankSummaryOut)
async def get_bank_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Текущий баланс — последняя транзакция банка
    last_tx = await db.execute(
        select(BankTransaction)
        .where(BankTransaction.user_id == current_user.id)
        .order_by(BankTransaction.created_at.desc())
        .limit(1)
    )
    last = last_tx.scalar_one_or_none()
    current_balance = float(last.balance_after) if last else 0.0

    # Первая транзакция — начальный банк
    first_tx = await db.execute(
        select(BankTransaction)
        .where(BankTransaction.user_id == current_user.id)
        .order_by(BankTransaction.created_at.asc())
        .limit(1)
    )
    first = first_tx.scalar_one_or_none()
    initial_balance = float(first.amount) if first else 0.0

    settled = await db.execute(
        select(EVBet).where(
            EVBet.user_id == current_user.id,
            EVBet.status.in_([BetStatus.WON, BetStatus.LOST]),
        )
    )
    settled_bets = settled.scalars().all()
    total_bets = len(settled_bets)
    won = sum(1 for b in settled_bets if b.status == BetStatus.WON)
    total_staked = sum(float(b.recommended_stake or 0) for b in settled_bets)

    win_rate = (won / total_bets * 100) if total_bets else 0.0
    profit = current_balance - initial_balance
    roi = (profit / initial_balance * 100) if initial_balance else 0.0
    yield_pct = (profit / total_staked * 100) if total_staked else 0.0

    return BankSummaryOut(
        current_balance=current_balance,
        initial_balance=initial_balance,
        roi=roi,
        yield_pct=yield_pct,
        win_rate=win_rate,
        total_bets=total_bets,
    )
