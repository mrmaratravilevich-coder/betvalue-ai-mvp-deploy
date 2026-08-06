"""
Расчёт EV и рекомендуемого размера ставки (Kelly).
Формулы — точно по разделу "Расчёт EV" / "Kelly" в ТЗ.

Подбор прогнозов (Poisson/XGBoost/LightGBM/ансамбль) и сами фильтры
(EV<5%, коэфф.>6, <1000 матчей, неизвестный состав, аномальное движение
линии, высокая неопределённость) реализуются отдельно в ML-пайплайне —
здесь только чистая математика, не зависящая от модели.
"""
from dataclasses import dataclass


def implied_probability(odds: float) -> float:
    """Имплицитная вероятность рынка: 1 / коэффициент."""
    if odds <= 1:
        raise ValueError("Коэффициент должен быть больше 1")
    return 1 / odds


def calculate_ev(model_probability: float, odds: float) -> float:
    """
    EV = P(модель) * коэффициент - 1

    Пример из ТЗ: P=0.61, odds=2.10 -> EV = 0.61*2.10 - 1 = 0.281 (+28.1%)
    """
    if not 0 <= model_probability <= 1:
        raise ValueError("Вероятность модели должна быть в диапазоне 0..1")
    implied_probability(odds)
    return model_probability * odds - 1


def kelly_fraction(model_probability: float, odds: float, fraction: float = 0.25) -> float:
    """
    f = (b*p - q) / b
    b = коэффициент - 1
    p = вероятность модели
    q = 1 - p

    fraction — доля от полного Kelly (по ТЗ используем 25%).
    Результат ограничен снизу нулём: при отрицательном EV ставка не рекомендуется.
    """
    if not 0 <= model_probability <= 1:
        raise ValueError("Вероятность модели должна быть в диапазоне 0..1")
    if fraction < 0:
        raise ValueError("Доля Kelly не может быть отрицательной")
    implied_probability(odds)
    b = odds - 1
    p = model_probability
    q = 1 - p
    full_kelly = (b * p - q) / b
    return max(full_kelly, 0.0) * fraction


@dataclass
class EVEvaluation:
    model_probability: float
    market_probability: float
    odds: float
    ev: float
    kelly: float
    recommended_stake: float


def evaluate_bet(model_probability: float, odds: float, bank: float, kelly_pct: float = 0.25) -> EVEvaluation:
    """Собирает воедино EV и рекомендуемую ставку в рублях/условных единицах банка."""
    if bank < 0:
        raise ValueError("Банк не может быть отрицательным")
    ev = calculate_ev(model_probability, odds)
    k = kelly_fraction(model_probability, odds, fraction=kelly_pct)
    return EVEvaluation(
        model_probability=model_probability,
        market_probability=implied_probability(odds),
        odds=odds,
        ev=ev,
        kelly=k,
        recommended_stake=round(bank * k, 2),
    )


def passes_filters(
    ev: float,
    odds: float,
    historical_matches: int,
    lineup_known: bool,
    suspicious_line_movement: bool,
    model_uncertainty: float,
    min_ev: float = 0.05,
    max_odds: float = 6.0,
    min_historical_matches: int = 1000,
    max_uncertainty: float = 0.5,
) -> tuple[bool, str | None]:
    """
    Реализация раздела "Фильтры" из ТЗ. Возвращает (проходит_ли, причина_отказа).
    """
    if ev < min_ev:
        return False, f"EV {ev:.1%} ниже порога {min_ev:.1%}"
    if odds > max_odds:
        return False, f"Коэффициент {odds} выше лимита {max_odds}"
    if historical_matches < min_historical_matches:
        return False, f"Недостаточно исторических матчей: {historical_matches} < {min_historical_matches}"
    if not lineup_known:
        return False, "Неизвестен состав"
    if suspicious_line_movement:
        return False, "Подозрительное движение линии"
    if model_uncertainty > max_uncertainty:
        return False, f"Высокая неопределённость модели: {model_uncertainty:.2f}"
    return True, None
