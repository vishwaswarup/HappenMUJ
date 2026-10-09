from typing import Annotated

from fastapi import APIRouter, Query

from app.core import timeutil
from app.core.deps import DB, OptionalUser
from app.models.discovery import EventList, FeaturedOut, RankingConfigOut, SuggestedOut, TopEventsOut
from app.services import discovery
from app.services.settings import get_ranking_settings

router = APIRouter(prefix="/home", tags=["home"])
Limit = Annotated[int, Query(ge=1, le=50)]


@router.get(
    "/featured", response_model=FeaturedOut, summary="Platform-admin featured event (fallback: soonest with poster)"
)
async def featured(db: DB, user: OptionalUser) -> FeaturedOut:
    return await discovery.featured(db, user, timeutil.now())


@router.get(
    "/suggested",
    response_model=SuggestedOut,
    summary="Logged in: rule-based score from interests/categories/clubs. Anonymous: upcoming by popularity",
)
async def suggested(db: DB, user: OptionalUser, limit: Limit = 10) -> SuggestedOut:
    personalized, items = await discovery.suggested(db, user, timeutil.now(), limit)
    return SuggestedOut(personalized=personalized, items=items)


@router.get("/top-events", response_model=TopEventsOut, summary="Top 10 events to participate in (windowed engagement)")
async def top_events(db: DB, user: OptionalUser) -> TopEventsOut:
    cfg = await get_ranking_settings(db)
    items = await discovery.top_events(db, user, timeutil.now())
    return TopEventsOut(window_days=cfg["window_days"], disclaimer=discovery.DISCLAIMER, items=items)


@router.get("/top-events/config", response_model=RankingConfigOut, summary="The ranking weights, in the open")
async def top_events_config(db: DB) -> RankingConfigOut:
    cfg = await get_ranking_settings(db)
    return RankingConfigOut(
        weights=cfg["weights"], window_days=cfg["window_days"], updated_at=cfg.get("updated_at"),
        formula={
            "saves": "saves in window / max saves in window across eligible events",
            "views": "views in window / max views in window",
            "clicks": "registration clicks in window / max registration clicks in window",
            "proximity": "exp(-days_until_start / 7)",
            "urgency": "1.0 if registration deadline within 72h; 0.5 if registration required and open; else 0",
            "score": "sum of weight * component",
        },
        disclaimer=discovery.DISCLAIMER,
    )  # fmt: skip


@router.get("/next-7-days", response_model=EventList, summary="[now, 00:00 IST today+7d), chronological")
async def next_7_days(db: DB, user: OptionalUser, limit: Limit = 50) -> EventList:
    now = timeutil.now()
    start, end = timeutil.next_7_days_range(now)
    return EventList(items=await discovery.in_range(db, user, now, start, end, limit))


@router.get("/tomorrow", response_model=EventList, summary="Tomorrow in IST; an empty list is a valid answer")
async def tomorrow(db: DB, user: OptionalUser, limit: Limit = 50) -> EventList:
    now = timeutil.now()
    start, end = timeutil.tomorrow_range(now)
    return EventList(items=await discovery.in_range(db, user, now, start, end, limit))
