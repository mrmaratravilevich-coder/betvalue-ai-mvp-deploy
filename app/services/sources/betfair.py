"""
Тонкий клиент Betfair Exchange API (Betting API, JSON-RPC).

Схема авторизации подтверждена официальной документацией разработчика Betfair
(support.developer.betfair.com, июль 2026):

  - Delayed App Key бесплатен, не требует активации, даёт котировки с задержкой
    1-180 сек — этого достаточно для аналитики (нам не нужна live-торговля).
    Live App Key с разовым сбором £499 нужен ТОЛЬКО для реального выставления
    ставок ("Read-only access via the Live App Key isn't permitted"), поэтому
    для этого проекта (аналитика без автоматических ставок) он не нужен вообще.
  - Логин: POST identitysso.betfair.com/api/login (form-data username/password,
    заголовок X-Application: <app_key>) -> {"token": "...", "status": "SUCCESS", "error": ""}.
    Для продакшн-автоматизации Betfair рекомендует сертификатный логин
    (identitysso-cert.betfair.com) — не реализован здесь, это следующий шаг
    при переходе с MVP на постоянно работающий сервис (сессия не будет зависеть
    от истечения пароля/2FA так часто).
  - Все Betting-запросy — POST на
    https://api.betfair.com/exchange/betting/json-rpc/v1
    с заголовками X-Application и X-Authentication (sessionToken),
    метод в стиле "SportsAPING/v1.0/<name>".
"""
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

LOGIN_URL = "https://identitysso.betfair.com/api/login"
KEEP_ALIVE_URL = "https://identitysso.betfair.com/api/keepAlive"
BETTING_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

SOCCER_EVENT_TYPE_ID = "1"  # Betfair eventTypeId для футбола


class BetfairError(RuntimeError):
    pass


class BetfairAuthError(BetfairError):
    pass


@dataclass
class BetfairSession:
    token: str
    app_key: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-Application": self.app_key,
            "X-Authentication": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


async def login() -> BetfairSession:
    if settings.BETFAIR_APP_KEY and settings.BETFAIR_SESSION_TOKEN:
        return BetfairSession(token=settings.BETFAIR_SESSION_TOKEN, app_key=settings.BETFAIR_APP_KEY)

    """Интерактивный логин по паролю. Требует BETFAIR_APP_KEY/USERNAME/PASSWORD в .env."""
    if not (settings.BETFAIR_APP_KEY and settings.BETFAIR_USERNAME and settings.BETFAIR_PASSWORD):
        raise BetfairAuthError(
            "BETFAIR_APP_KEY / BETFAIR_USERNAME / BETFAIR_PASSWORD не заданы в .env — "
            "получите Delayed App Key через Accounts API Demo Tool "
            "(https://support.developer.betfair.com, статья 'How do I get started?')"
        )

    headers = {
        "X-Application": settings.BETFAIR_APP_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"username": settings.BETFAIR_USERNAME, "password": settings.BETFAIR_PASSWORD}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(LOGIN_URL, headers=headers, data=data)
    response.raise_for_status()
    payload = response.json()

    # Подтверждено официальной документацией (Interactive Login - API Endpoint):
    # {"token": "...", "product": "...", "status": "SUCCESS", "error": ""}
    if payload.get("status") != "SUCCESS":
        raise BetfairAuthError(f"Betfair логин не удался: status={payload.get('status')} error={payload.get('error')}")

    return BetfairSession(token=payload["token"], app_key=settings.BETFAIR_APP_KEY)


async def keep_alive(session: BetfairSession) -> None:
    """Продлевает сессию (иначе истекает от неактивности)."""
    headers = {"X-Application": session.app_key, "X-Authentication": session.token, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(KEEP_ALIVE_URL, headers=headers)
    if response.status_code != 200 or response.json().get("status") != "SUCCESS":
        raise BetfairAuthError("Не удалось продлить сессию Betfair — потребуется повторный login()")


async def _rpc_call(session: BetfairSession, method: str, params: dict) -> list | dict:
    body = {"jsonrpc": "2.0", "method": f"SportsAPING/v1.0/{method}", "params": params, "id": 1}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(BETTING_URL, headers=session.headers, json=body)
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        error = payload["error"]
        raise BetfairError(f"Betfair API error [{method}]: {error.get('message', error)}")
    return payload["result"]


async def list_event_types(session: BetfairSession) -> list[dict]:
    return await _rpc_call(session, "listEventTypes", {"filter": {}})


async def list_competitions(session: BetfairSession, event_type_id: str = SOCCER_EVENT_TYPE_ID) -> list[dict]:
    """
    Турниры с активными рынками прямо сейчас. Возвращает [{"competition": {"id": ..., "name": ...}, ...}].
    Используется, чтобы вручную подобрать betfair_competition_id для app/core/leagues.py —
    Betfair не публикует статичный справочник id по турнирам.
    """
    return await _rpc_call(session, "listCompetitions", {"filter": {"eventTypeIds": [event_type_id]}})


async def list_market_catalogue(
    session: BetfairSession,
    market_type_codes: list[str],
    date_from: datetime,
    date_to: datetime,
    competition_ids: list[str] | None = None,
    max_results: int = 200,
) -> list[dict]:
    """
    Список рынков (без цен) — событие, команды, id рынка.
    market_type_codes: например ["MATCH_ODDS", "OVER_UNDER_25", "BOTH_TEAMS_TO_SCORE"].
    """
    market_filter: dict = {
        "eventTypeIds": [SOCCER_EVENT_TYPE_ID],
        "marketTypeCodes": market_type_codes,
        "marketStartTime": {"from": date_from.isoformat(), "to": date_to.isoformat()},
    }
    if competition_ids:
        market_filter["competitionIds"] = competition_ids

    return await _rpc_call(
        session,
        "listMarketCatalogue",
        {
            "filter": market_filter,
            "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME", "COMPETITION"],
            "maxResults": max_results,
        },
    )


async def list_market_book(session: BetfairSession, market_ids: list[str]) -> list[dict]:
    """Актуальные цены (best back/lay) по списку рынков. Batch до ~40 market_ids за раз рекомендован Betfair."""
    if not market_ids:
        return []
    if len(market_ids) > 40:
        raise BetfairError("listMarketBook accepts at most 40 market ids per request")
    return await _rpc_call(
        session,
        "listMarketBook",
        {
            "marketIds": market_ids,
            "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
        },
    )
