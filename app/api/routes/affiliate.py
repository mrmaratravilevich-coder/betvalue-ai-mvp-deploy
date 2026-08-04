import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.schemas.affiliate import AffiliateStatusOut
from app.services.affiliate import (
    AffiliateConfigurationError,
    AffiliateContext,
    AffiliateProvider,
    get_affiliate_provider,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/affiliate", tags=["affiliate"])
SAFE_LABEL = re.compile(r"^[a-z0-9_-]{1,48}$")


def _safe_label(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if not SAFE_LABEL.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"Invalid {field}")
    return normalized


@router.get("/status", response_model=AffiliateStatusOut)
async def affiliate_status(
    provider: AffiliateProvider = Depends(get_affiliate_provider),
) -> AffiliateStatusOut:
    config = getattr(provider, "config", None)
    return AffiliateStatusOut(
        enabled=provider.enabled,
        provider=provider.name,
        promo_available=bool(getattr(config, "AFFILIATE_PROMO_CODE", None)),
    )


@router.get("/go", include_in_schema=False)
async def affiliate_redirect(
    placement: str = Query(min_length=1, max_length=48),
    campaign: str = Query(default="default", min_length=1, max_length=48),
    sport: str | None = Query(default=None, max_length=48),
    match_id: int | None = Query(default=None, gt=0),
    provider: AffiliateProvider = Depends(get_affiliate_provider),
) -> RedirectResponse:
    context = AffiliateContext(
        placement=_safe_label(placement, "placement"),
        campaign=_safe_label(campaign, "campaign"),
        sport=_safe_label(sport, "sport") if sport else None,
        match_id=match_id,
    )
    try:
        redirect = provider.build_redirect(context)
    except AffiliateConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Affiliate offer is unavailable",
        ) from exc

    logger.info(
        "Affiliate click provider=%s click_id=%s placement=%s campaign=%s sport=%s match_id=%s",
        redirect.provider,
        redirect.click_id,
        context.placement,
        context.campaign,
        context.sport,
        context.match_id,
    )
    return RedirectResponse(redirect.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
