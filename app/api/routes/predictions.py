from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.prediction import Prediction
from app.schemas.prediction import PredictionOut

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("", response_model=list[PredictionOut])
async def list_predictions(
    match_id: int | None = Query(default=None),
    max_uncertainty: float = Query(
        default=0.5,
        ge=0,
        le=1,
        description="Максимальная допустимая неопределённость модели",
    ),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Prediction).options(selectinload(Prediction.market))
    if match_id is not None:
        stmt = stmt.where(Prediction.match_id == match_id)
    stmt = stmt.where(
        Prediction.uncertainty.is_not(None),
        Prediction.uncertainty <= max_uncertainty,
    )
    stmt = stmt.order_by(Prediction.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    predictions = result.scalars().all()
    return [
        PredictionOut(
            id=p.id,
            match_id=p.match_id,
            market=p.market.name,
            selection=p.selection,
            model_probability=float(p.model_probability),
            model_version=p.model_version,
            ensemble_components=p.ensemble_components,
            uncertainty=float(p.uncertainty) if p.uncertainty is not None else None,
        )
        for p in predictions
    ]
