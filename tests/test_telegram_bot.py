from datetime import datetime, timezone

import pytest

from app.services import telegram_bot
from app.services.upcoming_matches import UpcomingFixture, UpcomingMatches


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
async def test_matches_command_lists_upcoming_fixtures(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str) -> dict:
        sent.append((chat_id, text))
        return {}

    async def fake_matches() -> UpcomingMatches:
        kickoff = datetime(2026, 8, 15, 19, 30, tzinfo=timezone.utc)
        return UpcomingMatches(
            football=(
                UpcomingFixture(
                    sport="football",
                    competition="Premier League",
                    home_team="Liverpool",
                    away_team="Arsenal",
                    kickoff_at=kickoff,
                    source="football-data.org",
                ),
            ),
            hockey=(
                UpcomingFixture(
                    sport="hockey",
                    competition="KHL",
                    home_team="Динамо",
                    away_team="Спартак",
                    kickoff_at=kickoff,
                    source="API-SPORTS Hockey",
                ),
            ),
            errors={},
        )

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot, "get_upcoming_matches", fake_matches)

    await telegram_bot.handle_update(
        {"message": {"text": "/matches@BetValueAI_bot", "chat": {"id": 42}}}
    )

    assert "Liverpool × Arsenal" in sent[0][1]
    assert "Динамо × Спартак" in sent[0][1]
    assert "время МСК" in sent[0][1]


@pytest.mark.asyncio
async def test_matches_command_handles_empty_schedule(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str) -> dict:
        sent.append((chat_id, text))
        return {}

    async def fake_matches() -> UpcomingMatches:
        return UpcomingMatches(football=(), hockey=(), errors={})

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot, "get_upcoming_matches", fake_matches)

    await telegram_bot.handle_update(
        {"message": {"text": "/matches", "chat": {"id": 42}}}
    )

    assert "Матчей в ближайшие 30 дней не найдено" in sent[0][1]
    assert "Матчей на ближайшие 4 дня не найдено" in sent[0][1]
