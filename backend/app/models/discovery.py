from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import Page
from app.models.events import EventCard


class CategoryFacet(BaseModel):
    value: str
    count: int


class ClubFacet(BaseModel):
    id: str
    name: str
    slug: str
    count: int


class Facets(BaseModel):
    categories: list[CategoryFacet]
    clubs: list[ClubFacet]


class CataloguePage(Page[EventCard]):
    facets: Facets


class EventList(BaseModel):
    items: list[EventCard]


class ScoreBreakdown(BaseModel):
    components: dict[str, float]  # normalised 0..1 inputs
    contributions: dict[str, float]  # weight * component; they sum to `score`


class ScoredEventCard(EventCard):
    score: float
    score_breakdown: ScoreBreakdown


class RankedEventCard(ScoredEventCard):
    rank: int


class TopEventsOut(BaseModel):
    window_days: int
    disclaimer: str
    items: list[RankedEventCard]


class SuggestedOut(BaseModel):
    personalized: bool
    items: list[ScoredEventCard]


class FeaturedOut(BaseModel):
    source: Literal["featured", "fallback", "none"]
    event: EventCard | None


class RankingConfigOut(BaseModel):
    weights: dict[str, float]
    window_days: int
    updated_at: datetime | None
    formula: dict[str, str]
    disclaimer: str
