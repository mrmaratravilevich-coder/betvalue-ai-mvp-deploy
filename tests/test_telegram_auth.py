import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from app.services.telegram_auth import TelegramAuthError, validate_init_data


def signed_init_data(token: str, *, auth_date: int = 1_700_000_000) -> str:
    values = {
        "auth_date": str(auth_date),
        "query_id": "AAE-test",
        "user": json.dumps(
            {
                "id": 8876258961,
                "first_name": "Марат",
                "username": "analyst",
                "language_code": "ru",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_validate_init_data_returns_verified_user():
    payload = signed_init_data("bot-token")

    user = validate_init_data(payload, "bot-token", now=1_700_000_100)

    assert user.id == 8876258961
    assert user.first_name == "Марат"
    assert user.username == "analyst"


def test_validate_init_data_rejects_wrong_signature():
    payload = signed_init_data("bot-token")

    with pytest.raises(TelegramAuthError, match="signature"):
        validate_init_data(payload, "other-token", now=1_700_000_100)


def test_validate_init_data_rejects_expired_payload():
    payload = signed_init_data("bot-token")

    with pytest.raises(TelegramAuthError, match="expired"):
        validate_init_data(payload, "bot-token", now=1_700_001_000)
