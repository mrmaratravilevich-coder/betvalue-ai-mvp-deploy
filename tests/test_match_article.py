from datetime import datetime, timezone

from app.services.match_article import ArticleContext, ArticlePrediction, build_match_article


NOW = datetime(2026, 8, 3, 18, tzinfo=timezone.utc)


def prediction(selection: str, probability: float, uncertainty: float = 0.24) -> ArticlePrediction:
    return ArticlePrediction(
        selection=selection,
        probability=probability,
        uncertainty=uncertainty,
        model_version="poisson-v1",
        created_at=NOW,
    )


def test_ready_article_is_plain_and_grounded() -> None:
    article = build_match_article(
        match_id=10,
        home_team="Арсенал",
        away_team="Челси",
        league_name="Премьер-лига",
        predictions=[
            prediction("home", 0.55),
            prediction("draw", 0.27),
            prediction("away", 0.18),
        ],
    )

    assert article.status == "ready"
    assert article.verdict == "Победа Арсенал"
    assert "55%" in article.lead
    assert article.confidence_label == "Средняя"
    assert len(article.sections) == 4
    assert any(section["title"] == "Два сценария матча" for section in article.sections)
    assert any(section["title"] == "Риски и ограничения" for section in article.sections)


def test_close_match_does_not_claim_clear_favorite() -> None:
    article = build_match_article(
        match_id=11,
        home_team="Команда А",
        away_team="Команда Б",
        league_name="Лига",
        predictions=[
            prediction("home", 0.36),
            prediction("draw", 0.33),
            prediction("away", 0.31),
        ],
    )

    assert "явного фаворита нет" in article.lead


def test_article_normalizes_rounded_probabilities() -> None:
    article = build_match_article(
        match_id=13,
        home_team="Команда А",
        away_team="Команда Б",
        league_name="Лига",
        predictions=[
            prediction("home", 50),
            prediction("draw", 30),
            prediction("away", 20),
        ],
    )

    assert "50%" in article.lead
    assert "100%" not in article.lead


def test_scenario_uses_match_specific_form_and_scoring_context() -> None:
    article = build_match_article(
        match_id=14,
        home_team="Айнтрахт Франкфурт",
        away_team="Аугсбург",
        league_name="Бундеслига",
        predictions=[prediction("home", 0.458), prediction("draw", 0.256), prediction("away", 0.286)],
        article_context=ArticleContext(
            home_form=("П", "Н", "П", "П", "Н"),
            away_form=("В", "Н", "В", "В", "П"),
            h2h_count=2,
            h2h_home_wins=1,
            h2h_draws=1,
            expected_home_score=1.863,
            expected_away_score=1.282,
            over_2_5_probability=0.60842,
            both_score_probability=0.61034,
        ),
    )

    scenario = next(section["body"] for section in article.sections if section["title"] == "Как может пройти матч")
    assert "46%" in scenario and "29%" in scenario
    assert "10 условных очков против 2" in scenario
    assert "1.86:1.28" in scenario
    assert "тотал больше 2,5 — 61%" in scenario
    assert "Очная выборка (2)" in scenario


def test_waiting_article_hides_incomplete_probabilities() -> None:
    article = build_match_article(
        match_id=12,
        home_team="Команда А",
        away_team="Команда Б",
        league_name="Лига",
        predictions=[prediction("home", 0.5), prediction("away", 0.5)],
    )

    assert article.status == "waiting"
    assert article.confidence_label == "Недостаточно данных"
    assert "%" not in article.lead

