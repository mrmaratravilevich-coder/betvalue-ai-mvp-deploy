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


def _scenario_text(selection: str, home_team: str, away_team: str) -> str:
    if selection == "home":
        return (
            f"По текущему расчёту инициатива чаще остаётся у {home_team}. "
            f"Для {away_team} ключевым становится умение удержать игру равной и не позволить хозяевам закрепить преимущество."
        )
    if selection == "away":
        return (
            f"Расчёт немного сильнее поддерживает {away_team}. "
            f"Матч может измениться, если {home_team} сумеет навязать свой темп и использовать преимущество домашней площадки."
        )
    return (
        f"Расклад между {home_team} и {away_team} выглядит близким. "
        "В таком матче особенно важен первый результативный эпизод: после него характер игры может заметно измениться."
    )


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

    ranked = sorted(complete_outcomes, key=lambda item: item.probability, reverse=True)
    leader, second = ranked[0], ranked[1]
    uncertainty = max(value for value in uncertainty_values if value is not None)
    margin = leader.probability - second.probability
    if margin >= 0.15:
        balance = "Перевес заметный, но он не исключает другой исход."
    elif margin >= 0.07:
        balance = "Перевес небольшой, поэтому матч остаётся конкурентным."
    else:
        balance = "Исходы расположены близко — явного фаворита нет."

    probability_by_selection = {item.selection: item.probability for item in complete_outcomes}
    verdict_name = _outcome_name(leader.selection, home_team, away_team)
    newest = max(complete_outcomes, key=lambda item: item.created_at)
    return GeneratedArticle(
        status="ready",
        title=title,
        lead=f"Наиболее вероятный сценарий — {verdict_name} ({_percent(leader.probability)}). {balance}",
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
                "body": _scenario_text(leader.selection, home_team, away_team),
            },
            {
                "title": "Два сценария матча",
                "body": f"Основной сценарий: {_scenario_text(leader.selection, home_team, away_team)} "
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
