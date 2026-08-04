from datetime import datetime, timezone

import pytest

from app.services import telegram_bot
from app import main as app_main
from app.services.upcoming_matches import UpcomingFixture, UpcomingMatches


@pytest.mark.asyncio
async def test_start_command_sends_welcome(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_WEB_APP_URL", "https://bvai.onrender.com/telegram")
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_CHANNEL_URL", None)

    await telegram_bot.handle_update(
        {"message": {"text": "/start", "chat": {"id": 42}}}
    )

    assert sent[0][0] == 42
    assert "BetValue AI готов к работе" in sent[0][1]
    assert "вероятности исходов" in sent[0][1]
    assert "сценарии экспрессов" in sent[0][1]
    assert "не обещаем гарантированный исход" in sent[0][1]
    button = sent[0][2]["inline_keyboard"][0][0]
    assert button["text"] == "Открыть матчи"
    assert button["web_app"]["url"] == "https://bvai.onrender.com/telegram"
    assert sent[0][2]["inline_keyboard"][1][0]["text"] == "Тариф Pro"
    assert sent[0][2]["inline_keyboard"][1][0]["web_app"]["url"].endswith("#plans")


@pytest.mark.asyncio
async def test_matches_command_lists_upcoming_fixtures(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
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

    assert "Ливерпуль × Арсенал" in sent[0][1]
    assert "Динамо × Спартак" in sent[0][1]
    assert "Премьер-лига" in sent[0][1]
    assert "время МСК" in sent[0][1]


@pytest.mark.asyncio
async def test_matches_command_handles_empty_schedule(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
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


@pytest.mark.asyncio
async def test_channel_command_opens_configured_channel(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_CHANNEL_URL", "@BetValueAI_Analytics")

    await telegram_bot.handle_update(
        {"message": {"text": "/channel", "chat": {"id": 42}}}
    )

    assert "Технические разборы" in sent[0][1]
    assert sent[0][2]["inline_keyboard"][0][0]["url"] == "https://t.me/BetValueAI_Analytics"


@pytest.mark.asyncio
async def test_channel_command_handles_missing_channel(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_CHANNEL_URL", None)

    await telegram_bot.handle_update(
        {"message": {"text": "/channel", "chat": {"id": 42}}}
    )

    assert "готовится к запуску" in sent[0][1]
    assert sent[0][2] is None


@pytest.mark.asyncio
async def test_app_command_opens_mini_app(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_WEB_APP_URL", "https://bvai.onrender.com/telegram")

    await telegram_bot.handle_update({"message": {"text": "/app", "chat": {"id": 42}}})

    assert "экспресс-сценариев" in sent[0][1]
    assert sent[0][2]["inline_keyboard"][0][0]["web_app"]["url"] == "https://bvai.onrender.com/telegram"
    assert sent[0][2]["inline_keyboard"][1][0]["text"] == "Тариф Pro"


@pytest.mark.asyncio
async def test_pro_command_opens_tariff(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_WEB_APP_URL", "https://bvai.onrender.com/telegram")

    await telegram_bot.handle_update({"message": {"text": "/pro", "chat": {"id": 42}}})

    assert "полный контекст" in sent[0][1]
    assert "разбивкой риска" in sent[0][1]
    assert sent[0][2]["inline_keyboard"][0][0]["text"] == "Открыть тариф Pro"
    assert sent[0][2]["inline_keyboard"][0][0]["web_app"]["url"].endswith("#plans")


@pytest.mark.asyncio
async def test_unknown_command_shows_recovery(monkeypatch):
    sent = []

    async def fake_send(chat_id: int, text: str, reply_markup=None) -> dict:
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(telegram_bot, "send_message", fake_send)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_WEB_APP_URL", None)

    await telegram_bot.handle_update({"message": {"text": "/unknown", "chat": {"id": 42}}})

    assert "Не нашёл такую команду" in sent[0][1]


@pytest.mark.asyncio
async def test_configure_profile_sets_copy_and_menu_button(monkeypatch):
    calls = []

    async def fake_call(method: str, payload=None) -> dict:
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_bot, "_call", fake_call)
    monkeypatch.setattr(
        telegram_bot.settings,
        "TELEGRAM_WEB_APP_URL",
        "https://bvai.onrender.com/telegram",
    )

    await telegram_bot.configure_profile()

    assert [method for method, _ in calls] == [
        "setMyName",
        "setMyShortDescription",
        "setMyDescription",
        "setChatMenuButton",
    ]
    menu_button = calls[-1][1]["menu_button"]
    assert menu_button["text"] == "Открыть матчи"
    assert menu_button["web_app"]["url"] == "https://bvai.onrender.com/telegram"


@pytest.mark.asyncio
async def test_configure_profile_skips_menu_without_web_app(monkeypatch):
    calls = []

    async def fake_call(method: str, payload=None) -> dict:
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram_bot, "_call", fake_call)
    monkeypatch.setattr(telegram_bot.settings, "TELEGRAM_WEB_APP_URL", None)

    await telegram_bot.configure_profile()

    assert "setChatMenuButton" not in [method for method, _ in calls]


@pytest.mark.asyncio
async def test_api_startup_configures_telegram_profile(monkeypatch):
    called = []

    async def fake_commands() -> None:
        called.append("commands")

    async def fake_profile() -> None:
        called.append("profile")

    monkeypatch.setattr(app_main.settings, "TELEGRAM_BOT_TOKEN", "configured")
    monkeypatch.setattr(app_main.telegram_bot, "set_commands", fake_commands)
    monkeypatch.setattr(app_main.telegram_bot, "configure_profile", fake_profile)

    await app_main.configure_telegram()

    assert called == ["commands", "profile"]
