"""Development entry point for the Telegram long-polling worker."""

import asyncio

from app.services.telegram_bot import poll


if __name__ == "__main__":
    asyncio.run(poll())
