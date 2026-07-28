"""
Пуассоновская модель для счёта матча (раздел "Алгоритмы" в ТЗ: "Poisson — для счёта").

Классический подход (Maher, 1982 / "the numbers game"): голы каждой команды —
независимые случайные величины с распределением Пуассона, ожидание которых
задаётся силой атаки одной команды и силой обороны другой.

Упрощение: голы команд считаются независимыми (без поправки Диксона-Коулза
на корреляцию низких счётов вроде 0:0/1:1). Это стандартная отправная точка;
поправку можно добавить позже, не меняя интерфейс функций ниже.
"""
from dataclasses import dataclass
from math import exp, factorial


@dataclass
class MatchProbabilities:
    expected_home_goals: float
    expected_away_goals: float

    home_win: float
    draw: float
    away_win: float

    btts_yes: float
    btts_no: float

    # Тоталы считаются для одной "центральной" линии (обычно 2.5) —
    # вызывающий код может запросить любую половинную линию.
    over_line: float
    under_line: float
    total_line: float


def score_matrix(expected_home_goals: float, expected_away_goals: float, max_goals: int = 10) -> list[list[float]]:
    """P(home забил i, away забил j) для i,j в [0, max_goals]."""
    def pmf(goals: int, expected_goals: float) -> float:
        return exp(-expected_goals) * expected_goals**goals / factorial(goals)

    home_probs = [pmf(i, expected_home_goals) for i in range(max_goals + 1)]
    away_probs = [pmf(j, expected_away_goals) for j in range(max_goals + 1)]
    return [[hp * ap for ap in away_probs] for hp in home_probs]


def predict_match(
    expected_home_goals: float,
    expected_away_goals: float,
    total_line: float = 2.5,
    max_goals: int = 10,
) -> MatchProbabilities:
    if expected_home_goals < 0 or expected_away_goals < 0:
        raise ValueError("Ожидаемое число голов не может быть отрицательным")

    matrix = score_matrix(expected_home_goals, expected_away_goals, max_goals)

    home_win = draw = away_win = 0.0
    btts_yes = 0.0
    over = 0.0

    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p

            if i > 0 and j > 0:
                btts_yes += p
            if i + j > total_line:
                over += p

    # "Хвост" за пределами max_goals обычно пренебрежимо мал (< 0.1% при
    # разумных ожиданиях голов), нормализуем, чтобы вероятности суммировались в 1.
    total_mass = home_win + draw + away_win
    if total_mass > 0:
        home_win, draw, away_win = (x / total_mass for x in (home_win, draw, away_win))

    return MatchProbabilities(
        expected_home_goals=expected_home_goals,
        expected_away_goals=expected_away_goals,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        btts_yes=btts_yes,
        btts_no=1 - btts_yes,
        over_line=over,
        under_line=1 - over,
        total_line=total_line,
    )
