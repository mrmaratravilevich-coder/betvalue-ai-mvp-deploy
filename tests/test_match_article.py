from datetime import datetime, timezone

from app.services.match_article import ArticlePrediction, build_match_article


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

