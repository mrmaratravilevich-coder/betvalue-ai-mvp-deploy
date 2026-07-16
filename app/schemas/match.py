from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchStatus


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    elo_rating: float


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    league_id: int
    home_team: TeamOut
    away_team: TeamOut
    kickoff_at: datetime
    status: MatchStatus
    home_score: int | None = None
    away_score: int | None = None
