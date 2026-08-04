"""Telegram webhook endpoint."""

import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token
from app.core.config import settings
from app.db.session import get_db
from app.models.telegram_account import TelegramAccount
from app.models.telegram_payment import TelegramPayment
from app.schemas.telegram import SubscriptionPlanOut, TelegramInvoiceOut, TelegramSessionIn, TelegramSessionOut
from app.services.telegram_auth import TelegramAuthError, validate_init_data
from app.services import telegram_bot, telegram_payments

router = APIRouter(prefix="/telegram", tags=["telegram"])
telegram_bearer = HTTPBearer(auto_error=False)


@router.get("/plans", response_model=list[SubscriptionPlanOut])
async def subscription_plans() -> list[SubscriptionPlanOut]:
    pro_available = telegram_payments.payments_enabled()
    return [
        SubscriptionPlanOut(
            code="free",
            name="Базовый",
            description="Ближайшие матчи и доступные расчёты модели.",
            features=["Расписание матчей", "Вероятности исходов", "Уровень уверенности"],
            available=True,
        ),
        SubscriptionPlanOut(
            code="pro",
            name="Расширенный",
            description="Дополнительный контекст и подборки после подключения источников.",
            features=["Форма команд", "Очные встречи", "Расширенная статистика", "Подборки событий"],
            available=pro_available,
            price_stars=settings.TELEGRAM_PRO_PRICE_STARS if pro_available else None,
        ),
    ]


async def current_telegram_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(telegram_bearer),
    db: AsyncSession = Depends(get_db),
) -> TelegramAccount:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram authorization required")
    claims = decode_access_token(credentials.credentials)
    subject = str((claims or {}).get("sub") or "")
    if (claims or {}).get("auth_source") != "telegram" or not subject.startswith("telegram:"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram authorization")
    try:
        telegram_user_id = int(subject.removeprefix("telegram:"))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram authorization") from exc
    result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram account not found")
    return account


@router.post("/invoice", response_model=TelegramInvoiceOut)
async def create_pro_invoice(
    account: TelegramAccount = Depends(current_telegram_account),
    db: AsyncSession = Depends(get_db),
) -> TelegramInvoiceOut:
    if not telegram_payments.payments_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram Stars payments are not enabled")

    invoice_payload = f"pro:{account.telegram_user_id}:{secrets.token_urlsafe(24)}"
    payment = TelegramPayment(
        account_id=account.id,
        invoice_payload=invoice_payload,
        amount_stars=settings.TELEGRAM_PRO_PRICE_STARS,
    )
    db.add(payment)
    await db.commit()
    try:
        invoice_url = await telegram_bot.create_invoice_link(
            title="BetValue AI Pro",
            description=f"Расширенный доступ на {settings.TELEGRAM_PRO_DURATION_DAYS} дней",
            payload=invoice_payload,
            amount_stars=payment.amount_stars,
        )
    except Exception as exc:
        payment.status = "failed"
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create Telegram invoice") from exc
    return TelegramInvoiceOut(
        invoice_url=invoice_url,
        plan_code="pro",
        price_stars=payment.amount_stars,
    )


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
    db: AsyncSession = Depends(get_db),
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

    payment_processed = await telegram_payments.handle_payment_update(update, db)
    if not payment_processed:
        background_tasks.add_task(telegram_bot.handle_update, update)
    return {"ok": True}
