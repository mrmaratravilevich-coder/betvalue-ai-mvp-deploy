"""Minimal async Telegram Bot API client and long-polling command handler."""

import asyncio
import logging
from datetime import timedelta, timezone

import httpx

from app.core.config import settings
from app.services.name_localization import localize_name
from app.services.upcoming_matches import UpcomingFixture, UpcomingMatches, get_upcoming_matches

logger = logging.getLogger(__name__)
MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")


class TelegramBotError(RuntimeError):
    pass


def _token() -> str:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN is not configured")
    return settings.TELEGRAM_BOT_TOKEN


async def _call(method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{_token()}/{method}"
    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(url, json=payload or {})
    data = response.json()
    if not response.is_success or not data.get("ok"):
        description = data.get("description", f"HTTP {response.status_code}")
        raise TelegramBotError(f"Telegram API error: {description}")
    return data["result"]


async def get_me() -> dict:
    return await _call("getMe")


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await _call(
        "sendMessage",
        payload,
    )


async def set_commands() -> None:
    await _call(
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Запустить BetValue AI"},
                {"command": "matches", "description": "Показать ближайшие матчи"},
                {"command": "app", "description": "Открыть приложение"},
                {"command": "channel", "description": "Открыть канал аналитики"},
                {"command": "help", "description": "Показать справку"},
            ]
        },
    )


def _format_fixture(fixture: UpcomingFixture) -> str:
    kickoff = fixture.kickoff_at.astimezone(MOSCOW_TZ)
    return (
        f"{kickoff:%d.%m %H:%M} — {localize_name(fixture.home_team)} × "
        f"{localize_name(fixture.away_team)}\n"
        f"   {localize_name(fixture.competition)}"
    )


def _format_matches(matches: UpcomingMatches) -> str:
    lines = ["📅 Ближайшие матчи · время МСК"]

    lines.extend(["", "⚽ Футбол · football-data.org"])
    if matches.football:
        lines.extend(_format_fixture(fixture) for fixture in matches.football)
    elif "football" in matches.errors:
        lines.append("Источник временно недоступен.")
    else:
        lines.append("Матчей в ближайшие 30 дней не найдено.")

    lines.extend(["", "🏒 Хоккей · API-SPORTS"])
    if matches.hockey:
        lines.extend(_format_fixture(fixture) for fixture in matches.hockey)
    elif "hockey" in matches.errors:
        lines.append("Источник временно недоступен.")
    else:
        lines.append("Матчей на ближайшие 4 дня не найдено.")

    lines.extend(["", "Данные обновляются не чаще одного раза в 5 минут."])
    return "\n".join(lines)


def _channel_url() -> str | None:
    value = (settings.TELEGRAM_CHANNEL_URL or "").strip()
    if not value:
        return None
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    return value


def _web_app_url() -> str | None:
    value = (settings.TELEGRAM_WEB_APP_URL or "").strip()
    return value or None


def _start_keyboard() -> dict | None:
    rows = []
    if web_app_url := _web_app_url():
        rows.append([{"text": "Открыть матчи", "web_app": {"url": web_app_url}}])
    if channel_url := _channel_url():
        rows.append([{"text": "Канал аналитики", "url": channel_url}])
    return {"inline_keyboard": rows} if rows else None


def _app_keyboard() -> dict | None:
    if web_app_url := _web_app_url():
        return {
            "inline_keyboard": [
                [{"text": "Открыть BetValue AI", "web_app": {"url": web_app_url}}]
            ]
        }
    return None


def _channel_keyboard(url: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Открыть канал аналитики", "url": url}],
        ]
    }


async def handle_update(update: dict) -> None:
    """Process one Telegram update received by polling or webhook."""
    message = update.get("message") or {}
    raw_text = (message.get("text") or "").strip().split(maxsplit=1)[0]
    command = raw_text.split("@", maxsplit=1)[0].lower()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return

    try:
        if command == "/start":
            first_name = str((message.get("from") or {}).get("first_name") or "").strip()
            greeting = f"{first_name}, BetValue AI готов к работе." if first_name else "BetValue AI готов к работе."
            await send_message(
                chat_id,
                f"{greeting}\n\n"
                "Матчи, расчёты и уровень уверенности — в одном приложении. "
                "Аналитика появляется только при достаточном объёме данных.\n\n"
                "Откройте приложение или отправьте /matches для краткого расписания.",
                reply_markup=_start_keyboard(),
            )
        elif command == "/help":
            await send_message(
                chat_id,
                "Команды BetValue AI:\n"
                "/start — подключить бота\n"
                "/matches — показать ближайшие матчи\n"
                "/app — открыть приложение\n"
                "/channel — открыть канал аналитики\n"
                "/help — показать справку",
            )
        elif command == "/app":
            keyboard = _app_keyboard()
            if keyboard:
                await send_message(
                    chat_id,
                    "Откройте ленту матчей и полный разбор, не выходя из Telegram.",
                    reply_markup=keyboard,
                )
            else:
                await send_message(chat_id, "Приложение временно недоступно. Используйте /matches.")
        elif command == "/channel":
            channel_url = _channel_url()
            if channel_url:
                await send_message(
                    chat_id,
                    "Технические разборы матчей, обновления модели и открытая статистика — в канале BetValue AI.",
                    reply_markup=_channel_keyboard(channel_url),
                )
            else:
                await send_message(
                    chat_id,
                    "Канал BetValue AI готовится к запуску. Пока используйте /matches для просмотра ближайших событий.",
                )
        elif command == "/matches":
            matches = await get_upcoming_matches()
            await send_message(chat_id, _format_matches(matches))
        elif command.startswith("/"):
            await send_message(
                chat_id,
                "Не нашёл такую команду. Отправьте /help или откройте приложение.",
                reply_markup=_app_keyboard(),
            )
    except (httpx.HTTPError, TelegramBotError) as exc:
        logger.warning("Telegram update error: %s", exc)


async def poll() -> None:
    await set_commands()
    offset = 0
    logger.info("Telegram polling started")
    while True:
        try:
            updates = await _call("getUpdates", {"offset": offset, "timeout": 25})
            for update in updates:
                offset = update["update_id"] + 1
                await handle_update(update)
        except (httpx.HTTPError, TelegramBotError) as exc:
            logger.warning("Telegram polling error: %s", exc)
            await asyncio.sleep(5)
