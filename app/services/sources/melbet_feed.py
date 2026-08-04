"""Async client for the MELBET/Digitain Affiliate Feed API."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import msgpack

from app.core.config import Settings, settings


class MelbetFeedError(RuntimeError):
    """Raised when the feed is unavailable or returns a protocol error."""


def datetime_to_unix_ticks(value: datetime) -> int:
    """Convert a timezone-aware datetime to 100 ns ticks since Unix epoch."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 10_000_000)


def unix_ticks_to_datetime(value: int) -> datetime:
    """Convert 100 ns ticks since Unix epoch to an aware UTC datetime."""
    return datetime.fromtimestamp(int(value) / 10_000_000, tz=timezone.utc)


def messagepack_value(value: Any, key: int, default: Any = None) -> Any:
    """Read an integer-keyed MessagePack object serialized as a list or mapping."""
    if isinstance(value, (list, tuple)):
        return value[key] if 0 <= key < len(value) else default
    if isinstance(value, dict):
        return value.get(key, value.get(str(key), default))
    return default


def translated_name(value: Any, language_id: int = 1) -> str:
    """Select Russian, then English, then the first non-empty translation."""
    if not isinstance(value, dict):
        return str(value or "").strip()
    for key in (language_id, str(language_id), 1, "1", 2, "2"):
        translated = value.get(key)
        if translated:
            return str(translated).strip()
    return next((str(item).strip() for item in value.values() if item), "")


class MelbetFeedClient:
    """OAuth2 client with token caching and MessagePack response decoding."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self._access_token: str | None = None
        self._token_type = "Bearer"
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(
            self.config.MELBET_FEED_ENABLED
            and self.config.MELBET_FEED_CLIENT_ID
            and self.config.MELBET_FEED_CLIENT_SECRET
        )

    @property
    def base_url(self) -> str:
        return self.config.MELBET_FEED_BASE_URL.rstrip("/")

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        if not self.config.MELBET_FEED_CLIENT_ID or not self.config.MELBET_FEED_CLIENT_SECRET:
            raise MelbetFeedError("MELBET feed credentials are not configured")
        async with self._token_lock:
            if self._access_token and time.monotonic() < self._token_expires_at:
                return f"{self._token_type} {self._access_token}"
            response = await client.post(
                f"{self.base_url}/connect/token",
                data={
                    "client_id": self.config.MELBET_FEED_CLIENT_ID,
                    "client_secret": self.config.MELBET_FEED_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise MelbetFeedError("MELBET OAuth response did not contain an access token")
            self._access_token = str(token)
            self._token_type = str(payload.get("token_type") or "Bearer")
            expires_in = max(int(payload.get("expires_in") or 3600), 60)
            self._token_expires_at = time.monotonic() + expires_in - 30
            return f"{self._token_type} {self._access_token}"

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        response.raise_for_status()
        try:
            payload = msgpack.unpackb(response.content, raw=False, strict_map_key=False)
        except (ValueError, msgpack.ExtraData) as exc:
            raise MelbetFeedError("MELBET feed returned invalid MessagePack") from exc

        result = messagepack_value(payload, 0)
        error = messagepack_value(payload, 1)
        if error:
            code = messagepack_value(error, 0, "unknown")
            name = messagepack_value(error, 1, "FeedError")
            raise MelbetFeedError(f"MELBET feed error {code}: {name}")
        return result

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: list[tuple[str, str | int]] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self.configured:
            raise MelbetFeedError("MELBET feed is disabled or not configured")
        async with httpx.AsyncClient(timeout=45, transport=self.transport) as client:
            authorization = await self._authenticate(client)
            response = await client.request(
                method,
                f"{self.base_url}/api/v1/AffiliateFeed/{endpoint}",
                params=params,
                json=json,
                headers={
                    "Authorization": authorization,
                    "Accept": "application/x-msgpack",
                },
            )
        return self._decode_response(response)

    async def fetch_sports(
        self,
        start: datetime,
        end: datetime,
        language_ids: list[int] | None = None,
    ) -> list[Any]:
        params: list[tuple[str, str | int]] = [
            ("startDate", datetime_to_unix_ticks(start)),
            ("endDate", datetime_to_unix_ticks(end)),
        ]
        params.extend(("lId", item) for item in (language_ids or [1, 2]))
        return list(await self._request("GET", "GetSports", params=params) or [])

    async def fetch_prematch_events(
        self,
        start: datetime,
        end: datetime,
        *,
        tournament_ids: list[int],
        stake_type_ids: list[int],
        language_ids: list[int] | None = None,
        include_periods: bool = False,
    ) -> list[Any]:
        if not tournament_ids or len(tournament_ids) > 10:
            raise ValueError("MELBET prematch requests require between 1 and 10 tournament IDs")
        if not stake_type_ids or len(stake_type_ids) > 10:
            raise ValueError("MELBET prematch requests require between 1 and 10 stake type IDs")
        payload = {
            "startDate": datetime_to_unix_ticks(start),
            "endDate": datetime_to_unix_ticks(end),
            "LangIds": language_ids or [1, 2],
            "TournamentIds": tournament_ids,
            "StakeTypeIds": stake_type_ids,
            "IncludePeriods": include_periods,
        }
        return list(await self._request("POST", "GetPrematchEvents", json=payload) or [])

    async def fetch_live_events(
        self,
        *,
        tournament_ids: list[int],
        stake_type_ids: list[int],
        language_ids: list[int] | None = None,
        include_periods: bool = False,
    ) -> list[Any]:
        if not tournament_ids or len(tournament_ids) > 10:
            raise ValueError("MELBET live requests require between 1 and 10 tournament IDs")
        if not stake_type_ids or len(stake_type_ids) > 10:
            raise ValueError("MELBET live requests require between 1 and 10 stake type IDs")
        payload = {
            "LangIds": language_ids or [1, 2],
            "TournamentIds": tournament_ids,
            "StakeTypeIds": stake_type_ids,
            "IncludePeriods": include_periods,
        }
        return list(await self._request("POST", "GetLiveEvents", json=payload) or [])
