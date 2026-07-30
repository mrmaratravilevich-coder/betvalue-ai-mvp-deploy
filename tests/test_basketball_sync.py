from datetime import datetime, timezone

from app.models.enums import MatchStatus
from app.services.match_ingestion import normalize_basketball_game


def test_normalize_basketball_game() -> None:
    raw = {
        "id": 494977,
        "timestamp": 1785283200,
        "week": "Round 7",
        "status": {"short": "FT"},
        "league": {"id": 13, "name": "NBA W", "season": 2026},
        "country": {"name": "USA"},
        "teams": {
            "home": {"id": 169, "name": "Minnesota Lynx W"},
            "away": {"id": 7870, "name": "Toronto Tempo W"},
        },
        "scores": {
            "home": {"total": 100},
            "away": {"total": 93},
        },
    }

    game = normalize_basketball_game(raw)

    assert game["external_id"] == "494977"
    assert game["kickoff_at"] == datetime.fromtimestamp(1785283200, tz=timezone.utc)
    assert game["status"] == MatchStatus.FINISHED
    assert game["home_score"] == 100
    assert game["away_score"] == 93
