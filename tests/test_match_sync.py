from datetime import date, timedelta

import pytest

from app.services import match_ingestion


class FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_upcoming_sync_uses_bounded_windows_and_isolates_failures(monkeypatch):
    today = date(2026, 7, 28)
    db = FakeSession()
    football_calls = []
    hockey_calls = []

    async def fake_football(session, league, date_from=None, date_to=None):
        football_calls.append((league.football_data_code, date_from, date_to))
        if len(football_calls) == 1:
            raise RuntimeError("competition unavailable")
        return 2

    async def fake_hockey(session, game_date=None):
        hockey_calls.append(game_date)
        return 1

    monkeypatch.setattr(match_ingestion, "sync_football_data_league", fake_football)
    monkeypatch.setattr(match_ingestion, "sync_api_hockey_date", fake_hockey)

    result = await match_ingestion.sync_upcoming_match_window(
        db,
        today=today,
        football_days=30,
        hockey_days=3,
    )

    expected_football_calls = sum(
        bool(league.football_data_code) for league in match_ingestion.SUPPORTED_LEAGUES
    )
    assert len(football_calls) == expected_football_calls
    assert all(call[1] == today and call[2] == today + timedelta(days=30) for call in football_calls)
    assert hockey_calls == [today + timedelta(days=offset) for offset in range(4)]
    assert result["football_data_matches"] == (expected_football_calls - 1) * 2
    assert result["api_hockey_matches"] == 4
    assert result["errors"] == 1
    assert db.rollbacks == 1
