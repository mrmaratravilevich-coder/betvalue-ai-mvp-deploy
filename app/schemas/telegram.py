from datetime import datetime

from pydantic import BaseModel, Field


class TelegramSessionIn(BaseModel):
    init_data: str = Field(min_length=1, max_length=16_384)


class TelegramSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    telegram_user_id: int
    first_name: str
    username: str | None
    subscription_plan: str
    subscription_expires_at: datetime | None
