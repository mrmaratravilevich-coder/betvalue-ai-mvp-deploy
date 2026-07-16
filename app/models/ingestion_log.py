from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import IngestionStatus


class IngestionLog(Base, TimestampMixin):
    """
    Журнал каждого шага ежедневного цикла (06:00 обновление БД, 07:00 коэффициенты,
    08:00 обучение модели, 09:00 поиск EV, почасовое обновление линии).
    """

    __tablename__ = "ingestion_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(80))  # "update_matches" | "update_odds" | "train_model" | ...
    status: Mapped[IngestionStatus] = mapped_column(Enum(IngestionStatus), default=IngestionStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_processed: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
