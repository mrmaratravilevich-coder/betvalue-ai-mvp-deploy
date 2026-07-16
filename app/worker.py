"""
Celery-приложение и планировщик (beat) — реализация раздела "Ежедневный
цикл" ТЗ:

    06:00        Обновление базы            -> task_update_matches
    07:00        Получение коэффициентов    -> покрывается task_update_odds (см. ниже)
    08:00        Обучение модели            -> task_train_model
    09:00        Поиск EV                   -> task_find_ev
    Каждый час   Обновление линии           -> task_update_odds (hourly)
    За 30 минут  Обновление составов        -> task_update_lineups (ЗАГЛУШКА)

Отдельной daily-задачи на 07:00 для коэффициентов нет: почасовая задача
(minute=0) естественно покрывает и 7 утра — заводить вторую задачу на тот
же час означало бы дважды дёргать Betfair в 07:00 без всякой пользы.

EV пересчитывается не только в 09:00, но и каждый час через 5 минут после
обновления линии (minute=5) — иначе рекомендации весь день опирались бы на
цены восьмичасовой давности, что прямо противоречит смыслу "почасового
обновления линии" из ТЗ.

Обновление составов ("За 30 минут" в ТЗ) — заглушка: ни football-data.org,
ни StatsBomb Open Data, ни Betfair не отдают составы. Задача зарегистрирована
и стоит в расписании, чтобы инфраструктура была готова, как только появится
источник данных.

Каждый шаг цикла пишет запись в IngestionLog (RUNNING -> SUCCESS/FAILED) —
эта таблица для того и создавалась (см. app/models/ingestion_log.py).

Расписание — в часовом поясе Europe/Moscow (тот же оффсет, что и в
Татарстане, где базируется STZ16): время из ТЗ ("06:00" и т.д.) имеет смысл
только в местном времени, а не в UTC контейнера.
"""
import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models.enums import IngestionStatus
from app.models.ingestion_log import IngestionLog
from app.services import ev_generation, match_ingestion, odds_ingestion, prediction_engine

logger = logging.getLogger(__name__)

celery_app = Celery(
    "betvalue",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.timezone = settings.CELERY_TIMEZONE
celery_app.conf.enable_utc = True

celery_app.conf.beat_schedule = {
    "06-00-update-matches": {
        "task": "app.worker.task_update_matches",
        "schedule": crontab(hour=6, minute=0),
    },
    "hourly-update-odds": {
        "task": "app.worker.task_update_odds",
        "schedule": crontab(minute=0),
    },
    "08-00-train-model": {
        "task": "app.worker.task_train_model",
        "schedule": crontab(hour=8, minute=0),
    },
    "09-00-find-ev": {
        "task": "app.worker.task_find_ev",
        "schedule": crontab(hour=9, minute=0),
    },
    "hourly-find-ev-refresh": {
        "task": "app.worker.task_find_ev",
        "schedule": crontab(minute=5),
    },
    "every-30-min-update-lineups": {
        "task": "app.worker.task_update_lineups",
        "schedule": crontab(minute="*/30"),
    },
}

# Позволяет запускать и `celery -A app.worker worker`, и `celery -A app.worker.celery_app worker`
app = celery_app


def _extract_count(result) -> int:
    if isinstance(result, dict):
        return sum(v for v in result.values() if isinstance(v, int))
    return 0


def _run_logged(job_name: str, coro_factory) -> dict:
    """
    Оборачивает вызов сервиса: пишет IngestionLog (RUNNING -> SUCCESS/FAILED)
    и выполняет корутину в отдельном event loop.
    """

    async def runner() -> dict:
        try:
            async with AsyncSessionLocal() as db:
                log = IngestionLog(
                    job_name=job_name,
                    status=IngestionStatus.RUNNING,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(log)
                await db.commit()
                await db.refresh(log)

                try:
                    result = await coro_factory(db)
                except Exception as exc:  # noqa: BLE001 — логируем любую ошибку задачи и пробрасываем дальше
                    await db.rollback()
                    log.status = IngestionStatus.FAILED
                    log.finished_at = datetime.now(timezone.utc)
                    log.error = str(exc)[:2000]
                    await db.commit()
                    logger.exception("Задача %s завершилась с ошибкой", job_name)
                    raise

                log.status = IngestionStatus.SUCCESS
                log.finished_at = datetime.now(timezone.utc)
                log.records_processed = _extract_count(result)
                await db.commit()
                return result
        finally:
            # Celery выполняет задачи одна за другой в одном процессе, но каждый
            # вызов asyncio.run() создаёт НОВЫЙ event loop, а соединения asyncpg
            # привязаны к тому loop, на котором были открыты. dispose() должен
            # выполниться В ТОМ ЖЕ loop (внутри этой же корутины) — если вызвать
            # его отдельным asyncio.run() снаружи, закрытие уйдёт в другой loop
            # и упадёт с "Event loop is closed". Небольшой оверхед на
            # переустановку соединения оправдан: задачи фоновые и нечастые.
            await engine.dispose()

    return asyncio.run(runner())


@celery_app.task(
    name="app.worker.task_update_matches",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def task_update_matches() -> dict:
    return _run_logged("update_matches", match_ingestion.run_daily_match_update)


@celery_app.task(
    name="app.worker.task_update_odds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def task_update_odds() -> dict:
    return _run_logged("update_odds", odds_ingestion.sync_all_betfair_leagues)


@celery_app.task(name="app.worker.task_train_model")
def task_train_model() -> dict:
    return _run_logged("train_model", prediction_engine.generate_predictions_all_leagues)


@celery_app.task(name="app.worker.task_find_ev")
def task_find_ev() -> dict:
    return _run_logged("find_ev", ev_generation.generate_ev_bets_all)


async def _lineups_not_implemented(db) -> dict:
    logger.info("update_lineups: источник данных о составах не подключён — задача пропущена")
    return {"status": "not_implemented"}


@celery_app.task(name="app.worker.task_update_lineups")
def task_update_lineups() -> dict:
    """
    ЗАГЛУШКА. Раздел ТЗ "За 30 минут — обновление составов" требует источника
    данных о заявках на матч — среди подключённых (football-data.org,
    StatsBomb Open Data, Betfair Exchange) такого нет. Задача стоит в
    расписании и пишется в IngestionLog наравне с остальными шагами цикла,
    чтобы её было достаточно один раз реализовать и не трогать Celery beat
    заново, когда источник появится.
    """
    return _run_logged("update_lineups", _lineups_not_implemented)
