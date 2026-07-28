from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

from app.models.enums import MatchStatus
from app.services.name_localization import localize_name


class SportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str

    @field_serializer("name")
    def serialize_name(self, value: str) -> str:
        return localize_name(value)


class LeagueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str | None
    sport: SportOut

    @computed_field
    @property
    def original_name(self) -> str:
        return self.name

    @field_serializer("name")
    def serialize_name(self, value: str) -> str:
        return localize_name(value)


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    elo_rating: float

    @computed_field
    @property
    def original_name(self) -> str:
        return self.name

    @field_serializer("name")
    def serialize_name(self, value: str) -> str:
        return localize_name(value)


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    league_id: int
    league: LeagueOut
    home_team: TeamOut
    away_team: TeamOut
    kickoff_at: datetime
    status: MatchStatus
    home_score: int | None = None
    away_score: int | None = None
