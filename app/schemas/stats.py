from pydantic import BaseModel


class EVDistributionBucket(BaseModel):
    ev_range: str   # напр. "5-10%"
    count: int


class LeagueHeatmapEntry(BaseModel):
    league_name: str
    roi: float
    bets_count: int


class StatsOut(BaseModel):
    """
    Блок 'Аналитика' из ТЗ. На старте, пока не подключён источник реальных
    коэффициентов, большинство полей возвращаются нулевыми/пустыми —
    структура готова к наполнению, когда появятся закрывающие линии (CLV).
    """

    roi: float = 0.0
    yield_pct: float = 0.0
    clv_avg: float | None = None
    drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None
    ev_distribution: list[EVDistributionBucket] = []
    league_heatmap: list[LeagueHeatmapEntry] = []
