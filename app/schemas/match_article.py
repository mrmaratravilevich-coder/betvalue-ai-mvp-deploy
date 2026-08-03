from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MatchArticleSection(BaseModel):
    title: str
    body: str


class MatchArticleOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    match_id: int
    status: Literal["ready", "waiting"]
    title: str
    lead: str
    verdict: str
    confidence_label: str
    sections: list[MatchArticleSection]
    model_version: str | None = None
    updated_at: datetime | None = None

