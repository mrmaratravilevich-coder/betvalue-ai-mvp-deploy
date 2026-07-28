"""
Загрузка матчей из открытых источников и апсерт в БД.

  - football_data.py  -> актуальные расписания/результаты (Match, Team, League)
  - statsbomb.py       -> детальная статистика по событиям (MatchTeamStat: xG, удары...)
                          для тех матчей, что покрыты открытым датасетом.

Вызывается из Celery-задачи ежедневного цикла в 06:00 ("Обновление базы"),
см. app/worker (следующий этап) — здесь только сама логика синка.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.leagues import SUPPORTED_LEAGUES, LeagueConfig
from app.models.enums import MatchStatus
from app.models.match import Match, MatchTeamStat
from app.models.team import League, Sport, Team
from app.services.sources import api_hockey, football_data

logger = logging.getLogger(__name__)

FOOTBALL_DATA_STATUS_MAP = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.LIVE,
    "PAUSED": MatchStatus.LIVE,
    "FINISHED": MatchStatus.FINISHED,
    "POSTPONED": MatchStatus.POSTPONED,
    "SUSPENDED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
    "AWARDED": MatchStatus.FINISHED,
}

API_HOCKEY_STATUS_MAP = {
    "NS": MatchStatus.SCHEDULED,
    "PST": MatchStatus.POSTPONED,
    "CANC": MatchStatus.CANCELLED,
    "LIVE": MatchStatus.LIVE,
    "P1": MatchStatus.LIVE,
    "P2": MatchStatus.LIVE,
    "P3": MatchStatus.LIVE,
    "OT": MatchStatus.LIVE,
    "BT": MatchStatus.LIVE,
    "FT": MatchStatus.FINISHED,
    "AOT": MatchStatus.FINISHED,
    "AP": MatchStatus.FINISHED,
}


# ---------------------------------------------------------------------------
# Базовые upsert-функции
# ---------------------------------------------------------------------------

async def get_or_create_sport(db: AsyncSession, code: str, name: str) -> Sport:
    result = await db.execute(select(Sport).where(Sport.code == code))
    sport = result.scalar_one_or_none()
    if sport is None:
        sport = Sport(code=code, name=name)
        db.add(sport)
        await db.flush()
    return sport


async def get_or_create_league(
    db: AsyncSession, sport: Sport, name: str, country: str | None, source: str, external_id: str | int
) -> League:
    result = await db.execute(
        select(League).where(League.external_ids.contains({source: external_id}))
    )
    league = result.scalar_one_or_none()
    if league is None:
        league = League(sport_id=sport.id, name=name, country=country, external_ids={source: external_id})
        db.add(league)
        await db.flush()
    else:
        league.name = name
        league.country = country or league.country
    return league


async def get_or_create_team(
    db: AsyncSession, league: League | None, name: str, source: str, external_id: str | int
) -> Team:
    result = await db.execute(select(Team).where(Team.external_ids.contains({source: external_id})))
    team = result.scalar_one_or_none()
    if team is None:
        team = Team(
            league_id=league.id if league else None,
            name=name,
            external_ids={source: external_id},
        )
        db.add(team)
        await db.flush()
    else:
        team.name = name
        if league is not None:
            team.league_id = league.id
    return team


async def upsert_match(
    db: AsyncSession,
    league: League,
    home_team: Team,
    away_team: Team,
    *,
    kickoff_at: datetime,
    status: MatchStatus,
    season: str | None,
    round_: str | None,
    home_score: int | None,
    away_score: int | None,
    source: str,
    external_id: str,
) -> Match:
    result = await db.execute(
        select(Match).where(Match.source == source, Match.external_id == external_id)
    )
    match = result.scalar_one_or_none()
    if match is None:
        match = Match(
            league_id=league.id,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            kickoff_at=kickoff_at,
            status=status,
            season=season,
            round=round_,
            home_score=home_score,
            away_score=away_score,
            source=source,
            external_id=external_id,
        )
        db.add(match)
    else:
        match.status = status
        match.home_score = home_score
        match.away_score = away_score
        match.round = round_ or match.round
    await db.flush()
    return match


# ---------------------------------------------------------------------------
# football-data.org: расписания и результаты
# ---------------------------------------------------------------------------

SOURCE_FOOTBALL_DATA = "football_data"


async def sync_football_data_league(
    db: AsyncSession,
    league_config: LeagueConfig,
    date_from: date | None = None,
    date_to: date | None = None,
) -> int:
    """Синхронизирует один турнир из football-data.org. Возвращает число обработанных матчей."""
    if not league_config.football_data_code:
        return 0

    sport = await get_or_create_sport(db, code="football", name="Футбол")
    raw_matches = await football_data.fetch_competition_matches(
        league_config.football_data_code, date_from=date_from, date_to=date_to
    )

    processed = 0
    for raw in raw_matches:
        competition = raw["competition"]
        league = await get_or_create_league(
            db,
            sport=sport,
            name=competition["name"],
            country=raw.get("area", {}).get("name"),
            source=SOURCE_FOOTBALL_DATA,
            external_id=competition["id"],
        )

        home_raw, away_raw = raw["homeTeam"], raw["awayTeam"]
        # У части "будущих" матчей id/name команды могут отсутствовать (плей-офф TBD)
        if home_raw.get("id") is None or away_raw.get("id") is None:
            continue

        home_team = await get_or_create_team(
            db, league, home_raw["name"], SOURCE_FOOTBALL_DATA, home_raw["id"]
        )
        away_team = await get_or_create_team(
            db, league, away_raw["name"], SOURCE_FOOTBALL_DATA, away_raw["id"]
        )

        score = raw.get("score", {}).get("fullTime", {}) or {}
        kickoff_at = datetime.fromisoformat(raw["utcDate"].replace("Z", "+00:00")).astimezone(timezone.utc)

        await upsert_match(
            db,
            league=league,
            home_team=home_team,
            away_team=away_team,
            kickoff_at=kickoff_at,
            status=FOOTBALL_DATA_STATUS_MAP.get(raw["status"], MatchStatus.SCHEDULED),
            season=str(raw.get("season", {}).get("id")) if raw.get("season") else None,
            round_=str(raw.get("matchday")) if raw.get("matchday") is not None else None,
            home_score=score.get("home"),
            away_score=score.get("away"),
            source=SOURCE_FOOTBALL_DATA,
            external_id=str(raw["id"]),
        )
        processed += 1

    await db.commit()
    logger.info("football-data.org: %s — обработано %s матчей", league_config.football_data_code, processed)
    return processed


async def sync_all_football_data_leagues(
    db: AsyncSession, date_from: date | None = None, date_to: date | None = None
) -> int:
    total = 0
    for league_config in SUPPORTED_LEAGUES:
        if league_config.football_data_code:
            total += await sync_football_data_league(db, league_config, date_from, date_to)
    return total


# ---------------------------------------------------------------------------
# API-SPORTS Hockey: current schedule and results
# ---------------------------------------------------------------------------

SOURCE_API_HOCKEY = "api_sports_hockey"


def normalize_hockey_game(raw: dict) -> dict:
    """Normalize one API-SPORTS game while keeping provider details out of DB models."""
    league = raw.get("league") or {}
    country = raw.get("country") or {}
    teams = raw.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    status_raw = raw.get("status") or {}
    scores = raw.get("scores") or {}
    timestamp = raw.get("timestamp")
    kickoff = (
        datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        if timestamp is not None
        else datetime.fromisoformat(str(raw["date"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    )
    short_status = status_raw.get("short") if isinstance(status_raw, dict) else str(status_raw)
    country_name = country.get("name") if isinstance(country, dict) else str(country)
    return {
        "external_id": str(raw["id"]),
        "kickoff_at": kickoff,
        "status": API_HOCKEY_STATUS_MAP.get(short_status, MatchStatus.SCHEDULED),
        "league_id": league["id"],
        "league_name": league["name"],
        "country": country_name,
        "season": str(league.get("season")) if league.get("season") is not None else None,
        "round": str(raw.get("week")) if raw.get("week") is not None else None,
        "home_id": home["id"],
        "home_name": home["name"],
        "away_id": away["id"],
        "away_name": away["name"],
        "home_score": scores.get("home"),
        "away_score": scores.get("away"),
    }


async def sync_api_hockey_date(db: AsyncSession, game_date: date | None = None) -> int:
    game_date = game_date or date.today()
    games = await api_hockey.fetch_games(game_date)
    if not games:
        logger.info("API-SPORTS Hockey: %s — матчей нет", game_date)
        return 0

    sport = await get_or_create_sport(db, code="hockey", name="Хоккей")
    processed = 0
    for raw in games:
        try:
            game = normalize_hockey_game(raw)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("API-SPORTS Hockey: пропущена некорректная запись: %s", exc)
            continue
        league = await get_or_create_league(
            db, sport, game["league_name"], game["country"], SOURCE_API_HOCKEY, game["league_id"]
        )
        home = await get_or_create_team(db, league, game["home_name"], SOURCE_API_HOCKEY, game["home_id"])
        away = await get_or_create_team(db, league, game["away_name"], SOURCE_API_HOCKEY, game["away_id"])
        await upsert_match(
            db,
            league,
            home,
            away,
            kickoff_at=game["kickoff_at"],
            status=game["status"],
            season=game["season"],
            round_=game["round"],
            home_score=game["home_score"],
            away_score=game["away_score"],
            source=SOURCE_API_HOCKEY,
            external_id=game["external_id"],
        )
        processed += 1
    await db.commit()
    logger.info("API-SPORTS Hockey: %s — обработано %s матчей", game_date, processed)
    return processed


# ---------------------------------------------------------------------------
# StatsBomb Open Data: детальная статистика (xG, удары, владение...)
# ---------------------------------------------------------------------------

SOURCE_STATSBOMB = "statsbomb"


async def sync_statsbomb_league(db: AsyncSession, league_config: LeagueConfig) -> int:
    """
    Синхронизирует матчи + агрегированную статистику из StatsBomb Open Data.
    Используется как источник признаков для обучения модели, а не расписания.
    """
    if league_config.statsbomb_competition_id is None or league_config.statsbomb_season_id is None:
        return 0
    from app.services.sources import statsbomb

    sport = await get_or_create_sport(db, code="football", name="Футбол")
    league = await get_or_create_league(
        db,
        sport=sport,
        name=league_config.name,
        country=league_config.country,
        source=SOURCE_STATSBOMB,
        external_id=league_config.statsbomb_competition_id,
    )

    matches_df = await statsbomb.fetch_matches(
        league_config.statsbomb_competition_id, league_config.statsbomb_season_id
    )

    processed = 0
    for _, row in matches_df.iterrows():
        home_team = await get_or_create_team(
            db, league, row["home_team"], SOURCE_STATSBOMB, row["home_team_id"]
        )
        away_team = await get_or_create_team(
            db, league, row["away_team"], SOURCE_STATSBOMB, row["away_team_id"]
        )

        kickoff_at = pd_timestamp_to_utc(row.get("match_date"), row.get("kick_off"))

        match = await upsert_match(
            db,
            league=league,
            home_team=home_team,
            away_team=away_team,
            kickoff_at=kickoff_at,
            status=MatchStatus.FINISHED,
            season=str(row.get("season_id")),
            round_=str(row.get("match_week")) if row.get("match_week") is not None else None,
            home_score=int(row["home_score"]) if row.get("home_score") is not None else None,
            away_score=int(row["away_score"]) if row.get("away_score") is not None else None,
            source=SOURCE_STATSBOMB,
            external_id=str(row["match_id"]),
        )

        await _sync_statsbomb_team_stats(db, match, home_team, away_team)
        processed += 1

    await db.commit()
    logger.info("StatsBomb: %s/%s — обработано %s матчей", league_config.statsbomb_competition_id,
                league_config.statsbomb_season_id, processed)
    return processed


async def _sync_statsbomb_team_stats(db: AsyncSession, match: Match, home_team: Team, away_team: Team) -> None:
    """Агрегирует события матча (shots, xG) по командам в MatchTeamStat."""
    from app.services.sources import statsbomb

    try:
        events = await statsbomb.fetch_team_match_stats(int(match.external_id))
    except statsbomb.StatsBombError as exc:
        logger.warning("Не удалось получить события матча %s: %s", match.external_id, exc)
        return

    if events.empty or "type" not in events.columns:
        return

    shots = events[events["type"] == "Shot"]
    for team_obj, is_home in ((home_team, True), (away_team, False)):
        team_shots = shots[shots["team"] == team_obj.name]
        xg_sum = float(team_shots["shot_statsbomb_xg"].sum()) if "shot_statsbomb_xg" in team_shots else None
        on_target = None
        if "shot_outcome" in team_shots.columns:
            on_target = int(team_shots["shot_outcome"].isin(["Goal", "Saved"]).sum())

        result = await db.execute(
            select(MatchTeamStat).where(
                MatchTeamStat.match_id == match.id, MatchTeamStat.team_id == team_obj.id
            )
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = MatchTeamStat(match_id=match.id, team_id=team_obj.id, is_home=is_home)
            db.add(stat)
        stat.shots = int(len(team_shots))
        stat.shots_on_target = on_target
        stat.xg = xg_sum
    await db.flush()


def pd_timestamp_to_utc(match_date, kick_off) -> datetime:
    """StatsBomb отдаёт match_date ('YYYY-MM-DD') и kick_off ('HH:MM:SS.fff') отдельно."""
    date_str = str(match_date) if match_date is not None else "1970-01-01"
    time_str = str(kick_off).split(".")[0] if kick_off else "00:00:00"
    return datetime.fromisoformat(f"{date_str}T{time_str}").replace(tzinfo=timezone.utc)


async def sync_all_statsbomb_leagues(db: AsyncSession) -> int:
    total = 0
    for league_config in SUPPORTED_LEAGUES:
        if league_config.statsbomb_competition_id is not None:
            total += await sync_statsbomb_league(db, league_config)
    return total


# ---------------------------------------------------------------------------
# Точка входа для ежедневного цикла (06:00 "Обновление базы")
# ---------------------------------------------------------------------------

async def run_daily_match_update(db: AsyncSession) -> dict[str, int]:
    fd_count = await sync_all_football_data_leagues(db)
    hockey_count = await sync_api_hockey_date(db)
    sb_count = await sync_all_statsbomb_leagues(db)
    return {
        "football_data_matches": fd_count,
        "api_hockey_matches": hockey_count,
        "statsbomb_matches": sb_count,
    }


async def sync_upcoming_match_window(
    db: AsyncSession,
    *,
    today: date | None = None,
    football_days: int = 30,
    hockey_days: int = 3,
) -> dict[str, int]:
    """
    Lightweight production sync for the public API.

    Unlike the full daily pipeline, this only loads the near-term schedule and
    deliberately skips the large StatsBomb historical dataset. Provider or
    competition failures are isolated so one unavailable source cannot leave
    the other sport empty.
    """
    current_day = today or date.today()
    result = {
        "football_data_matches": 0,
        "api_hockey_matches": 0,
        "errors": 0,
    }

    for league_config in SUPPORTED_LEAGUES:
        if not league_config.football_data_code:
            continue
        try:
            result["football_data_matches"] += await sync_football_data_league(
                db,
                league_config,
                date_from=current_day,
                date_to=current_day + timedelta(days=football_days),
            )
        except Exception:  # noqa: BLE001 - isolate provider/competition failures
            await db.rollback()
            result["errors"] += 1
            logger.exception(
                "Upcoming sync: football-data.org %s failed",
                league_config.football_data_code,
            )

    for offset in range(hockey_days + 1):
        game_date = current_day + timedelta(days=offset)
        try:
            result["api_hockey_matches"] += await sync_api_hockey_date(db, game_date)
        except Exception:  # noqa: BLE001 - continue with the remaining dates
            await db.rollback()
            result["errors"] += 1
            logger.exception("Upcoming sync: API-SPORTS Hockey %s failed", game_date)

    logger.info("Upcoming match window sync finished: %s", result)
    return result
