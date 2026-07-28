import pytest

from app.services import telegram_bot


@pytest.mark.asyncio
async def test_start_command_sends_welcome(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str) -> dict:
        sent.append((chat_id, text))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)

    await telegram_bot.handle_update(
        {"message": {"text": "/start", "chat": {"id": 42}}}
    )

    assert sent[0][0] == 42
    assert "BetValue AI подключён" in sent[0][1]


@pytest.mark.asyncio
async def test_matches_command_reports_sources(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str) -> dict:
        sent.append((chat_id, text))
        return {}

    async def fake_health() -> dict:
        return {
            "football": {"ok": True, "matches": 380},
            "hockey": {"ok": True},
        }

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot, "check_mvp_sources", fake_health)

    await telegram_bot.handle_update(
        {"message": {"text": "/matches@BetValueAI_bot", "chat": {"id": 42}}}
    )

    assert "380 матчей PL" in sent[0][1]
    assert "API-SPORTS Hockey: работает" in sent[0][1]
