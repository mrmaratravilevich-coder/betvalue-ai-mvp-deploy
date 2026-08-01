"""
Ручной запуск загрузки матчей, коэффициентов, прогнозов и поиска EV —
пока не подключён Celery beat.

    python -m app.cli sync-football-data
    python -m app.cli sync-football-history YYYY-MM-DD YYYY-MM-DD
    python -m app.cli sync-statsbomb
    python -m app.cli sync-all
    python -m app.cli predict
    python -m app.cli backtest-football LEAGUE_ID [MIN_TRAIN_MATCHES]
    python -m app.cli backtest-football-all [MIN_TRAIN_MATCHES]
    python -m app.cli compare-football-windows [MIN_TRAIN_MATCHES]
    python -m app.cli compare-football-elo [MIN_TRAIN_MATCHES]
    python -m app.cli compare-football-dixon-coles [MIN_TRAIN_MATCHES]
    python -m app.cli list-betfair-competitions
    python -m app.cli sync-odds
    python -m app.cli find-ev
"""
import asyncio
import sys
from datetime import date

from app.db.session import AsyncSessionLocal
from app.services import backtest, ev_generation, match_ingestion, odds_ingestion, prediction_engine
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


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Некорректная дата {value!r}; ожидается YYYY-MM-DD") from exc


async def _sync_football_history(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise SystemExit("Дата начала не может быть позже даты окончания")
    async with AsyncSessionLocal() as db:
        result = await match_ingestion.sync_all_football_data_leagues(db, date_from, date_to)
        print({"processed_matches": result, "date_from": str(date_from), "date_to": str(date_to)})


async def _backtest_football(league_id: int, min_train_matches: int) -> None:
    async with AsyncSessionLocal() as db:
        report = await backtest.backtest_football_league(
            db,
            league_id,
            min_train_matches=min_train_matches,
        )
        print(report.to_dict())


async def _backtest_football_all(min_train_matches: int) -> None:
    async with AsyncSessionLocal() as db:
        reports = await backtest.backtest_all_football_leagues(
            db,
            min_train_matches=min_train_matches,
        )
        print(reports)


async def _compare_football_windows(min_train_matches: int) -> None:
    async with AsyncSessionLocal() as db:
        reports = await backtest.compare_football_history_windows(
            db,
            min_train_matches=min_train_matches,
        )
        print(reports)


async def _compare_football_elo(min_train_matches: int) -> None:
    async with AsyncSessionLocal() as db:
        reports = await backtest.compare_football_elo_weights(
            db,
            min_train_matches=min_train_matches,
        )
        print(reports)


async def _compare_football_dixon_coles(min_train_matches: int) -> None:
    async with AsyncSessionLocal() as db:
        reports = await backtest.compare_football_dixon_coles(
            db,
            min_train_matches=min_train_matches,
        )
        print(reports)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    command = sys.argv[1]
    if command == "sync-football-data":
        asyncio.run(_run(match_ingestion.sync_all_football_data_leagues))
    elif command == "sync-football-history":
        if len(sys.argv) != 4:
            raise SystemExit("Использование: sync-football-history YYYY-MM-DD YYYY-MM-DD")
        asyncio.run(_sync_football_history(_parse_date(sys.argv[2]), _parse_date(sys.argv[3])))
    elif command == "sync-hockey":
        asyncio.run(_run(match_ingestion.sync_api_hockey_date))
    elif command == "sync-basketball":
        asyncio.run(_run(match_ingestion.sync_api_basketball_date))
    elif command == "sync-statsbomb":
        asyncio.run(_run(match_ingestion.sync_all_statsbomb_leagues))
    elif command == "sync-all":
        asyncio.run(_run(match_ingestion.run_daily_match_update))
    elif command == "predict":
        asyncio.run(_run(prediction_engine.generate_predictions_all_leagues))
    elif command == "backtest-football":
        if len(sys.argv) not in (3, 4):
            raise SystemExit("Использование: backtest-football LEAGUE_ID [MIN_TRAIN_MATCHES]")
        minimum = int(sys.argv[3]) if len(sys.argv) == 4 else 100
        asyncio.run(_backtest_football(int(sys.argv[2]), minimum))
    elif command == "backtest-football-all":
        if len(sys.argv) not in (2, 3):
            raise SystemExit("Использование: backtest-football-all [MIN_TRAIN_MATCHES]")
        minimum = int(sys.argv[2]) if len(sys.argv) == 3 else 100
        asyncio.run(_backtest_football_all(minimum))
    elif command == "compare-football-windows":
        if len(sys.argv) not in (2, 3):
            raise SystemExit("Использование: compare-football-windows [MIN_TRAIN_MATCHES]")
        minimum = int(sys.argv[2]) if len(sys.argv) == 3 else 100
        asyncio.run(_compare_football_windows(minimum))
    elif command == "compare-football-elo":
        if len(sys.argv) not in (2, 3):
            raise SystemExit("Использование: compare-football-elo [MIN_TRAIN_MATCHES]")
        minimum = int(sys.argv[2]) if len(sys.argv) == 3 else 100
        asyncio.run(_compare_football_elo(minimum))
    elif command == "compare-football-dixon-coles":
        if len(sys.argv) not in (2, 3):
            raise SystemExit("Использование: compare-football-dixon-coles [MIN_TRAIN_MATCHES]")
        minimum = int(sys.argv[2]) if len(sys.argv) == 3 else 100
        asyncio.run(_compare_football_dixon_coles(minimum))
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
