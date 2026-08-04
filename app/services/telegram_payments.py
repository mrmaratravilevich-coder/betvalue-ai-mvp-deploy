"""Telegram Stars invoice validation and idempotent subscription activation."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.telegram_account import TelegramAccount
from app.models.telegram_payment import TelegramPayment
from app.services import telegram_bot


def payments_enabled() -> bool:
    return bool(
        settings.TELEGRAM_STARS_ENABLED
        and settings.TELEGRAM_PRO_PRICE_STARS > 0
        and settings.TELEGRAM_PRO_DURATION_DAYS > 0
    )


async def handle_payment_update(update: dict, db: AsyncSession) -> bool:
    pre_checkout = update.get("pre_checkout_query")
    if pre_checkout:
        await _handle_pre_checkout(pre_checkout, db)
        return True

    message = update.get("message") or {}
    successful_payment = message.get("successful_payment")
    if successful_payment:
        await _handle_successful_payment(successful_payment, db)
        return True
    return False


async def _handle_pre_checkout(query: dict, db: AsyncSession) -> None:
    query_id = str(query.get("id") or "")
    payload = str(query.get("invoice_payload") or "")
    result = await db.execute(
        select(TelegramPayment).where(TelegramPayment.invoice_payload == payload)
    )
    payment = result.scalar_one_or_none()
    valid = bool(
        payments_enabled()
        and payment
        and payment.status == "pending"
        and query.get("currency") == "XTR"
        and query.get("total_amount") == payment.amount_stars
    )
    await telegram_bot.answer_pre_checkout_query(
        query_id,
        ok=valid,
        error_message=None if valid else "Платёж не прошёл проверку. Откройте приложение и попробуйте ещё раз.",
    )


async def _handle_successful_payment(successful_payment: dict, db: AsyncSession) -> None:
    payload = str(successful_payment.get("invoice_payload") or "")
    charge_id = str(successful_payment.get("telegram_payment_charge_id") or "")
    result = await db.execute(
        select(TelegramPayment)
        .where(TelegramPayment.invoice_payload == payload)
        .with_for_update()
    )
    payment = result.scalar_one_or_none()
    if (
        not payment
        or payment.status == "paid"
        or not charge_id
        or successful_payment.get("currency") != "XTR"
        or successful_payment.get("total_amount") != payment.amount_stars
    ):
        return

    account_result = await db.execute(
        select(TelegramAccount).where(TelegramAccount.id == payment.account_id)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        return

    now = datetime.now(timezone.utc)
    current_expiry = account.subscription_expires_at
    if current_expiry and current_expiry.tzinfo is None:
        current_expiry = current_expiry.replace(tzinfo=timezone.utc)
    starts_at = max(now, current_expiry) if current_expiry else now
    account.subscription_plan = "pro"
    account.subscription_expires_at = starts_at + timedelta(days=settings.TELEGRAM_PRO_DURATION_DAYS)
    payment.status = "paid"
    payment.telegram_payment_charge_id = charge_id
    payment.paid_at = now
    await db.commit()
