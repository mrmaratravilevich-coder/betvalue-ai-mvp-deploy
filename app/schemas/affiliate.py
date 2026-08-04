from pydantic import BaseModel


class AffiliateStatusOut(BaseModel):
    enabled: bool
    provider: str
    promo_available: bool
