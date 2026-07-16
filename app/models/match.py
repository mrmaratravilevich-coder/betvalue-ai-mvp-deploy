from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MatchStatus


class Match(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_match_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))

    season: Mapped[str | None] = mapped_column(String(20), nullable=True)
    round: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)

    home_score: Mapped[int | None] = mapped_column(nullable=True)
    away_score: Mapped[int | None] = mapped_column(nullable=True)
    xg_home: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    xg_away: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Откуда пришёл матч: "football_data" | "statsbomb" | ...
    source: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(80))

    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])
    league: Mapped["League"] = relationship()
    stats: Mapped[list["MatchTeamStat"]] = relationship(back_populates="match")
    odds_lines: Mapped[list["OddsLine"]] = relationship(back_populates="match")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")


class MatchTeamStat(Base, TimestampMixin):
    """Статистика одной команды в конкретном матче — источник признаков для модели."""

    __tablename__ = "match_team_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    is_home: Mapped[bool] = mapped_column(default=True)

    shots: Mapped[int | None] = mapped_column(nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(nullable=True)
    possession_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    corners: Mapped[int | None] = mapped_column(nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(nullable=True)
    red_cards: Mapped[int | None] = mapped_column(nullable=True)
    xg: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    xga: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    match: Mapped["Match"] = relationship(back_populates="stats")
    team: Mapped["Team"] = relationship()
