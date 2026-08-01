from datetime import datetime, timedelta, timezone

import pytest

from app.services.backtest import (
    HistoricalMatch,
    _elo_expected_home,
    _update_elo,
    evaluate_chronologically,
    summarize_backtest,
)


def _matches(count: int = 12) -> list[HistoricalMatch]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        HistoricalMatch(
            kickoff_at=start + timedelta(days=index),
            home_team_id=index % 4,
            away_team_id=(index + 1) % 4,
            home_score=(index + 1) % 3,
            away_score=index % 2,
        )
        for index in range(count)
    ]


def test_backtest_uses_only_earlier_matches() -> None:
    predictions = evaluate_chronologically(_matches(), min_train_matches=4, min_team_games=1)

    assert len(predictions) == 8
    assert [prediction.training_matches for prediction in predictions] == list(range(4, 12))


def test_backtest_rolling_window_caps_training_history() -> None:
    predictions = evaluate_chronologically(
        _matches(),
        min_train_matches=4,
        min_team_games=1,
        history_window=6,
    )

    assert len(predictions) == 8
    assert max(prediction.training_matches for prediction in predictions) == 6


def test_backtest_rejects_window_smaller_than_warmup() -> None:
    with pytest.raises(ValueError, match="history_window"):
        evaluate_chronologically([], min_train_matches=100, history_window=99)


def test_elo_expected_result_reflects_home_advantage() -> None:
    assert _elo_expected_home(1500, 1500) > 0.5


def test_elo_update_is_zero_sum() -> None:
    new_home, new_away = _update_elo(1500, 1500, home_score=0, away_score=1)

    assert new_home < 1500
    assert new_away > 1500
    assert new_home + new_away == pytest.approx(3000)


def test_zero_elo_weight_preserves_poisson_predictions() -> None:
    baseline = evaluate_chronologically(_matches(), min_train_matches=4, min_team_games=1)
    zero_weight = evaluate_chronologically(
        _matches(),
        min_train_matches=4,
        min_team_games=1,
        elo_weight=0.0,
    )

    assert zero_weight == baseline


def test_input_order_does_not_change_predictions() -> None:
    matches = _matches()

    chronological = evaluate_chronologically(matches, min_train_matches=4, min_team_games=1)
    reversed_input = evaluate_chronologically(
        list(reversed(matches)),
        min_train_matches=4,
        min_team_games=1,
    )

    assert chronological == reversed_input


def test_baseline_uses_only_prior_results() -> None:
    predictions = evaluate_chronologically(_matches(), min_train_matches=4, min_team_games=1)
    first = predictions[0]

    assert first.training_matches == 4
    assert first.baseline_home_probability == pytest.approx(3 / 7)
    assert first.baseline_draw_probability == pytest.approx(3 / 7)
    assert first.baseline_away_probability == pytest.approx(1 / 7)


def test_report_contains_probability_quality_metrics() -> None:
    predictions = evaluate_chronologically(_matches(), min_train_matches=4, min_team_games=1)
    report = summarize_backtest(predictions, skipped_warmup=4)

    assert report.evaluated_matches == 8
    assert 0 <= report.accuracy <= 1
    assert 0 <= report.brier_score <= 2
    assert report.log_loss >= 0
    assert report.baseline_brier_score >= 0
    assert report.baseline_log_loss >= 0
    assert 0 <= report.calibration_error <= 1


def test_empty_evaluation_is_rejected() -> None:
    with pytest.raises(ValueError, match="Недостаточно матчей"):
        summarize_backtest([], skipped_warmup=100)
