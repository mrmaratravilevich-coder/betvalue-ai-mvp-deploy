"""Leakage-safe chronological evaluation for the football Poisson model."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from math import exp, log

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MatchStatus
from app.models.match import Match
from app.models.team import League, Sport
from app.services.models.poisson_model import predict_match


@dataclass(frozen=True)
class HistoricalMatch:
    kickoff_at: datetime
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int


@dataclass(frozen=True)
class BacktestPrediction:
    kickoff_at: datetime
    training_matches: int
    actual: str
    predicted: str
    home_probability: float
    draw_probability: float
    away_probability: float
    baseline_home_probability: float
    baseline_draw_probability: float
    baseline_away_probability: float


@dataclass(frozen=True)
class BacktestReport:
    evaluated_matches: int
    skipped_warmup: int
    accuracy: float
    brier_score: float
    log_loss: float
    baseline_brier_score: float
    baseline_log_loss: float
    calibration_error: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _SideStats:
    games: int = 0
    goals_for: int = 0
    goals_against: int = 0


def _outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


def _elo_expected_home(home_rating: float, away_rating: float, home_advantage: float = 65.0) -> float:
    return 1 / (1 + 10 ** (-(home_rating + home_advantage - away_rating) / 400))


def _update_elo(
    home_rating: float,
    away_rating: float,
    *,
    home_score: int,
    away_score: int,
    k_factor: float = 20.0,
    home_advantage: float = 65.0,
) -> tuple[float, float]:
    expected_home = _elo_expected_home(home_rating, away_rating, home_advantage)
    actual_home = 1.0 if home_score > away_score else 0.0 if home_score < away_score else 0.5
    change = k_factor * (actual_home - expected_home)
    return home_rating + change, away_rating - change


def evaluate_chronologically(
    matches: list[HistoricalMatch],
    *,
    min_train_matches: int = 100,
    min_team_games: int = 3,
    history_window: int | None = None,
    elo_weight: float = 0.0,
    elo_k_factor: float = 20.0,
    elo_home_advantage: float = 65.0,
    dixon_coles_rho: float = 0.0,
) -> list[BacktestPrediction]:
    """Predict every match before adding its result to the training state."""
    if history_window is not None and history_window < min_train_matches:
        raise ValueError("history_window must be at least min_train_matches")

    ordered = sorted(matches, key=lambda match: match.kickoff_at)
    recent_history: deque[HistoricalMatch] = deque()
    home_stats: dict[int, _SideStats] = {}
    away_stats: dict[int, _SideStats] = {}
    total_home_goals = 0
    total_away_goals = 0
    history_count = 0
    outcome_counts = {"home": 0, "draw": 0, "away": 0}
    elo_ratings: dict[int, float] = {}
    predictions: list[BacktestPrediction] = []

    for match in ordered:
        if history_count >= min_train_matches and total_home_goals > 0 and total_away_goals > 0:
            league_home = total_home_goals / history_count
            league_away = total_away_goals / history_count
            home = home_stats.get(match.home_team_id, _SideStats())
            away = away_stats.get(match.away_team_id, _SideStats())

            home_attack = home.goals_for / home.games / league_home if home.games >= min_team_games else 1.0
            home_defense = home.goals_against / home.games / league_away if home.games >= min_team_games else 1.0
            away_attack = away.goals_for / away.games / league_away if away.games >= min_team_games else 1.0
            away_defense = away.goals_against / away.games / league_home if away.games >= min_team_games else 1.0
            expected_home_goals = home_attack * away_defense * league_home
            expected_away_goals = away_attack * home_defense * league_away
            if elo_weight:
                elo_difference = (
                    elo_ratings.get(match.home_team_id, 1500.0)
                    - elo_ratings.get(match.away_team_id, 1500.0)
                )
                elo_multiplier = exp(elo_weight * elo_difference / 400)
                expected_home_goals *= elo_multiplier
                expected_away_goals /= elo_multiplier
            probabilities = predict_match(
                expected_home_goals,
                expected_away_goals,
                dixon_coles_rho=dixon_coles_rho,
            )
            probability_by_outcome = {
                "home": probabilities.home_win,
                "draw": probabilities.draw,
                "away": probabilities.away_win,
            }
            baseline_total = history_count + 3
            predictions.append(
                BacktestPrediction(
                    kickoff_at=match.kickoff_at,
                    training_matches=history_count,
                    actual=_outcome(match.home_score, match.away_score),
                    predicted=max(probability_by_outcome, key=probability_by_outcome.get),
                    home_probability=probabilities.home_win,
                    draw_probability=probabilities.draw,
                    away_probability=probabilities.away_win,
                    baseline_home_probability=(outcome_counts["home"] + 1) / baseline_total,
                    baseline_draw_probability=(outcome_counts["draw"] + 1) / baseline_total,
                    baseline_away_probability=(outcome_counts["away"] + 1) / baseline_total,
                )
            )

        home = home_stats.setdefault(match.home_team_id, _SideStats())
        home.games += 1
        home.goals_for += match.home_score
        home.goals_against += match.away_score
        away = away_stats.setdefault(match.away_team_id, _SideStats())
        away.games += 1
        away.goals_for += match.away_score
        away.goals_against += match.home_score
        total_home_goals += match.home_score
        total_away_goals += match.away_score
        outcome_counts[_outcome(match.home_score, match.away_score)] += 1
        history_count += 1
        recent_history.append(match)

        current_home_elo = elo_ratings.get(match.home_team_id, 1500.0)
        current_away_elo = elo_ratings.get(match.away_team_id, 1500.0)
        new_home_elo, new_away_elo = _update_elo(
            current_home_elo,
            current_away_elo,
            home_score=match.home_score,
            away_score=match.away_score,
            k_factor=elo_k_factor,
            home_advantage=elo_home_advantage,
        )
        elo_ratings[match.home_team_id] = new_home_elo
        elo_ratings[match.away_team_id] = new_away_elo

        if history_window is not None and history_count > history_window:
            expired = recent_history.popleft()
            expired_home = home_stats[expired.home_team_id]
            expired_home.games -= 1
            expired_home.goals_for -= expired.home_score
            expired_home.goals_against -= expired.away_score
            expired_away = away_stats[expired.away_team_id]
            expired_away.games -= 1
            expired_away.goals_for -= expired.away_score
            expired_away.goals_against -= expired.home_score
            total_home_goals -= expired.home_score
            total_away_goals -= expired.away_score
            outcome_counts[_outcome(expired.home_score, expired.away_score)] -= 1
            history_count -= 1

    return predictions


def summarize_backtest(
    predictions: list[BacktestPrediction],
    *,
    skipped_warmup: int,
    calibration_bins: int = 10,
) -> BacktestReport:
    if not predictions:
        raise ValueError("Недостаточно матчей для backtest после периода прогрева")

    outcomes = ("home", "draw", "away")
    brier = log_loss = 0.0
    baseline_brier = baseline_log_loss = 0.0
    correct = 0
    calibration: list[list[float]] = [[] for _ in range(calibration_bins)]

    for prediction in predictions:
        probabilities = {
            "home": prediction.home_probability,
            "draw": prediction.draw_probability,
            "away": prediction.away_probability,
        }
        baseline = {
            "home": prediction.baseline_home_probability,
            "draw": prediction.baseline_draw_probability,
            "away": prediction.baseline_away_probability,
        }
        brier += sum(
            (probabilities[outcome] - float(prediction.actual == outcome)) ** 2
            for outcome in outcomes
        )
        log_loss -= log(max(probabilities[prediction.actual], 1e-15))
        baseline_brier += sum(
            (baseline[outcome] - float(prediction.actual == outcome)) ** 2
            for outcome in outcomes
        )
        baseline_log_loss -= log(max(baseline[prediction.actual], 1e-15))
        correct += int(prediction.predicted == prediction.actual)
        confidence = max(probabilities.values())
        bin_index = min(int(confidence * calibration_bins), calibration_bins - 1)
        calibration[bin_index].append(float(prediction.predicted == prediction.actual) - confidence)

    total = len(predictions)
    calibration_error = sum(
        abs(sum(bucket) / len(bucket)) * len(bucket) / total
        for bucket in calibration
        if bucket
    )
    return BacktestReport(
        evaluated_matches=total,
        skipped_warmup=skipped_warmup,
        accuracy=round(correct / total, 6),
        brier_score=round(brier / total, 6),
        log_loss=round(log_loss / total, 6),
        baseline_brier_score=round(baseline_brier / total, 6),
        baseline_log_loss=round(baseline_log_loss / total, 6),
        calibration_error=round(calibration_error, 6),
    )


async def backtest_football_league(
    db: AsyncSession,
    league_id: int,
    *,
    min_train_matches: int = 100,
    history_window: int | None = None,
    elo_weight: float = 0.0,
    dixon_coles_rho: float = 0.0,
) -> BacktestReport:
    rows = (
        await db.execute(
            select(Match)
            .join(League)
            .join(Sport)
            .where(
                Match.league_id == league_id,
                Sport.code == "football",
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
        for match in rows
    ]
    predictions = evaluate_chronologically(
        historical,
        min_train_matches=min_train_matches,
        history_window=history_window,
        elo_weight=elo_weight,
        dixon_coles_rho=dixon_coles_rho,
    )
    return summarize_backtest(predictions, skipped_warmup=min(min_train_matches, len(historical)))


async def backtest_all_football_leagues(
    db: AsyncSession,
    *,
    min_train_matches: int = 100,
) -> dict[int, dict]:
    """Run the chronological backtest for every football league with enough data."""
    league_ids = (
        await db.execute(
            select(League.id)
            .join(Sport)
            .where(Sport.code == "football")
            .order_by(League.id)
        )
    ).scalars().all()

    reports: dict[int, dict] = {}
    for league_id in league_ids:
        try:
            report = await backtest_football_league(
                db,
                league_id,
                min_train_matches=min_train_matches,
            )
        except ValueError:
            continue
        reports[league_id] = report.to_dict()
    return reports


async def compare_football_history_windows(
    db: AsyncSession,
    *,
    min_train_matches: int = 100,
    windows: tuple[int | None, ...] = (None, 120, 200),
) -> dict[int, dict[str, dict]]:
    """Compare full-history and rolling-history variants on every football league."""
    league_ids = (
        await db.execute(
            select(League.id)
            .join(Sport)
            .where(Sport.code == "football")
            .order_by(League.id)
        )
    ).scalars().all()

    comparison: dict[int, dict[str, dict]] = {}
    for league_id in league_ids:
        variants: dict[str, dict] = {}
        for window in windows:
            try:
                report = await backtest_football_league(
                    db,
                    league_id,
                    min_train_matches=min_train_matches,
                    history_window=window,
                )
            except ValueError:
                continue
            variants["full" if window is None else f"window_{window}"] = report.to_dict()
        if variants:
            comparison[league_id] = variants
    return comparison


async def compare_football_elo_weights(
    db: AsyncSession,
    *,
    min_train_matches: int = 100,
    weights: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3),
) -> dict[int, dict[str, dict]]:
    """Compare the Poisson baseline with leakage-safe chronological Elo adjustments."""
    league_ids = (
        await db.execute(
            select(League.id)
            .join(Sport)
            .where(Sport.code == "football")
            .order_by(League.id)
        )
    ).scalars().all()

    comparison: dict[int, dict[str, dict]] = {}
    for league_id in league_ids:
        variants: dict[str, dict] = {}
        for weight in weights:
            try:
                report = await backtest_football_league(
                    db,
                    league_id,
                    min_train_matches=min_train_matches,
                    elo_weight=weight,
                )
            except ValueError:
                continue
            variants["poisson" if weight == 0 else f"elo_{weight:g}"] = report.to_dict()
        if variants:
            comparison[league_id] = variants
    return comparison


async def compare_football_dixon_coles(
    db: AsyncSession,
    *,
    min_train_matches: int = 100,
    rho_values: tuple[float, ...] = (0.0, -0.15, -0.1, -0.05, 0.05),
) -> dict[int, dict[str, dict]]:
    """Compare Poisson with low-score Dixon-Coles corrections by league."""
    league_ids = (
        await db.execute(
            select(League.id)
            .join(Sport)
            .where(Sport.code == "football")
            .order_by(League.id)
        )
    ).scalars().all()

    comparison: dict[int, dict[str, dict]] = {}
    for league_id in league_ids:
        variants: dict[str, dict] = {}
        for rho in rho_values:
            try:
                report = await backtest_football_league(
                    db,
                    league_id,
                    min_train_matches=min_train_matches,
                    dixon_coles_rho=rho,
                )
            except ValueError:
                continue
            variants["poisson" if rho == 0 else f"dc_{rho:g}"] = report.to_dict()
        if variants:
            comparison[league_id] = variants
    return comparison
