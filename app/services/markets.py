"""Справочник рынков ставок (см. app/models/enums.MarketCode) + upsert-хелпер."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MarketCode
from app.models.odds import Market

MARKET_NAMES: dict[MarketCode, str] = {
    MarketCode.MATCH_WINNER: "Победа",
    MarketCode.DOUBLE_CHANCE: "Двойной шанс",
    MarketCode.TOTAL_OVER: "Тотал больше",
    MarketCode.TOTAL_UNDER: "Тотал меньше",
    MarketCode.BTTS: "Обе забьют",
    MarketCode.HANDICAP: "Фора",
    MarketCode.TEAM_TOTAL: "Индивидуальный тотал",
}


async def get_or_create_market(db: AsyncSession, code: MarketCode) -> Market:
    result = await db.execute(select(Market).where(Market.code == code))
    market = result.scalar_one_or_none()
    if market is None:
        market = Market(code=code, name=MARKET_NAMES[code])
        db.add(market)
        await db.flush()
    return market


async def seed_markets(db: AsyncSession) -> dict[MarketCode, Market]:
    markets = {}
    for code in MarketCode:
        markets[code] = await get_or_create_market(db, code)
    await db.commit()
    return markets
