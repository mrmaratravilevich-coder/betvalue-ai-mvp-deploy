from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.prediction_engine import generate_predictions_all_leagues


@pytest.mark.asyncio
async def test_global_prediction_run_selects_only_football_leagues() -> None:
    league = MagicMock()
    league.id = 42
    league.name = "Премьер-лига"

    scalars = MagicMock()
    scalars.all.return_value = [league]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    db = AsyncMock()
    db.execute.return_value = execute_result

    with patch(
        "app.services.prediction_engine.generate_predictions_for_league",
        new=AsyncMock(return_value=1),
    ) as generate:
        result = await generate_predictions_all_leagues(db)

    statement = db.execute.await_args.args[0]
    assert "sports.code = :code_1" in str(statement)
    assert statement.compile().params["code_1"] == "football"
    generate.assert_awaited_once_with(db, 42)
    assert result == {"Премьер-лига": 1}
