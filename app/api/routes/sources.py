from fastapi import APIRouter

from app.services.source_health import check_mvp_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/health")
async def sources_health() -> dict:
    """Check the two read-only providers used by the MVP."""
    return await check_mvp_sources()

