"""
Финальное звено пайплайна: Prediction (вероятность модели) + OddsLine
(последняя известная цена) -> ev_engine.calculate_ev/kelly_fraction/passes_filters
-> EVBet.

Точка входа для ежедневного цикла в 09:00 ("Поиск EV") и для почасового
пересчёта при обновлении линии — обе задачи вызывают одну и ту же функцию,
она идемпотентна: на пару (prediction_id) всегда ровно один EVBet, который
просто обновляется при новой цене, а не плодится дублями.

Ограничение по составам ("За 30 минут — обновление составов", фильтр
"неизвестный состав") пока не реализовано — источника данных о заявках нет,
поэтому _lineup_known() всегда возвращает True. Как только появится модуль
обновления составов, здесь нужно будет только заменить эту функцию.
"""
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.enums import BetStatus, MatchStatus
from app.models.match import Match
from app.models.odds import OddsLine
from app.models.prediction import EVBet, Prediction
from app.services.ev_engine import calculate_ev, kelly_fraction, passes_filters

logger = logging.getLogger(__name__)

# Если цена по одному и тому же исходу изменилась больше, чем на эту долю
# между первым и последним известным снимком — считаем движение подозрительным
# (см. фильтр "Подозрительное движение линии" в ТЗ). Эвристика, не защита от
# реального манипулирования линией — только грубая отсечка аномалий/опечаток.
LINE_MOVEMENT_THRESHOLD = 0.30

# Порог неопределённости модели, выше которого ставка отсекается фильтром
# "Высокая неопределённость модели" (см. ev_engine.passes_filters).
MAX_MODEL_UNCERTAINTY = 0.5


@dataclass
class EVGenerationStats:
    predictions_seen: int = 0
    no_odds: int = 0
    passed_filters: int = 0
    filtered_out: int = 0


def _lineup_known(match: Match) -> bool:
    """TODO: заменить на реальную проверку, когда появится модуль составов."""
    return True


async def _latest_odds_line(
    db: AsyncSession, match_id: int, market_id: int, selection: str
) -> OddsLine | None:
    result = await db.execute(
        select(OddsLine)
        .where(
            OddsLine.match_id == match_id,
            OddsLine.market_id == market_id,
            OddsLine.selection == selection,
        )
        .order_by(OddsLine.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _line_movement(
    db: AsyncSession, match_id: int, market_id: int, selection: str
) -> tuple[float, float] | None:
    """Возвращает (первая_цена, последняя_цена) по исходу, либо None, если снимок один."""
    result = await db.execute(
        select(OddsLine.price, OddsLine.created_at)
        .where(
            OddsLine.match_id == match_id,
            OddsLine.market_id == market_id,
            OddsLine.selection == selection,
        )
        .order_by(OddsLine.created_at.asc())
    )
    rows = result.all()
    if len(rows) < 2:
        return None
    return float(rows[0][0]), float(rows[-1][0])


def _is_suspicious_movement(first_price: float, last_price: float) -> bool:
    if first_price <= 0:
        return False
    relative_change = abs(last_price - first_price) / first_price
    return relative_change > LINE_MOVEMENT_THRESHOLD


async def _historical_matches_count(db: AsyncSession, league_id: int) -> int:
    """Число завершённых матчей лиги — фильтр 'Меньше 1000 исторических матчей'."""
    result = await db.execute(
        select(func.count(Match.id)).where(
            Match.league_id == league_id, Match.status == MatchStatus.FINISHED
        )
    )
    return result.scalar_one()


def _confidence_score(ev: float, uncertainty: float) -> float:
    """
    Грубая эвристика для поля 'Уверенность' в карточке матча (0..10 по ТЗ):
    выше EV и ниже неопределённость модели -> выше уверенность.
    Не заменяет калибровку вероятностей (Brier Score/Log Loss) из v2.0 ТЗ —
    это отдельная задача поверх честной оценки модели, здесь только эвристика
    для сортировки/отображения.
    """
    ev_component = min(ev / 0.30, 1.0)          # EV >= 30% насыщает шкалу
    certainty_component = 1 - min(uncertainty, 1.0)
    return round(10 * (0.6 * ev_component + 0.4 * certainty_component), 1)


def _build_reasoning(
    match: Match, prediction: Prediction, odds_line: OddsLine, ev: float, market_probability: float
) -> str:
    """
    Текстовое объяснение ставки (блок 'AI Explain' в ТЗ). Собирается по
    шаблону из фактов, которые реально есть в БД — без обращения к LLM,
    чтобы пайплайн формирования EV не зависел от внешнего API.
    """
    lines: list[str] = []

    poisson = (prediction.ensemble_components or {}).get("poisson")
    if poisson:
        lines.append(
            f"Модель ожидает {poisson['expected_home_goals']} гола(ов) у {match.home_team.name} "
            f"и {poisson['expected_away_goals']} у {match.away_team.name}."
        )

    lines.append(
        f"Вероятность модели на исход «{prediction.selection}»: {prediction.model_probability:.0%}, "
        f"рынок оценивает его в {market_probability:.0%} (коэффициент {float(odds_line.price):.2f})."
    )
    lines.append(f"Разница даёт положительное математическое ожидание: EV = {ev:+.1%}.")

    return " ".join(lines)


async def _upsert_ev_bet(
    db: AsyncSession,
    prediction: Prediction,
    odds_line: OddsLine,
    ev: float,
    kelly: float,
    confidence: float,
    reasoning: str,
    status: BetStatus,
) -> EVBet:
    result = await db.execute(select(EVBet).where(EVBet.prediction_id == prediction.id, EVBet.user_id.is_(None)))
    ev_bet = result.scalar_one_or_none()
    if ev_bet is None:
        ev_bet = EVBet(prediction_id=prediction.id)
        db.add(ev_bet)

    ev_bet.odds_line_id = odds_line.id
    ev_bet.ev = ev
    ev_bet.kelly_fraction = kelly
    ev_bet.recommended_stake = None  # зависит от банка конкретного пользователя — считается на чтении
    ev_bet.confidence = confidence
    ev_bet.reasoning = reasoning
    ev_bet.status = status
    await db.flush()
    return ev_bet


async def generate_ev_bets_for_match(
    db: AsyncSession,
    match: Match,
    *,
    min_ev: float = settings.MIN_EV_THRESHOLD,
    max_odds: float = settings.MAX_ODDS,
    min_historical_matches: int = settings.MIN_HISTORICAL_MATCHES,
    kelly_pct: float = settings.DEFAULT_KELLY_FRACTION,
) -> EVGenerationStats:
    stats = EVGenerationStats()

    # home_team/away_team нужны для текста AI Explain (_build_reasoning). Не полагаемся
    # на то, что вызывающий код заранее сделал selectinload — догружаем сами, иначе
    # в async-сессии ленивая подгрузка на match.home_team падает с MissingGreenlet.
    match = (
        await db.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(Match.id == match.id)
        )
    ).scalar_one()

    predictions = (
        await db.execute(select(Prediction).where(Prediction.match_id == match.id))
    ).scalars().all()
    if not predictions:
        return stats

    historical_matches = await _historical_matches_count(db, match.league_id)
    lineup_known = _lineup_known(match)

    for prediction in predictions:
        stats.predictions_seen += 1

        odds_line = await _latest_odds_line(db, match.id, prediction.market_id, prediction.selection)
        if odds_line is None:
            stats.no_odds += 1
            continue

        odds = float(odds_line.price)
        model_probability = float(prediction.model_probability)
        ev = calculate_ev(model_probability, odds)

        movement = await _line_movement(db, match.id, prediction.market_id, prediction.selection)
        suspicious_movement = _is_suspicious_movement(*movement) if movement else False

        ok, reason = passes_filters(
            ev=ev,
            odds=odds,
            historical_matches=historical_matches,
            lineup_known=lineup_known,
            suspicious_line_movement=suspicious_movement,
            model_uncertainty=float(prediction.uncertainty or 0.0),
            min_ev=min_ev,
            max_odds=max_odds,
            min_historical_matches=min_historical_matches,
            max_uncertainty=MAX_MODEL_UNCERTAINTY,
        )

        # kelly_pct приходит либо долей (settings.DEFAULT_KELLY_FRACTION=0.25), либо
        # процентом (UserSettings.kelly_fraction_pct=25.0) — приводим к единому формату.
        kelly = kelly_fraction(model_probability, odds, fraction=kelly_pct / 100 if kelly_pct > 1 else kelly_pct)
        confidence = _confidence_score(ev, float(prediction.uncertainty or 0.0))
        reasoning = _build_reasoning(match, prediction, odds_line, ev, odds_line.implied_probability)
        if not ok:
            reasoning = f"{reasoning} Отсеяно фильтром: {reason}."

        await _upsert_ev_bet(
            db,
            prediction=prediction,
            odds_line=odds_line,
            ev=ev,
            kelly=kelly,
            confidence=confidence,
            reasoning=reasoning,
            status=BetStatus.PENDING if ok else BetStatus.FILTERED_OUT,
        )

        if ok:
            stats.passed_filters += 1
        else:
            stats.filtered_out += 1

    await db.commit()
    return stats


async def generate_ev_bets_all(db: AsyncSession) -> dict[str, int]:
    """
    Точка входа для ежедневного цикла (09:00 "Поиск EV") и для почасового
    обновления линии — вызывается заново на каждое обновление OddsLine.
    """
    matches = (
        await db.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(Match.status == MatchStatus.SCHEDULED)
        )
    ).scalars().all()

    total = EVGenerationStats()
    for match in matches:
        match_stats = await generate_ev_bets_for_match(db, match)
        total.predictions_seen += match_stats.predictions_seen
        total.no_odds += match_stats.no_odds
        total.passed_filters += match_stats.passed_filters
        total.filtered_out += match_stats.filtered_out

    logger.info(
        "EV-поиск: матчей=%s, прогнозов=%s, без коэффициентов=%s, прошли фильтры=%s, отсеяно=%s",
        len(matches), total.predictions_seen, total.no_odds, total.passed_filters, total.filtered_out,
    )
    return {
        "matches": len(matches),
        "predictions_seen": total.predictions_seen,
        "no_odds": total.no_odds,
        "passed_filters": total.passed_filters,
        "filtered_out": total.filtered_out,
    }
