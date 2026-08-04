from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TelegramPayment(Base, TimestampMixin):
    __tablename__ = "telegram_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("telegram_accounts.id"), index=True)
    invoice_payload: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    amount_stars: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(
        String(160), unique=True, nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
