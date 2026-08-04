"""Telegram webhook endpoint."""

import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.config import settings
from app.db.session import get_db
from app.models.telegram_account import TelegramAccount
from app.schemas.telegram import TelegramSessionIn, TelegramSessionOut
from app.services.telegram_auth import TelegramAuthError, validate_init_data
from app.services.telegram_bot import handle_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/session", response_model=TelegramSessionOut)
async def create_telegram_session(
    payload: TelegramSessionIn,
    db: AsyncSession = Depends(get_db),
) -> TelegramSessionOut:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram login is unavailable")
    try:
        telegram_user = validate_init_data(
            payload.init_data,
            settings.TELEGRAM_BOT_TOKEN,
            max_age_seconds=settings.TELEGRAM_INIT_DATA_MAX_AGE_SECONDS,
        )
    except TelegramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    result = await db.execute(
        select(TelegramAccount).where(
            TelegramAccount.telegram_user_id == telegram_user.id
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = TelegramAccount(
            telegram_user_id=telegram_user.id,
            first_name=telegram_user.first_name,
        )
        db.add(account)
    account.first_name = telegram_user.first_name
    account.last_name = telegram_user.last_name
    account.username = telegram_user.username
    account.language_code = telegram_user.language_code
    await db.commit()
    await db.refresh(account)

    token = create_access_token(
        subject=f"telegram:{account.telegram_user_id}",
        extra_claims={"auth_source": "telegram"},
    )
    return TelegramSessionOut(
        access_token=token,
        telegram_user_id=account.telegram_user_id,
        first_name=account.first_name,
        username=account.username,
        subscription_plan=account.subscription_plan,
        subscription_expires_at=account.subscription_expires_at,
    )


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    update: dict,
    background_tasks: BackgroundTasks,
    telegram_secret: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> dict[str, bool]:
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook is not configured",
        )
    if not telegram_secret or not secrets.compare_digest(telegram_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )

    background_tasks.add_task(handle_update, update)
    return {"ok": True}
