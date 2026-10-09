from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.common import Page
from app.models.events import EventCard


class Facets(BaseModel):
    """Counts by id. Each group's counts ignore that group's own filter (so a selection can be widened)."""

    category: dict[str, int]
    club: dict[str, int]  # keyed by club id


class CataloguePage(Page[EventCard]):
    facets: Facets


class EventList(BaseModel):
    items: list[EventCard]


class ScoredEventCard(EventCard):
    score: float
    score_breakdown: dict[str, float]  # weighted contribution of each term; the values sum to `score`
    components: dict[str, float] = {}  # the normalised 0..1 inputs before weighting


class RankedWindow(BaseModel):
    saves: int
    views: int
    registration_clicks: int


class RankedEventCard(ScoredEventCard):
    rank: int
    window: RankedWindow  # engagement counted inside the ranking window


class TopEventsOut(BaseModel):
    window_days: int
    disclaimer: str
    items: list[RankedEventCard]


class SuggestedOut(BaseModel):
    personalised: bool
    items: list[ScoredEventCard]


class FeaturedCard(EventCard):
    source: Literal["featured", "fallback"]


class RankingConfigOut(BaseModel):
    weights: dict[str, float]
    window_days: int
    updated_at: datetime | None
    formula: dict[str, str]
    disclaimer: str
