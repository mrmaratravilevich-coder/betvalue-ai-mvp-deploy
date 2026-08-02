from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QualityMetrics(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    evaluated_matches: int
    accuracy: float | None = None
    brier_score: float | None = None
    log_loss: float | None = None
    calibration_error: float | None = None


class LeagueQuality(QualityMetrics):
    league_id: int
    league_name: str


class QualityWindow(BaseModel):
    days: int
    from_date: datetime
    to_date: datetime
    overall: QualityMetrics
    leagues: list[LeagueQuality]


class ModelQualityOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    generated_at: datetime
    model_version: str
    windows: list[QualityWindow]
