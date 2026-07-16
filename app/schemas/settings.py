from pydantic import BaseModel, ConfigDict, Field


class UserSettingsIn(BaseModel):
    min_ev_threshold: float = Field(default=0.05, ge=0, le=1)
    max_odds: float = Field(default=6.0, gt=1)
    kelly_fraction_pct: float = Field(default=25.0, gt=0, le=100)
    min_historical_matches: int = Field(default=1000, ge=0)
    telegram_chat_id: str | None = None


class UserSettingsOut(UserSettingsIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
