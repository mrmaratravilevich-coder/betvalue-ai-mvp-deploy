"""Provider-neutral affiliate link generation and attribution metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.core.config import Settings, settings


class AffiliateConfigurationError(RuntimeError):
    """Raised when an affiliate destination is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class AffiliateContext:
    placement: str
    campaign: str = "default"
    sport: str | None = None
    match_id: int | None = None


@dataclass(frozen=True, slots=True)
class AffiliateRedirect:
    provider: str
    click_id: str
    url: str


class AffiliateProvider(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def name(self) -> str: ...

    def build_redirect(self, context: AffiliateContext) -> AffiliateRedirect: ...


class GenericAffiliateProvider:
    """Query-string provider configured entirely through environment variables."""

    def __init__(self, config: Settings = settings):
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.AFFILIATE_ENABLED and self.config.AFFILIATE_BASE_URL)

    @property
    def name(self) -> str:
        return self.config.AFFILIATE_PROVIDER.strip() or "partner"

    def _validated_base_url(self) -> str:
        value = (self.config.AFFILIATE_BASE_URL or "").strip()
        parsed = urlsplit(value)
        allowed_hosts = self.config.affiliate_allowed_hosts
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise AffiliateConfigurationError("Affiliate URL must use HTTPS")
        if not allowed_hosts or host not in allowed_hosts:
            raise AffiliateConfigurationError("Affiliate host is not allowlisted")
        return value

    def build_redirect(self, context: AffiliateContext) -> AffiliateRedirect:
        if not self.enabled:
            raise AffiliateConfigurationError("Affiliate provider is disabled")

        click_id = uuid4().hex
        parsed = urlsplit(self._validated_base_url())
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        prefix = self.config.AFFILIATE_SUB_PARAM_PREFIX.strip() or "sub"
        params.update(
            {
                self.config.AFFILIATE_CLICK_ID_PARAM: click_id,
                f"{prefix}1": context.placement,
                f"{prefix}2": context.campaign,
            }
        )
        if context.sport:
            params[f"{prefix}3"] = context.sport
        if context.match_id is not None:
            params[f"{prefix}4"] = str(context.match_id)
        if self.config.AFFILIATE_PROMO_CODE:
            params[self.config.AFFILIATE_PROMO_PARAM] = self.config.AFFILIATE_PROMO_CODE

        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), parsed.fragment))
        return AffiliateRedirect(provider=self.name, click_id=click_id, url=url)


def get_affiliate_provider() -> AffiliateProvider:
    return GenericAffiliateProvider()
