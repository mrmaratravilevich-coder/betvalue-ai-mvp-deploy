from pydantic import BaseModel, ConfigDict


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    match_id: int
    market: str
    selection: str
    model_probability: float
    model_version: str
    ensemble_components: dict
    uncertainty: float | None
