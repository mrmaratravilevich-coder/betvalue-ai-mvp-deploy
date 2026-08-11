import pytest
from datetime import datetime, timezone

from app.models.telegram_account import TelegramAccount
from app.models.telegram_payment import TelegramPayment
from app.services import telegram_bot, telegram_payments


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDb:
    def __init__(self, *values):
        self.values = iter(values)
        self.commits = 0

    async def execute(self, _statement):
        return ScalarResult(next(self.values))

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_pre_checkout_accepts_matching_pending_invoice(monkeypatch):
    payment = TelegramPayment(account_id=1, invoice_payload="pro:42:nonce", amount_stars=25, status="pending")
    calls = []

    async def fake_answer(query_id, *, ok, error_message=None):
        calls.append((query_id, ok, error_message))

    monkeypatch.setattr(telegram_payments.settings, "TELEGRAM_STARS_ENABLED", True)
    monkeypatch.setattr(telegram_payments.settings, "TELEGRAM_PRO_PRICE_STARS", 25)
    monkeypatch.setattr(telegram_payments.settings, "TELEGRAM_PRO_DURATION_DAYS", 30)
    monkeypatch.setattr(telegram_bot, "answer_pre_checkout_query", fake_answer)

    handled = await telegram_payments.handle_payment_update({"pre_checkout_query": {
        "id": "query-1", "invoice_payload": payment.invoice_payload,
        "currency": "XTR", "total_amount": 25,
    }}, FakeDb(payment))

    assert handled is True
    assert calls == [("query-1", True, None)]


@pytest.mark.asyncio
async def test_successful_payment_activates_pro_once(monkeypatch):
    payment = TelegramPayment(account_id=1, invoice_payload="pro:42:nonce", amount_stars=25, status="pending")
    account = TelegramAccount(telegram_user_id=42, first_name="Test", subscription_plan="free")
    account.id = 1
    db = FakeDb(payment, account)
    monkeypatch.setattr(telegram_payments.settings, "TELEGRAM_PRO_DURATION_DAYS", 30)

    handled = await telegram_payments.handle_payment_update({"message": {"successful_payment": {
        "invoice_payload": payment.invoice_payload, "currency": "XTR", "total_amount": 25,
        "telegram_payment_charge_id": "charge-1",
    }}}, db)

    assert handled is True
    assert account.subscription_plan == "pro"
    assert account.subscription_expires_at > datetime.now(timezone.utc)
    assert payment.status == "paid"
    assert payment.telegram_payment_charge_id == "charge-1"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_create_invoice_link_uses_stars_payload(monkeypatch):
    calls = []

    async def fake_call(method, payload=None):
        calls.append((method, payload))
        return "https://t.me/invoice/test"

    monkeypatch.setattr(telegram_bot, "_call", fake_call)
    result = await telegram_bot.create_invoice_link(
        title="BetValue AI Pro", description="30 days", payload="pro:42:nonce", amount_stars=25
    )

    assert result == "https://t.me/invoice/test"
    assert calls[0][0] == "createInvoiceLink"
    assert calls[0][1]["currency"] == "XTR"
    assert "provider_token" not in calls[0][1]
    assert calls[0][1]["prices"] == [{"label": "BetValue AI Pro", "amount": 25}]
