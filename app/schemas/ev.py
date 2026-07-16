from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BetStatus


class EVBetOut(BaseModel):
    """Соответствует блоку 'Карточка матча' в ТЗ."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    match_id: int
    league_name: str
    home_team: str
    away_team: str
    kickoff_at: datetime

    market: str
    selection: str

    model_probability: float          # вероятность модели
    market_probability: float         # имплицитная вероятность рынка (1 / коэфф.)
    odds: float

    ev: float                         # напр. 0.281
    kelly_fraction: float
    recommended_stake: float | None
    confidence: float | None
    reasoning: str | None             # AI Explain текст

    status: BetStatus
