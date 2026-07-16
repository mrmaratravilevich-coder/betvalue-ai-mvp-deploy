from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BankTxType, UserRole


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(default=True)

    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False)
    bank_transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="user")


class UserSettings(Base, TimestampMixin):
    """Персональные настройки стратегии — используются фильтрами и Kelly-калькулятором."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    min_ev_threshold: Mapped[float] = mapped_column(Numeric(5, 4), default=0.05)   # EV < 5% -> отсекается
    max_odds: Mapped[float] = mapped_column(Numeric(5, 2), default=6.0)            # коэфф. > 6 -> отсекается
    kelly_fraction_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=25.0) # используем 25% Kelly
    min_historical_matches: Mapped[int] = mapped_column(default=1000)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    user: Mapped["User"] = relationship(back_populates="settings")


class BankTransaction(Base, TimestampMixin):
    """История изменений банка — основа для ROI/Yield/Drawdown в аналитике."""

    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ev_bet_id: Mapped[int | None] = mapped_column(ForeignKey("ev_bets.id"), nullable=True)

    type: Mapped[BankTxType] = mapped_column(Enum(BankTxType))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))       # знак: + пополнение/выигрыш, - ставка/вывод
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2))

    user: Mapped["User"] = relationship(back_populates="bank_transactions")
