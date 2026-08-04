import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUserData:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 600,
    now: int | None = None,
) -> TelegramUserData:
    if not init_data or len(init_data) > 16_384:
        raise TelegramAuthError("Invalid Telegram authorization data")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise TelegramAuthError("Duplicate Telegram authorization fields")
    values = dict(pairs)
    received_hash = values.pop("hash", "")
    if len(received_hash) != 64:
        raise TelegramAuthError("Invalid Telegram authorization signature")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramAuthError("Invalid Telegram authorization signature")

    try:
        auth_date = int(values["auth_date"])
        user = json.loads(values["user"])
        user_id = int(user["id"])
        first_name = str(user["first_name"]).strip()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("Incomplete Telegram authorization data") from exc

    timestamp = int(time.time()) if now is None else now
    if auth_date > timestamp + 30 or timestamp - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram authorization data has expired")
    if not first_name or len(first_name) > 128 or user_id <= 0:
        raise TelegramAuthError("Invalid Telegram user data")

    def optional_text(key: str, limit: int) -> str | None:
        value = user.get(key)
        if value is None:
            return None
        result = str(value).strip()
        return result[:limit] or None

    return TelegramUserData(
        id=user_id,
        first_name=first_name,
        last_name=optional_text("last_name", 128),
        username=optional_text("username", 64),
        language_code=optional_text("language_code", 16),
    )
