from sqlalchemy import JSON, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BetStatus


class Prediction(Base, TimestampMixin):
    """
    Вероятность исхода от ансамбля моделей (Poisson / XGBoost / LightGBM /
    Logistic Regression / Random Forest) для конкретного матча и рынка.
    """

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"))
    selection: Mapped[str] = mapped_column(String(40))

    model_probability: Mapped[float] = mapped_column(Numeric(6, 5))
    model_version: Mapped[str] = mapped_column(String(40))

    # Вклад отдельных моделей в итоговую (ансамблевую) вероятность
    ensemble_components: Mapped[dict] = mapped_column(JSON, default=dict)
    # Оценка неопределённости модели (0..1) — используется фильтром "высокая неопределённость"
    uncertainty: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    match: Mapped["Match"] = relationship(back_populates="predictions")
    market: Mapped["Market"] = relationship()
    ev_bets: Mapped[list["EVBet"]] = relationship(back_populates="prediction")


class EVBet(Base, TimestampMixin):
    """Рекомендация ставки с положительным EV — результат сравнения Prediction и OddsLine."""

    __tablename__ = "ev_bets"

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"))
    odds_line_id: Mapped[int] = mapped_column(ForeignKey("odds_lines.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    ev: Mapped[float] = mapped_column(Numeric(6, 4))                     # напр. 0.281 = +28.1%
    kelly_fraction: Mapped[float] = mapped_column(Numeric(6, 5))         # доля банка по формуле Kelly
    recommended_stake: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)  # 0..10, для карточки/Telegram

    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)   # текст AI Explain
    status: Mapped[BetStatus] = mapped_column(Enum(BetStatus), default=BetStatus.PENDING)

    prediction: Mapped["Prediction"] = relationship(back_populates="ev_bets")
    odds_line: Mapped["OddsLine"] = relationship()
