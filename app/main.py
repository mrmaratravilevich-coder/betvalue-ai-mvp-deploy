import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.services import prediction_engine, telegram_bot
from app.services.match_ingestion import sync_upcoming_match_window

logger = logging.getLogger(__name__)


async def automatic_match_sync() -> None:
    """Keep the public match database warm without requiring Celery/Redis."""
    await asyncio.sleep(2)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await sync_upcoming_match_window(db)
                logger.info("Automatic match sync completed: %s", result)
                predictions = await prediction_engine.generate_predictions_all_leagues(db)
                logger.info("Automatic prediction refresh completed: %s", predictions)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - background job must not stop the API
            logger.exception("Automatic match sync failed")
        await asyncio.sleep(settings.MATCH_SYNC_INTERVAL_SECONDS)


async def configure_telegram() -> None:
    """Refresh Telegram commands and public metadata without blocking API startup."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    try:
        await telegram_bot.set_commands()
        await telegram_bot.configure_profile()
        logger.info("Telegram bot profile configured")
    except Exception:  # noqa: BLE001 - Telegram must not block the public API
        logger.exception("Telegram bot profile configuration failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    sync_task: asyncio.Task | None = None
    if settings.AUTO_CREATE_SCHEMA:
        import app.models  # noqa: F401 — register all SQLAlchemy models

        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if (
        settings.ENV == "production"
        and settings.AUTO_SYNC_MATCHES
        and (settings.FOOTBALL_DATA_API_KEY or settings.API_SPORTS_KEY)
    ):
        sync_task = asyncio.create_task(automatic_match_sync(), name="automatic-match-sync")
    await configure_telegram()
    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task
        await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    description="Система поиска ставок с положительным EV на основе статистических моделей.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "env": settings.ENV}
