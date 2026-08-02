from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.model_quality import ModelQualityOut
from app.services.model_quality import get_model_quality

router = APIRouter(prefix="/model-quality", tags=["model-quality"])


@router.get("", response_model=ModelQualityOut)
async def model_quality(db: AsyncSession = Depends(get_db)) -> ModelQualityOut:
    """Rolling, leakage-safe quality metrics for completed 1X2 predictions."""
    return await get_model_quality(db)
