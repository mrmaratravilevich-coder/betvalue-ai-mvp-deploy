"""
Обёртка над statsbombpy (открытый датасет StatsBomb).
statsbombpy синхронный (тянет JSON из открытого GitHub-репозитория
statsbomb/open-data) — оборачиваем в asyncio.to_thread, чтобы не блокировать
event loop FastAPI/Celery.

Датасет содержит только определённые исторические соревнования/сезоны
(не текущие туры топ-лиг) — это источник ДЕТАЛЬНОЙ статистики (xG, удары,
владение, составы) для обучения модели, а не источник актуальных расписаний.
Актуальные матчи и результаты берём из football_data.py.
"""
import asyncio

import pandas as pd


class StatsBombError(RuntimeError):
    pass


def _import_statsbombpy():
    try:
        from statsbombpy import sb
    except ImportError as exc:  # pragma: no cover
        raise StatsBombError("Пакет statsbombpy не установлен (см. requirements.txt)") from exc
    return sb


async def fetch_matches(competition_id: int, season_id: int) -> pd.DataFrame:
    """Список матчей соревнования/сезона (id, дата, команды, счёт)."""
    sb = _import_statsbombpy()

    def _call() -> pd.DataFrame:
        return sb.matches(competition_id=competition_id, season_id=season_id)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001 — statsbombpy кидает разные типы ошибок сети/парсинга
        raise StatsBombError(f"Не удалось получить матчи StatsBomb ({competition_id}/{season_id}): {exc}") from exc


async def fetch_team_match_stats(match_id: int) -> pd.DataFrame:
    """
    Агрегированная статистика по событиям матча (удары, xG и т.д.), команда за команду.
    Возвращает "сырые" события — агрегация под MatchTeamStat делается в match_ingestion.py,
    т.к. набор считаемых метрик может меняться вместе с фичами ML-модели.
    """
    sb = _import_statsbombpy()

    def _call() -> pd.DataFrame:
        return sb.events(match_id=match_id)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        raise StatsBombError(f"Не удалось получить события матча StatsBomb {match_id}: {exc}") from exc
