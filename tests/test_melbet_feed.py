from datetime import datetime, timezone

import httpx
import msgpack
import pytest

from app.core.config import Settings
from app.models.enums import MarketCode
from app.services.melbet_feed_ingestion import normalize_prematch_event
from app.services.sources.melbet_feed import (
    MelbetFeedClient,
    MelbetFeedError,
    datetime_to_unix_ticks,
    unix_ticks_to_datetime,
)


def configured_settings(**overrides) -> Settings:
    values = {
        "MELBET_FEED_ENABLED": True,
        "MELBET_FEED_BASE_URL": "https://feed.example",
        "MELBET_FEED_CLIENT_ID": "client",
        "MELBET_FEED_CLIENT_SECRET": "secret",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_client_authenticates_decodes_messagepack_and_reuses_token():
    calls = {"auth": 0, "sports": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/token":
            calls["auth"] += 1
            assert b"client_secret=secret" in request.content
            return httpx.Response(
                200,
                json={"token_type": "Bearer", "access_token": "token", "expires_in": 3600},
            )
        calls["sports"] += 1
        assert request.headers["authorization"] == "Bearer token"
        payload = [[[1, {1: "Футбол", 2: "Football"}]], None]
        return httpx.Response(200, content=msgpack.packb(payload, use_bin_type=True))

    client = MelbetFeedClient(configured_settings(), transport=httpx.MockTransport(handler))
    start = datetime(2026, 8, 4, tzinfo=timezone.utc)
    assert len(await client.fetch_sports(start, start)) == 1
    assert len(await client.fetch_sports(start, start)) == 1
    assert calls == {"auth": 1, "sports": 2}


@pytest.mark.asyncio
async def test_client_raises_feed_error_from_messagepack_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/token":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(200, content=msgpack.packb([None, [8, "TooManyTournamentIds"]]))

    client = MelbetFeedClient(configured_settings(), transport=httpx.MockTransport(handler))
    now = datetime.now(timezone.utc)
    with pytest.raises(MelbetFeedError, match="TooManyTournamentIds"):
        await client.fetch_prematch_events(
            now,
            now,
            tournament_ids=[4485],
            stake_type_ids=[1],
        )


@pytest.mark.asyncio
async def test_client_enforces_feed_batch_limits_before_network_call():
    client = MelbetFeedClient(configured_settings())
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="between 1 and 10 tournament"):
        await client.fetch_prematch_events(
            now,
            now,
            tournament_ids=list(range(11)),
            stake_type_ids=[1],
        )


def test_tick_conversion_round_trip():
    value = datetime(2026, 8, 4, 12, 30, 15, 123456, tzinfo=timezone.utc)
    restored = unix_ticks_to_datetime(datetime_to_unix_ticks(value))
    assert abs((restored - value).total_seconds()) < 0.000001


def test_normalize_prematch_event_maps_core_markets():
    raw = [None] * 36
    raw[0] = 991
    raw[2] = {1: "Зенит", 2: "Zenit"}
    raw[3] = {1: "Спартак", 2: "Spartak"}
    raw[5] = 4485
    raw[7] = datetime_to_unix_ticks(datetime(2026, 8, 5, 17, tzinfo=timezone.utc))
    raw[11] = [
        [1, 1, 1, {2: "Zenit"}, 1.8, None, False, 0],
        [2, 1, 2, {2: "Draw"}, 3.4, None, False, 0],
        [3, 1, 3, {2: "Spartak"}, 4.5, None, False, 0],
        [4, 3, 1, {2: "Over"}, 1.9, 2.5, True, 0],
        [5, 3, 2, {2: "Under"}, 1.95, 2.5, True, 0],
        [6, 26, 1, {2: "Yes"}, 2.05, None, False, 0],
        [7, 37, 1, {2: "1X"}, 1.25, None, False, 0],
    ]
    raw[33] = {1: "Тестовая лига", 2: "Test League"}
    raw[34] = {1: "Россия", 2: "Russia"}
    raw[35] = 1

    event = normalize_prematch_event(raw)

    assert event.event_id == "991"
    assert event.home_name == "Зенит"
    assert event.tournament_id == 4485
    assert [(quote.market, quote.selection) for quote in event.quotes] == [
        (MarketCode.MATCH_WINNER, "home"),
        (MarketCode.MATCH_WINNER, "draw"),
        (MarketCode.MATCH_WINNER, "away"),
        (MarketCode.TOTAL_OVER, "over_2.5"),
        (MarketCode.TOTAL_UNDER, "under_2.5"),
        (MarketCode.BTTS, "yes"),
        (MarketCode.DOUBLE_CHANCE, "1x"),
    ]
