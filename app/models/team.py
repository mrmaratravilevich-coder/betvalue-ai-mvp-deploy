from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Sport(Base, TimestampMixin):
    """Вид спорта: футбол (v1), теннис/баскетбол (v2)."""

    __tablename__ = "sports"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # "football", "tennis", "basketball"
    name: Mapped[str] = mapped_column(String(50))

    leagues: Mapped[list["League"]] = relationship(back_populates="sport")


class League(Base, TimestampMixin):
    """Турнир/лига, привязан к виду спорта."""

    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Внешние идентификаторы по источникам данных: {"football_data": "PL", "statsbomb": 2}
    external_ids: Mapped[dict] = mapped_column(JSONB, default=dict)

    sport: Mapped["Sport"] = relationship(back_populates="leagues")
    teams: Mapped[list["Team"]] = relationship(back_populates="league")


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int | None] = mapped_column(ForeignKey("leagues.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Рейтинг Elo, обновляется ML-пайплайном после каждого матча
    elo_rating: Mapped[float] = mapped_column(Numeric(7, 2), default=1500)

    # Внешние идентификаторы по источникам: {"football_data": 57, "statsbomb": 1044}
    external_ids: Mapped[dict] = mapped_column(JSONB, default=dict)

    league: Mapped["League"] = relationship(back_populates="teams")
