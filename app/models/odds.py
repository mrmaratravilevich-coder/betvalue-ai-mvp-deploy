from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MarketCode, OddsSourceType


class OddsSource(Base, TimestampMixin):
    """
    Источник коэффициентов. На старте проекта активных источников нет —
    таблица существует, чтобы модуль сбора линий можно было подключить,
    не меняя схему БД (см. app/services/odds_ingestion.py — заглушка).
    """

    __tablename__ = "odds_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    type: Mapped[OddsSourceType] = mapped_column(Enum(OddsSourceType))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Market(Base, TimestampMixin):
    """Справочник рынков (1X2, тоталы, форы и т.д.)."""

    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[MarketCode] = mapped_column(Enum(MarketCode), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class OddsLine(Base, TimestampMixin):
    """
    Снимок коэффициента в конкретный момент времени.
    Хранится каждое обновление (почасовое, см. ежедневный цикл в ТЗ) —
    это и есть история для расчёта Closing Line Value.
    """

    __tablename__ = "odds_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("odds_sources.id"))

    selection: Mapped[str] = mapped_column(String(40))  # "home" | "draw" | "away" | "over_2.5" | ...
    price: Mapped[float] = mapped_column(Numeric(6, 3))
    line_value: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # для тоталов/фор, напр. 2.5

    @property
    def implied_probability(self) -> float:
        return 1 / float(self.price)

    match: Mapped["Match"] = relationship(back_populates="odds_lines")
    market: Mapped["Market"] = relationship()
    source: Mapped["OddsSource"] = relationship()
