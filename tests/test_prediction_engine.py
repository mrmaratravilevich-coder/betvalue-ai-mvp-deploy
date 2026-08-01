import pytest

from app.services.models.poisson_model import predict_match
from app.services.prediction_engine import LeagueModel, TeamStrength, _calibrated_match_winner


def test_uncertainty_is_maximum_without_team_history() -> None:
    model = LeagueModel(league_avg_home_goals=1.5, league_avg_away_goals=1.1)

    assert model.uncertainty_for(10, 20) == 1.0


def test_uncertainty_drops_with_relevant_home_and_away_history() -> None:
    model = LeagueModel(
        league_avg_home_goals=1.5,
        league_avg_away_goals=1.1,
        team_strengths={
            10: TeamStrength(home_games=12),
            20: TeamStrength(away_games=12),
        },
    )

    assert model.uncertainty_for(10, 20) == 0.4


def test_match_winner_calibration_is_normalized_and_preserves_ranking() -> None:
    probabilities = predict_match(1.8, 0.9)
    calibrated = _calibrated_match_winner(probabilities, 1.4)

    assert sum(calibrated.values()) == pytest.approx(1.0)
    assert max(calibrated, key=calibrated.get) == "home"
    assert calibrated["home"] < probabilities.home_win
