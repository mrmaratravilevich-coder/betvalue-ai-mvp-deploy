from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MarketCode, MatchStatus
from app.models.match import Match
from app.models.odds import Market
from app.models.prediction import Prediction
from app.models.team import League
from app.schemas.model_quality import LeagueQuality, ModelQualityOut, QualityMetrics, QualityWindow
from app.services.prediction_engine import MODEL_VERSION

SELECTIONS = ("home", "draw", "away")
DEFAULT_WINDOWS = (7, 30, 90)
EPSILON = 1e-12


@dataclass(frozen=True)
class PredictionSnapshot:
    match_id: int
    league_id: int
    league_name: str
    kickoff_at: datetime
    actual: str
    probabilities: dict[str, float]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _actual_selection(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"


def rows_to_snapshots(rows: Iterable[object]) -> list[PredictionSnapshot]:
    """Collapse database rows into complete, latest pre-match 1X2 snapshots."""
    grouped: dict[tuple, dict[str, tuple[datetime, float]]] = {}
    for row in rows:
        (
            match_id,
            league_id,
            league_name,
            kickoff_at,
            home_score,
            away_score,
            selection,
            probability,
            created_at,
        ) = row
        if selection not in SELECTIONS or home_score is None or away_score is None:
            continue
        kickoff_at = _as_utc(kickoff_at)
        created_at = _as_utc(created_at)
        if created_at > kickoff_at:
            continue
        key = (match_id, league_id, league_name, kickoff_at, home_score, away_score)
        current = grouped.setdefault(key, {}).get(selection)
        if current is None or created_at > current[0]:
            grouped[key][selection] = (created_at, float(probability))

    snapshots: list[PredictionSnapshot] = []
    for key, values in grouped.items():
        if not all(selection in values for selection in SELECTIONS):
            continue
        match_id, league_id, league_name, kickoff_at, home_score, away_score = key
        probabilities = {selection: values[selection][1] for selection in SELECTIONS}
        total = sum(probabilities.values())
        if total <= 0:
            continue
        probabilities = {selection: value / total for selection, value in probabilities.items()}
        snapshots.append(
            PredictionSnapshot(
                match_id=match_id,
                league_id=league_id,
                league_name=league_name,
                kickoff_at=kickoff_at,
                actual=_actual_selection(home_score, away_score),
                probabilities=probabilities,
            )
        )
    return snapshots


def summarize_snapshots(snapshots: Iterable[PredictionSnapshot], bins: int = 10) -> QualityMetrics:
    items = list(snapshots)
    if not items:
        return QualityMetrics(evaluated_matches=0)

    correct = 0
    brier_total = 0.0
    log_loss_total = 0.0
    calibration_bins: list[list[float]] = [[] for _ in range(bins)]

    for item in items:
        predicted = max(SELECTIONS, key=lambda selection: item.probabilities[selection])
        is_correct = float(predicted == item.actual)
        correct += int(is_correct)
        brier_total += sum(
            (item.probabilities[selection] - float(selection == item.actual)) ** 2
            for selection in SELECTIONS
        )
        log_loss_total -= math.log(max(item.probabilities[item.actual], EPSILON))
        confidence = item.probabilities[predicted]
        bin_index = min(int(confidence * bins), bins - 1)
        calibration_bins[bin_index].append(confidence - is_correct)

    count = len(items)
    calibration_error = sum(
        abs(sum(values) / len(values)) * len(values) / count
        for values in calibration_bins
        if values
    )
    return QualityMetrics(
        evaluated_matches=count,
        accuracy=correct / count,
        brier_score=brier_total / count,
        log_loss=log_loss_total / count,
        calibration_error=calibration_error,
    )


def build_quality_report(
    snapshots: Iterable[PredictionSnapshot],
    *,
    now: datetime | None = None,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
) -> ModelQualityOut:
    generated_at = _as_utc(now or datetime.now(timezone.utc))
    all_snapshots = list(snapshots)
    reports: list[QualityWindow] = []
    for days in windows:
        cutoff = generated_at - timedelta(days=days)
        selected = [item for item in all_snapshots if cutoff <= _as_utc(item.kickoff_at) <= generated_at]
        leagues: list[LeagueQuality] = []
        league_keys = sorted({(item.league_id, item.league_name) for item in selected}, key=lambda item: item[1])
        for league_id, league_name in league_keys:
            metrics = summarize_snapshots(item for item in selected if item.league_id == league_id)
            leagues.append(LeagueQuality(league_id=league_id, league_name=league_name, **metrics.model_dump()))
        reports.append(
            QualityWindow(
                days=days,
                from_date=cutoff,
                to_date=generated_at,
                overall=summarize_snapshots(selected),
                leagues=leagues,
            )
        )
    return ModelQualityOut(generated_at=generated_at, model_version=MODEL_VERSION, windows=reports)


async def get_model_quality(db: AsyncSession, *, now: datetime | None = None) -> ModelQualityOut:
    generated_at = _as_utc(now or datetime.now(timezone.utc))
    cutoff = generated_at - timedelta(days=max(DEFAULT_WINDOWS))
    stmt = (
        select(
            Match.id,
            League.id,
            League.name,
            Match.kickoff_at,
            Match.home_score,
            Match.away_score,
            Prediction.selection,
            Prediction.model_probability,
            Prediction.created_at,
        )
        .join(League, Match.league_id == League.id)
        .join(Prediction, Prediction.match_id == Match.id)
        .join(Market, Prediction.market_id == Market.id)
        .where(
            Match.status == MatchStatus.FINISHED,
            Match.kickoff_at >= cutoff,
            Match.kickoff_at <= generated_at,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
            Market.code == MarketCode.MATCH_WINNER,
            Prediction.model_version == MODEL_VERSION,
            Prediction.created_at <= Match.kickoff_at,
        )
        .order_by(Match.kickoff_at.desc(), Prediction.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return build_quality_report(rows_to_snapshots(rows), now=generated_at)
