"""
Ручной запуск загрузки матчей, коэффициентов, прогнозов и поиска EV —
пока не подключён Celery beat.

    python -m app.cli sync-football-data
    python -m app.cli sync-statsbomb
    python -m app.cli sync-all
    python -m app.cli predict
    python -m app.cli list-betfair-competitions
    python -m app.cli sync-odds
    python -m app.cli find-ev
"""
import asyncio
import sys

from app.db.session import AsyncSessionLocal
from app.services import ev_generation, match_ingestion, odds_ingestion, prediction_engine
from app.services.sources import betfair
from app.services import telegram_bot


async def _run(coro_factory) -> None:
    async with AsyncSessionLocal() as db:
        result = await coro_factory(db)
        print(result)


async def _list_betfair_competitions() -> None:
    session = await betfair.login()
    competitions = await betfair.list_competitions(session)
    print(f"Найдено турниров с активными рынками: {len(competitions)}\n")
    for entry in sorted(competitions, key=lambda c: c["competition"]["name"]):
        comp = entry["competition"]
        print(f"  id={comp['id']:<10} {comp['name']}  (рынков: {entry.get('marketCount', '?')})")
    print(
        "\nСкопируйте нужный id в betfair_competition_id соответствующей "
        "LeagueConfig в app/core/leagues.py"
    )


async def _telegram_check() -> None:
    bot = await telegram_bot.get_me()
    print({"ok": True, "id": bot["id"], "username": bot.get("username")})


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    command = sys.argv[1]
    if command == "sync-football-data":
        asyncio.run(_run(match_ingestion.sync_all_football_data_leagues))
    elif command == "sync-hockey":
        asyncio.run(_run(match_ingestion.sync_api_hockey_date))
    elif command == "sync-statsbomb":
        asyncio.run(_run(match_ingestion.sync_all_statsbomb_leagues))
    elif command == "sync-all":
        asyncio.run(_run(match_ingestion.run_daily_match_update))
    elif command == "predict":
        asyncio.run(_run(prediction_engine.generate_predictions_all_leagues))
    elif command == "list-betfair-competitions":
        asyncio.run(_list_betfair_competitions())
    elif command == "sync-odds":
        asyncio.run(_run(odds_ingestion.sync_all_betfair_leagues))
    elif command == "find-ev":
        asyncio.run(_run(ev_generation.generate_ev_bets_all))
    elif command == "telegram-check":
        asyncio.run(_telegram_check())
    elif command == "telegram-poll":
        asyncio.run(telegram_bot.poll())
    else:
        print(f"Неизвестная команда: {command}\n\n{__doc__}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
