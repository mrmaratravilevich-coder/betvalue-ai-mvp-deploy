from dataclasses import dataclass
from datetime import datetime


OUTCOME_LABELS = {
    "home": "победа хозяев",
    "draw": "ничья",
    "away": "победа гостей",
}


@dataclass(frozen=True)
class ArticlePrediction:
    selection: str
    probability: float
    uncertainty: float | None
    model_version: str
    created_at: datetime


@dataclass(frozen=True)
class ArticleContext:
    sport_code: str = "football"
    home_form: tuple[str, ...] = ()
    away_form: tuple[str, ...] = ()
    h2h_count: int = 0
    h2h_home_wins: int = 0
    h2h_draws: int = 0
    h2h_away_wins: int = 0
    expected_home_score: float | None = None
    expected_away_score: float | None = None
    over_2_5_probability: float | None = None
    both_score_probability: float | None = None


@dataclass(frozen=True)
class GeneratedArticle:
    status: str
    title: str
    lead: str
    verdict: str
    confidence_label: str
    sections: list[dict[str, str]]
    model_version: str | None
    updated_at: datetime | None


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _confidence_label(uncertainty: float) -> str:
    if uncertainty <= 0.2:
        return "Высокая"
    if uncertainty <= 0.35:
        return "Средняя"
    return "Ограниченная"


def _outcome_name(selection: str, home_team: str, away_team: str) -> str:
    if selection == "home":
        return f"победа {home_team}"
    if selection == "away":
        return f"победа {away_team}"
    return "ничья"


def _form_points(form: tuple[str, ...]) -> int:
    return sum(3 if result == "В" else 1 if result == "Н" else 0 for result in form)


def _scenario_text(
    *,
    selection: str,
    home_team: str,
    away_team: str,
    probabilities: dict[str, float],
    context: ArticleContext | None,
) -> str:
    parts = [
        f"Расчёт даёт {home_team} {_percent(probabilities['home'])}, ничьей {_percent(probabilities['draw'])}, "
        f"а {away_team} — {_percent(probabilities['away'])}."
    ]
    if context and context.home_form and context.away_form:
        home_points = _form_points(context.home_form)
        away_points = _form_points(context.away_form)
        home_games = len(context.home_form)
        away_games = len(context.away_form)
        if abs(home_points - away_points) >= 4:
            stronger = home_team if home_points > away_points else away_team
            weaker = away_team if home_points > away_points else home_team
            parts.append(
                f"Текущая форма сильнее у {stronger}: {max(home_points, away_points)} условных очков "
                f"против {min(home_points, away_points)} у {weaker} за {max(home_games, away_games)} последних игр. "
                "Это важное ограничение для основного прогноза."
            )
        else:
            parts.append(
                f"Форма сопоставима: {home_team} набрал {home_points} условных очков за {home_games} игр, "
                f"{away_team} — {away_points} за {away_games}."
            )
    if context and context.expected_home_score is not None and context.expected_away_score is not None:
        unit = "гола" if context.sport_code in {"football", "hockey"} else "очка"
        total = context.expected_home_score + context.expected_away_score
        scoring = (
            f"Модель ожидает {context.expected_home_score:.2f}:{context.expected_away_score:.2f} {unit} "
            f"(суммарно {total:.2f})"
        )
        signals: list[str] = []
        if context.over_2_5_probability is not None:
            signals.append(f"тотал больше 2,5 — {_percent(context.over_2_5_probability)}")
        if context.both_score_probability is not None:
            signals.append(f"обе забьют — {_percent(context.both_score_probability)}")
        parts.append(scoring + ("; " + ", ".join(signals) if signals else "") + ".")
    if context and context.h2h_count:
        parts.append(
            f"Очная выборка ({context.h2h_count}): победы {home_team} — {context.h2h_home_wins}, "
            f"ничьи — {context.h2h_draws}, победы {away_team} — {context.h2h_away_wins}. "
            "Из-за размера выборки это вспомогательный, а не решающий сигнал."
        )
    if len(parts) == 1:
        fallback = {
            "home": "Базовый сценарий — умеренный перевес хозяев без признаков односторонней игры.",
            "away": "Базовый сценарий — преимущество гостей при сохраняющемся домашнем сопротивлении.",
            "draw": "Базовый сценарий — равная игра без устойчивого преимущества одной стороны.",
        }
        parts.append(fallback[selection])
    return " ".join(parts)


def _alternative_scenario_text(selection: str, home_team: str, away_team: str) -> str:
    """Describe the counter-scenario instead of presenting one-sided certainty."""
    if selection == "home":
        return (
            f"Альтернативный сценарий: {away_team} удерживает темп, закрывает центр и"
            f" переводит игру в эпизоды. Тогда преимущество {home_team} может не реализоваться."
        )
    if selection == "away":
        return (
            f"Альтернативный сценарий: {home_team} использует фактор своего поля,"
            f" забирает инициативу после стартового отрезка и не даёт {away_team} играть на переходах."
        )
    return (
        f"Альтернативный сценарий: одна из команд забивает первой и заставляет соперника"
        f" отказаться от осторожного плана. Для пары {home_team} — {away_team} это особенно важно"
        " при близких вероятностях исходов."
    )


def build_match_article(
    *,
    match_id: int,
    home_team: str,
    away_team: str,
    league_name: str,
    predictions: list[ArticlePrediction],
    article_context: ArticleContext | None = None,
) -> GeneratedArticle:
    title = f"{home_team} — {away_team}: короткий разбор матча"
    latest = {prediction.selection: prediction for prediction in predictions}
    outcomes = [latest.get(selection) for selection in ("home", "draw", "away")]

    if any(outcome is None for outcome in outcomes):
        return GeneratedArticle(
            status="waiting",
            title=title,
            lead=f"Матч турнира «{league_name}». Данных пока недостаточно для уверенного вывода.",
            verdict="Разбор появится автоматически, когда расчёт будет готов.",
            confidence_label="Недостаточно данных",
            sections=[
                {
                    "title": "Почему разбор ещё не опубликован",
                    "body": "Мы не заполняем пробелы общими фразами и не придумываем проценты. Для публикации нужны три сопоставимых исхода матча.",
                },
                {
                    "title": "Что произойдёт дальше",
                    "body": "После следующего обновления данных страница сама получит короткий вывод, баланс исходов и оценку надёжности.",
                },
            ],
            model_version=None,
            updated_at=None,
        )

    complete_outcomes = [outcome for outcome in outcomes if outcome is not None]
    uncertainty_values = [outcome.uncertainty for outcome in complete_outcomes]
    if any(value is None for value in uncertainty_values) or max(value for value in uncertainty_values if value is not None) > 0.5:
        newest = max(complete_outcomes, key=lambda item: item.created_at)
        return GeneratedArticle(
            status="waiting",
            title=title,
            lead=f"Матч турнира «{league_name}». Расчёт уже есть, но его надёжность пока недостаточна для публикации.",
            verdict="Лучше дождаться более устойчивых данных.",
            confidence_label="Недостаточно данных",
            sections=[
                {
                    "title": "Почему мы ждём",
                    "body": "Текущие данные дают слишком широкий диапазон возможных сценариев. Публиковать один из них как основной было бы преждевременно.",
                },
                {
                    "title": "Когда появится статья",
                    "body": "Разбор обновится автоматически после накопления достаточной истории матчей команд.",
                },
            ],
            model_version=newest.model_version,
            updated_at=newest.created_at,
        )

    # A prediction source may return rounded or slightly uncalibrated values.
    # Normalize once before ranking and printing so the article never shows a
    # contradictory probability balance (for example, 50% + 40% + 40%).
    raw_probabilities = {
        item.selection: max(float(item.probability), 0.0)
        for item in complete_outcomes
    }
    probability_total = sum(raw_probabilities.values())
    if probability_total <= 0:
        newest = max(complete_outcomes, key=lambda item: item.created_at)
        return GeneratedArticle(
            status="waiting",
            title=title,
            lead=f"Матч турнира «{league_name}». Расчёт не опубликован: вероятности ещё не прошли проверку.",
            verdict="Нужна дополнительная проверка данных.",
            confidence_label="Недостаточно данных",
            sections=[
                {
                    "title": "Почему мы ждём",
                    "body": "Публикуем вывод только после проверки всех трёх исходов и их согласованности.",
                },
            ],
            model_version=newest.model_version,
            updated_at=newest.created_at,
        )
    probability_by_selection = {
        selection: probability / probability_total
        for selection, probability in raw_probabilities.items()
    }
    ranked_selections = sorted(
        probability_by_selection,
        key=probability_by_selection.get,
        reverse=True,
    )
    leader_selection, second_selection = ranked_selections[:2]
    leader = latest[leader_selection]
    second = latest[second_selection]
    uncertainty = max(value for value in uncertainty_values if value is not None)
    margin = probability_by_selection[leader_selection] - probability_by_selection[second_selection]
    if margin >= 0.15:
        balance = "Перевес заметный, но он не исключает другой исход."
    elif margin >= 0.07:
        balance = "Перевес небольшой, поэтому матч остаётся конкурентным."
    else:
        balance = "Исходы расположены близко — явного фаворита нет."

    verdict_name = _outcome_name(leader.selection, home_team, away_team)
    newest = max(complete_outcomes, key=lambda item: item.created_at)
    return GeneratedArticle(
        status="ready",
        title=title,
        lead=f"Наиболее вероятный сценарий — {verdict_name} ({_percent(probability_by_selection[leader_selection])}). {balance}",
        verdict=verdict_name[:1].upper() + verdict_name[1:],
        confidence_label=_confidence_label(uncertainty),
        sections=[
            {
                "title": "Баланс исходов",
                "body": (
                    f"Победа {home_team} — {_percent(probability_by_selection['home'])}, "
                    f"ничья — {_percent(probability_by_selection['draw'])}, "
                    f"победа {away_team} — {_percent(probability_by_selection['away'])}."
                ),
            },
            {
                "title": "Как может пройти матч",
                "body": _scenario_text(
                    selection=leader.selection,
                    home_team=home_team,
                    away_team=away_team,
                    probabilities=probability_by_selection,
                    context=article_context,
                ),
            },
            {
                "title": "Два сценария матча",
                "body": f"Основной сценарий: {_scenario_text(selection=leader.selection, home_team=home_team, away_team=away_team, probabilities=probability_by_selection, context=article_context)} "
                f"{_alternative_scenario_text(leader.selection, home_team, away_team)}",
            },
            {
                "title": "Риски и ограничения",
                "body": (
                    f"Уровень надёжности — {_confidence_label(uncertainty).lower()}. "
                    f"Разница между лидирующим исходом и следующим вариантом — {_percent(margin)}. "
                    "Это оценка текущего расклада, а не обещание результата. "
                    "Составы, новости и движение линии учитываются только при наличии подтверждённых данных."
                ),
            },
        ],
        model_version=newest.model_version,
        updated_at=newest.created_at,
    )
