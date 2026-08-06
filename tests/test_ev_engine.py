import pytest

from app.services.ev_engine import calculate_ev, evaluate_bet, kelly_fraction


def test_ev_matches_probability_and_decimal_odds() -> None:
    assert calculate_ev(0.61, 2.10) == pytest.approx(0.281)


@pytest.mark.parametrize(
    ("probability", "odds"),
    [(-0.01, 2.0), (1.01, 2.0), (0.5, 1.0)],
)
def test_ev_rejects_invalid_inputs(probability: float, odds: float) -> None:
    with pytest.raises(ValueError):
        calculate_ev(probability, odds)


def test_kelly_never_recommends_negative_stake() -> None:
    assert kelly_fraction(0.4, 2.0) == 0.0
    assert evaluate_bet(0.61, 2.1, 1000).recommended_stake > 0
