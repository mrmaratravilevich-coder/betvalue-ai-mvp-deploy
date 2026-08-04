from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services.affiliate import (
    AffiliateConfigurationError,
    AffiliateContext,
    GenericAffiliateProvider,
)


def configured_provider(**overrides) -> GenericAffiliateProvider:
    values = {
        "AFFILIATE_ENABLED": True,
        "AFFILIATE_PROVIDER": "demo",
        "AFFILIATE_BASE_URL": "https://partner.example/register?lang=ru",
        "AFFILIATE_ALLOWED_HOSTS": "partner.example",
        "AFFILIATE_PROMO_CODE": "CODE",
    }
    values.update(overrides)
    return GenericAffiliateProvider(Settings(**values))


def test_provider_builds_attributed_url_without_losing_existing_query():
    redirect = configured_provider().build_redirect(
        AffiliateContext(placement="match_card", campaign="launch", sport="football", match_id=41)
    )
    parsed = urlsplit(redirect.url)
    query = parse_qs(parsed.query)

    assert redirect.provider == "demo"
    assert parsed.hostname == "partner.example"
    assert query["lang"] == ["ru"]
    assert query["promo_code"] == ["CODE"]
    assert query["sub1"] == ["match_card"]
    assert query["sub2"] == ["launch"]
    assert query["sub3"] == ["football"]
    assert query["sub4"] == ["41"]
    assert query["click_id"] == [redirect.click_id]


def test_provider_rejects_non_allowlisted_host():
    provider = configured_provider(AFFILIATE_ALLOWED_HOSTS="approved.example")
    with pytest.raises(AffiliateConfigurationError):
        provider.build_redirect(AffiliateContext(placement="site"))


def test_provider_rejects_http_destination():
    provider = configured_provider(AFFILIATE_BASE_URL="http://partner.example/register")
    with pytest.raises(AffiliateConfigurationError):
        provider.build_redirect(AffiliateContext(placement="site"))


def test_affiliate_status_is_disabled_by_default():
    response = TestClient(app).get("/affiliate/status")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_affiliate_redirect_is_unavailable_until_configured():
    response = TestClient(app).get(
        "/affiliate/go",
        params={"placement": "match_card", "sport": "football", "match_id": 41},
        follow_redirects=False,
    )
    assert response.status_code == 503
