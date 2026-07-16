from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.stats import StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Заглушка структуры аналитики (ROI/Yield/CLV/Drawdown/Sharpe/EV-распределение/
    heatmap по турнирам). Реальные расчёты переезжают в app/services/analytics.py
    вместе с подключением исторических коэффициентов — сейчас источника
    коэффициентов нет, поэтому CLV и Sharpe считать не из чего.
    """
    return StatsOut()
