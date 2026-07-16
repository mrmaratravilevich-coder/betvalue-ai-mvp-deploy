from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BankTxType, BetStatus


class HistoryEntryOut(BaseModel):
    """Соответствует блоку 'История' в ТЗ: ставка / коэффициент / EV / результат / банк / ROI."""

    model_config = ConfigDict(from_attributes=True)

    ev_bet_id: int
    match_label: str          # "Арсенал — Брайтон"
    selection: str
    odds: float
    ev: float
    status: BetStatus
    stake: float | None
    settled_at: datetime | None
    bank_after: float | None


class BankTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: BankTxType
    amount: float
    balance_after: float
    created_at: datetime


class BankSummaryOut(BaseModel):
    current_balance: float
    initial_balance: float
    roi: float
    yield_pct: float
    win_rate: float
    total_bets: int
