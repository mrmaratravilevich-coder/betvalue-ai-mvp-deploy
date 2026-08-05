from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.enums import MarketCode, MatchStatus
from app.models.match import Match
from app.models.prediction import Prediction
from app.models.team import League
from app.schemas.match_article import MatchArticleOut
from app.services.match_article import ArticlePrediction, build_match_article
from app.services.name_localization import localize_name
from app.services.match_context import HistoricalMatch, build_context_sections

router = APIRouter(prefix="/match-articles", tags=["match-articles"])


@router.get("/{match_id}", response_model=MatchArticleOut)
async def get_match_article(match_id: int, db: AsyncSession = Depends(get_db)) -> MatchArticleOut:
    match_result = await db.execute(
        select(Match)
        .options(
            selectinload(Match.home_team),
            selectinload(Match.away_team),
            selectinload(Match.league).selectinload(League.sport),
        )
        .where(Match.id == match_id)
    )
    match = match_result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не найден")

    prediction_result = await db.execute(
        select(Prediction)
        .options(selectinload(Prediction.market))
        .where(Prediction.match_id == match_id)
        .order_by(Prediction.created_at.desc())
    )
    latest: dict[str, ArticlePrediction] = {}
    for prediction in prediction_result.scalars().all():
        if prediction.market.code != MarketCode.MATCH_WINNER or prediction.selection in latest:
            continue
        if prediction.selection not in {"home", "draw", "away"}:
            continue
        latest[prediction.selection] = ArticlePrediction(
            selection=prediction.selection,
            probability=float(prediction.model_probability),
            uncertainty=float(prediction.uncertainty) if prediction.uncertainty is not None else None,
            model_version=prediction.model_version,
            created_at=prediction.created_at,
        )

    history_result = await db.execute(
        select(Match)
        .where(
            Match.status == MatchStatus.FINISHED,
            Match.kickoff_at < match.kickoff_at,
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
            or_(
                Match.home_team_id.in_([match.home_team_id, match.away_team_id]),
                Match.away_team_id.in_([match.home_team_id, match.away_team_id]),
            ),
        )
        .order_by(desc(Match.kickoff_at))
        .limit(40)
    )
    history = [HistoricalMatch(row.home_team_id, row.away_team_id, int(row.home_score), int(row.away_score)) for row in history_result.scalars().all()]
    home_name = localize_name(match.home_team.name)
    away_name = localize_name(match.away_team.name)
    article = build_match_article(
        match_id=match.id, home_team=home_name, away_team=away_name,
        league_name=localize_name(match.league.name), predictions=list(latest.values()),
    )
    if article.status == "ready":
        article.sections.extend(build_context_sections(
            home_name=home_name, away_name=away_name, home_id=match.home_team_id,
            away_id=match.away_team_id, matches=history,
        ))
    return MatchArticleOut(match_id=match.id, **article.__dict__)

