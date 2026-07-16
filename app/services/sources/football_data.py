"""
Тонкий HTTP-клиент football-data.org v4.
Только сеть + разбор JSON, без записи в БД (это делает match_ingestion.py).

Схема ответа подтверждена официальной документацией
(https://docs.football-data.org/general/v4/match.html):

{
  "matches": [
    {
      "id": 330299,
      "utcDate": "2022-02-27T16:05:00Z",
      "status": "FINISHED",
      "matchday": 26,
      "competition": {"id": 2015, "name": "Ligue 1", "code": "FL1"},
      "season": {"id": 746, ...},
      "homeTeam": {"id": 531, "name": "ES Troyes AC"},
      "awayTeam": {"id": ..., "name": ...},
      "score": {"fullTime": {"home": 1, "away": 2}, ...}
    },
    ...
  ]
}
"""
from datetime import date

import httpx

from app.core.config import settings

BASE_URL = settings.FOOTBALL_DATA_BASE_URL

# Статусы football-data.org, которые считаем завершённым матчем
FINISHED_STATUSES = {"FINISHED"}


class FootballDataError(RuntimeError):
    pass


async def fetch_competition_matches(
    competition_code: str,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
) -> list[dict]:
    """
    GET /v4/competitions/{code}/matches

    Без API-ключа (settings.FOOTBALL_DATA_API_KEY) запрос не выполняется —
    бесплатный ключ можно получить на football-data.org/client/register.
    """
    if not settings.FOOTBALL_DATA_API_KEY:
        raise FootballDataError(
            "FOOTBALL_DATA_API_KEY не задан в .env — получите бесплатный ключ "
            "на https://www.football-data.org/client/register"
        )

    params: dict[str, str] = {}
    if date_from:
        params["dateFrom"] = date_from.isoformat()
    if date_to:
        params["dateTo"] = date_to.isoformat()
    if status:
        params["status"] = status

    headers = {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}
    url = f"{BASE_URL}/competitions/{competition_code}/matches"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code == 429:
        raise FootballDataError("football-data.org: превышен лимит запросов (rate limit)")
    if response.status_code == 403:
        raise FootballDataError(
            f"football-data.org: доступ запрещён для {competition_code} "
            "(проверьте тариф ключа — часть турниров доступна только платно)"
        )
    response.raise_for_status()

    return response.json().get("matches", [])
