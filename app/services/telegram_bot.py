"""Minimal async Telegram Bot API client and long-polling command handler."""

import asyncio
import logging

import httpx

from app.core.config import settings
from app.services.source_health import check_mvp_sources

logger = logging.getLogger(__name__)


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


async def send_message(chat_id: int, text: str) -> dict:
    return await _call(
        "sendMessage",
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
    )


async def set_commands() -> None:
    await _call(
        "setMyCommands",
        {
            "commands": [
                {"command": "start", "description": "Запустить BetValue AI"},
                {"command": "matches", "description": "Проверить источники матчей"},
                {"command": "help", "description": "Показать справку"},
            ]
        },
    )


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
            await send_message(
                chat_id,
                "✅ BetValue AI подключён!\n\n"
                "Команда /matches покажет состояние источников футбола и хоккея.\n"
                "Аналитика EV появится после загрузки матчей и коэффициентов.",
            )
        elif command == "/help":
            await send_message(
                chat_id,
                "Команды BetValue AI:\n"
                "/start — подключить бота\n"
                "/matches — проверить спортивные источники\n"
                "/help — показать справку",
            )
        elif command == "/matches":
            health = await check_mvp_sources()
            football = health["football"]
            hockey = health["hockey"]
            await send_message(
                chat_id,
                "📊 Источники BetValue AI\n\n"
                f"⚽ football-data.org: {'работает' if football['ok'] else 'ошибка'}"
                f" ({football.get('matches', 0)} матчей PL)\n"
                f"🏒 API-SPORTS Hockey: {'работает' if hockey['ok'] else 'ошибка'}",
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
