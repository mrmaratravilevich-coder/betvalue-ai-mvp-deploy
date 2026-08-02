import math
import unittest
from datetime import datetime, timedelta, timezone

from app.services.model_quality import PredictionSnapshot, build_quality_report, rows_to_snapshots, summarize_snapshots


NOW = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)


def snapshot(match_id: int, age_days: int, actual: str, probabilities: dict[str, float], league_id: int = 1):
    return PredictionSnapshot(
        match_id=match_id,
        league_id=league_id,
        league_name=f"League {league_id}",
        kickoff_at=NOW - timedelta(days=age_days),
        actual=actual,
        probabilities=probabilities,
    )


class ModelQualityTests(unittest.TestCase):
    def test_multiclass_metrics(self) -> None:
        metrics = summarize_snapshots(
            [
                snapshot(1, 1, "home", {"home": 0.7, "draw": 0.2, "away": 0.1}),
                snapshot(2, 2, "draw", {"home": 0.2, "draw": 0.3, "away": 0.5}),
            ]
        )
        self.assertEqual(metrics.evaluated_matches, 2)
        self.assertAlmostEqual(metrics.accuracy, 0.5)
        self.assertAlmostEqual(metrics.brier_score, 0.46)
        self.assertAlmostEqual(metrics.log_loss, (-math.log(0.7) - math.log(0.3)) / 2)

    def test_rolling_windows_and_leagues(self) -> None:
        probabilities = {"home": 0.5, "draw": 0.3, "away": 0.2}
        report = build_quality_report(
            [
                snapshot(1, 5, "home", probabilities),
                snapshot(2, 20, "draw", probabilities, league_id=2),
                snapshot(3, 60, "away", probabilities),
                snapshot(4, 100, "home", probabilities),
            ],
            now=NOW,
        )
        self.assertEqual([window.overall.evaluated_matches for window in report.windows], [1, 2, 3])
        self.assertEqual(len(report.windows[1].leagues), 2)

    def test_post_match_and_incomplete_predictions_are_excluded(self) -> None:
        kickoff = NOW - timedelta(days=1)
        rows = [
            (1, 1, "League", kickoff, 2, 0, "home", 0.6, kickoff - timedelta(hours=1)),
            (1, 1, "League", kickoff, 2, 0, "draw", 0.25, kickoff - timedelta(hours=1)),
            (1, 1, "League", kickoff, 2, 0, "away", 0.15, kickoff - timedelta(hours=1)),
            (1, 1, "League", kickoff, 2, 0, "home", 0.99, kickoff + timedelta(hours=2)),
            (2, 1, "League", kickoff, 1, 1, "home", 0.5, kickoff - timedelta(hours=1)),
            (2, 1, "League", kickoff, 1, 1, "draw", 0.3, kickoff - timedelta(hours=1)),
        ]
        snapshots = rows_to_snapshots(rows)
        self.assertEqual(len(snapshots), 1)
        self.assertAlmostEqual(snapshots[0].probabilities["home"], 0.6)


if __name__ == "__main__":
    unittest.main()
