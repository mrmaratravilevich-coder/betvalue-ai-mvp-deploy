"""
ML-пайплайн (пока — только Poisson-часть): считает силу атаки/обороны команд
по завершённым матчам лиги и формирует Prediction для предстоящих матчей.

XGBoost/LightGBM/логрегрессия/ансамбль (см. ТЗ, раздел "Алгоритмы") —
следующий слой поверх этого: каждая новая модель добавляет свою вероятность
в ensemble_components у уже существующих Prediction, а не заменяет Poisson.

Минимальный объём данных: раздел "Фильтры" ТЗ требует >=1000 исторических
матчей для реальной ставки — это проверяется позже, в ev_engine.passes_filters().
Здесь используется более мягкий порог (см. MIN_TEAM_GAMES) — просто чтобы не
считать прогноз по 1-2 матчам команды.
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MarketCode, MatchStatus
from app.models.match import Match
from app.models.prediction import Prediction
from app.models.team import League, Sport
from app.services.backtest import HistoricalMatch, _temperature_scale, fit_temperature_chronologically
from app.services.markets import get_or_create_market
from app.services.models.poisson_model import MatchProbabilities, predict_match

logger = logging.getLogger(__name__)

MODEL_VERSION = "poisson-v1"
DEFAULT_TOTAL_LINE = 2.5
MIN_TEAM_GAMES = 3  # ниже этого числа матчей команды используем среднюю по лиге силу
CALIBRATION_MIN_TRAIN_MATCHES = 100
CALIBRATION_MIN_PREDICTIONS = 50
CALIBRATION_TEMPERATURES = (0.7, 0.85, 1.0, 1.2, 1.4)


@dataclass
class TeamStrength:
    attack_home: float = 1.0
    defense_home: float = 1.0
    attack_away: float = 1.0
    defense_away: float = 1.0
    home_games: int = 0
    away_games: int = 0


@dataclass
class LeagueModel:
    league_avg_home_goals: float
    league_avg_away_goals: float
    team_strengths: dict[int, TeamStrength] = field(default_factory=dict)
    calibration_temperature: float = 1.0
    calibration_predictions: int = 0

    def uncertainty_for(self, home_team_id: int, away_team_id: int) -> float:
        """
        Грубая оценка неопределённости модели (0..1): чем меньше сыграно матчей
        обеими командами, тем выше значение. Используется фильтром EV
        ("высокая неопределённость модели", см. ev_engine.passes_filters).
        """
        home = self.team_strengths.get(home_team_id, TeamStrength())
        away = self.team_strengths.get(away_team_id, TeamStrength())
        games = min(home.home_games, away.away_games)
        return max(0.0, 1 - min(games, 20) / 20)


async def compute_league_model(db: AsyncSession, league_id: int) -> LeagueModel | None:
    """Считает средние по лиге и силу атаки/обороны каждой команды по завершённым матчам."""
    league_avg_stmt = select(
        func.avg(Match.home_score), func.avg(Match.away_score), func.count(Match.id)
    ).where(
        Match.league_id == league_id,
        Match.status == MatchStatus.FINISHED,
        Match.home_score.is_not(None),
        Match.away_score.is_not(None),
    )
    avg_home, avg_away, total_matches = (await db.execute(league_avg_stmt)).one()

    if not total_matches or avg_home is None or avg_away is None or float(avg_home) == 0 or float(avg_away) == 0:
        logger.info("Лига %s: недостаточно завершённых матчей для расчёта модели", league_id)
        return None

    league_avg_home_goals = float(avg_home)
    league_avg_away_goals = float(avg_away)

    home_stats_stmt = (
        select(
            Match.home_team_id,
            func.avg(Match.home_score).label("goals_for"),
            func.avg(Match.away_score).label("goals_against"),
            func.count(Match.id).label("games"),
        )
        .where(
            Match.league_id == league_id,
            Match.status == MatchStatus.FINISHED,
            Match.home_score.is_not(None),
        )
        .group_by(Match.home_team_id)
    )
    away_stats_stmt = (
        select(
            Match.away_team_id,
            func.avg(Match.away_score).label("goals_for"),
            func.avg(Match.home_score).label("goals_against"),
            func.count(Match.id).label("games"),
        )
        .where(
            Match.league_id == league_id,
            Match.status == MatchStatus.FINISHED,
            Match.away_score.is_not(None),
        )
        .group_by(Match.away_team_id)
    )

    home_rows = (await db.execute(home_stats_stmt)).all()
    away_rows = (await db.execute(away_stats_stmt)).all()

    historical_rows = (
        await db.execute(
            select(Match)
            .where(
                Match.league_id == league_id,
                Match.status == MatchStatus.FINISHED,
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
            )
            .order_by(Match.kickoff_at)
        )
    ).scalars().all()
    historical = [
        HistoricalMatch(
            kickoff_at=match.kickoff_at,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            home_score=match.home_score,
            away_score=match.away_score,
        )
        for match in historical_rows
    ]
    calibration_predictions = max(0, len(historical) - CALIBRATION_MIN_TRAIN_MATCHES)
    calibration_temperature = fit_temperature_chronologically(
        historical,
        min_train_matches=CALIBRATION_MIN_TRAIN_MATCHES,
        min_calibration_predictions=CALIBRATION_MIN_PREDICTIONS,
        candidates=CALIBRATION_TEMPERATURES,
    )

    strengths: dict[int, TeamStrength] = {}

    for team_id, goals_for, goals_against, games in home_rows:
        s = strengths.setdefault(team_id, TeamStrength())
        if games >= MIN_TEAM_GAMES:
            s.attack_home = float(goals_for) / league_avg_home_goals
            s.defense_home = float(goals_against) / league_avg_away_goals
        s.home_games = games

    for team_id, goals_for, goals_against, games in away_rows:
        s = strengths.setdefault(team_id, TeamStrength())
        if games >= MIN_TEAM_GAMES:
            s.attack_away = float(goals_for) / league_avg_away_goals
            s.defense_away = float(goals_against) / league_avg_home_goals
        s.away_games = games

    return LeagueModel(
        league_avg_home_goals=league_avg_home_goals,
        league_avg_away_goals=league_avg_away_goals,
        team_strengths=strengths,
        calibration_temperature=calibration_temperature,
        calibration_predictions=calibration_predictions,
    )


def _calibrated_match_winner(
    probabilities: MatchProbabilities,
    temperature: float,
) -> dict[str, float]:
    return _temperature_scale(
        {
            "home": probabilities.home_win,
            "draw": probabilities.draw,
            "away": probabilities.away_win,
        },
        temperature,
    )


async def _upsert_prediction(
    db: AsyncSession,
    match_id: int,
    market_id: int,
    selection: str,
    probability: float,
    ensemble_components: dict,
    uncertainty: float,
) -> None:
    result = await db.execute(
        select(Prediction).where(
            Prediction.match_id == match_id,
            Prediction.market_id == market_id,
            Prediction.selection == selection,
            Prediction.model_version == MODEL_VERSION,
        )
    )
    prediction = result.scalar_one_or_none()
    if prediction is None:
        prediction = Prediction(
            match_id=match_id,
            market_id=market_id,
            selection=selection,
            model_version=MODEL_VERSION,
        )
        db.add(prediction)
    prediction.model_probability = probability
    prediction.ensemble_components = ensemble_components
    prediction.uncertainty = uncertainty


async def generate_predictions_for_league(
    db: AsyncSession, league_id: int, total_line: float = DEFAULT_TOTAL_LINE
) -> int:
    model = await compute_league_model(db, league_id)
    if model is None:
        return 0

    markets = {
        code: await get_or_create_market(db, code)
        for code in (MarketCode.MATCH_WINNER, MarketCode.TOTAL_OVER, MarketCode.TOTAL_UNDER, MarketCode.BTTS)
    }

    upcoming = (
        await db.execute(
            select(Match).where(Match.league_id == league_id, Match.status == MatchStatus.SCHEDULED)
        )
    ).scalars().all()

    created = 0
    for match in upcoming:
        home = model.team_strengths.get(match.home_team_id, TeamStrength())
        away = model.team_strengths.get(match.away_team_id, TeamStrength())

        expected_home_goals = home.attack_home * away.defense_away * model.league_avg_home_goals
        expected_away_goals = away.attack_away * home.defense_home * model.league_avg_away_goals

        probs = predict_match(expected_home_goals, expected_away_goals, total_line=total_line)
        match_winner = _calibrated_match_winner(probs, model.calibration_temperature)
        uncertainty = model.uncertainty_for(match.home_team_id, match.away_team_id)
        ensemble = {
            "poisson": {
                "expected_home_goals": round(probs.expected_home_goals, 3),
                "expected_away_goals": round(probs.expected_away_goals, 3),
            },
            "calibration": {
                "method": "temperature",
                "temperature": round(model.calibration_temperature, 3),
                "historical_predictions": model.calibration_predictions,
            },
            # Место под будущие модели: "xgboost": {...}, "lightgbm": {...}, "logistic_regression": {...}
        }

        await _upsert_prediction(
            db, match.id, markets[MarketCode.MATCH_WINNER].id, "home", match_winner["home"], ensemble, uncertainty
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.MATCH_WINNER].id, "draw", match_winner["draw"], ensemble, uncertainty
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.MATCH_WINNER].id, "away", match_winner["away"], ensemble, uncertainty
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.TOTAL_OVER].id, f"over_{total_line}", probs.over_line, ensemble,
            uncertainty,
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.TOTAL_UNDER].id, f"under_{total_line}", probs.under_line, ensemble,
            uncertainty,
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.BTTS].id, "yes", probs.btts_yes, ensemble, uncertainty
        )
        await _upsert_prediction(
            db, match.id, markets[MarketCode.BTTS].id, "no", probs.btts_no, ensemble, uncertainty
        )
        created += 1

    await db.commit()
    logger.info("Лига %s: сформированы прогнозы для %s матчей", league_id, created)
    return created


async def generate_predictions_all_leagues(db: AsyncSession) -> dict[str, int]:
    """
    Точка входа для ежедневного цикла (08:00 "Обучение модели" / 09:00 "Поиск EV"
    в терминах ТЗ — здесь это "обучение" силы команд + расчёт вероятностей).
    """
    result: dict[str, int] = {}
    # Poisson v1 обучен только для футбольного счёта. Хоккей и баскетбол
    # показываем в расписании, но не публикуем для них футбольные вероятности.
    leagues = (
        await db.execute(
            select(League)
            .join(Sport)
            .where(Sport.code == "football")
        )
    ).scalars().all()
    for league in leagues:
        count = await generate_predictions_for_league(db, league.id)
        if count:
            result[league.name] = count
    return result
