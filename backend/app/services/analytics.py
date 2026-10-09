"""Analytics: the aggregation showcase. Pipeline builders are pure functions (reused by the docs)."""

from datetime import datetime, timedelta

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core import timeutil
from app.core.errors import not_found
from app.models.analytics import (
    BusiestOut,
    ClubAnalyticsOut,
    ClubSaves,
    CountBy,
    EngagementOut,
    FunnelRow,
    FunnelTotals,
    HeatCell,
    HourCount,
    OverviewOut,
    TopEvent,
    Totals,
    WeekdayCount,
)

WEEKDAYS = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


def ratio(num: str, den: str) -> dict:
    """Safe, rounded num/den (0 when the denominator is 0)."""
    return {"$cond": [{"$gt": [f"${den}", 0]}, {"$round": [{"$divide": [f"${num}", f"${den}"]}, 4]}, 0]}


def _r(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


# ------------------------------------------------------------------ overview
def overview_pipeline() -> list[dict]:
    return [
        {
            "$facet": {
                "by_category": [
                    {"$match": {"status": "published"}},
                    {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1, "_id": 1}},
                ],
                "by_status": [
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1, "_id": 1}},
                ],
                # Computed pattern: stats.* counters make this a cheap group, no interaction scan.
                "top_clubs": [
                    {"$match": {"status": "published"}},
                    {
                        "$group": {
                            "_id": "$club_id",
                            "name": {"$first": "$club_snapshot.name"},
                            "slug": {"$first": "$club_snapshot.slug"},
                            "events": {"$sum": 1},
                            "saves": {"$sum": "$stats.saves"},
                            "views": {"$sum": "$stats.views"},
                            "registration_clicks": {"$sum": "$stats.registration_clicks"},
                        }
                    },
                    {"$sort": {"saves": -1, "name": 1}},
                    {"$limit": 10},
                ],
            }
        }
    ]


async def overview(db: AsyncDatabase) -> OverviewOut:
    facet = (await (await db.events.aggregate(overview_pipeline())).to_list(1))[0]
    totals = Totals(
        users=await db.users.estimated_document_count(),
        clubs=await db.clubs.estimated_document_count(),
        verified_clubs=await db.clubs.count_documents({"verified": True}),
        events=await db.events.estimated_document_count(),
        saved_events=await db.saved_events.estimated_document_count(),
        posts=await db.posts.count_documents({"status": "active"}),
    )
    return OverviewOut(
        totals=totals,
        events_by_category=[CountBy(key=f["_id"], count=f["count"]) for f in facet["by_category"]],
        events_by_status=[CountBy(key=f["_id"], count=f["count"]) for f in facet["by_status"]],
        top_clubs_by_saves=[
            ClubSaves(
                club_id=str(f["_id"]),
                **{k: f[k] for k in ("name", "slug", "events", "saves", "views", "registration_clicks")},
            )
            for f in facet["top_clubs"]
        ],
    )


# ------------------------------------------------------------------ engagement funnel
def engagement_pipeline(since: datetime, limit: int, club_id: ObjectId | None = None) -> list[dict]:
    def count_of(kind: str) -> dict:
        return {"$sum": {"$cond": [{"$eq": ["$_id.t", kind]}, "$n", 0]}}

    pipeline: list[dict] = [
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {"_id": {"e": "$event_id", "t": "$type"}, "n": {"$sum": 1}}},
        {
            "$group": {
                "_id": "$_id.e",
                "views": count_of("view"),
                "saves": count_of("save"),
                "clicks": count_of("registration_click"),
            }
        },
        {
            "$lookup": {
                "from": "events",
                "localField": "_id",
                "foreignField": "_id",
                "pipeline": [{"$project": {"title": 1, "club_id": 1, "club_snapshot.name": 1}}],
                "as": "event",
            }
        },
        {"$unwind": "$event"},
    ]
    if club_id is not None:
        pipeline.append({"$match": {"event.club_id": club_id}})
    pipeline.append(
        {
            "$facet": {
                "items": [
                    {
                        "$addFields": {
                            "view_to_save": ratio("saves", "views"),
                            "save_to_click": ratio("clicks", "saves"),
                            "view_to_click": ratio("clicks", "views"),
                        }
                    },
                    {"$sort": {"views": -1, "saves": -1, "_id": 1}},
                    {"$limit": limit},
                ],
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "views": {"$sum": "$views"},
                            "saves": {"$sum": "$saves"},
                            "clicks": {"$sum": "$clicks"},
                        }
                    }
                ],
            }
        }
    )
    return pipeline


async def engagement(
    db: AsyncDatabase, now: datetime, *, days: int, limit: int, club_id: ObjectId | None = None
) -> EngagementOut:
    since = now - timedelta(days=days)
    facet = (await (await db.event_interactions.aggregate(engagement_pipeline(since, limit, club_id))).to_list(1))[0]
    t = facet["totals"][0] if facet["totals"] else {"views": 0, "saves": 0, "clicks": 0}
    totals = FunnelTotals(
        views=t["views"], saves=t["saves"], registration_clicks=t["clicks"],
        view_to_save=_r(t["saves"], t["views"]), save_to_click=_r(t["clicks"], t["saves"]),
        view_to_click=_r(t["clicks"], t["views"]),
    )  # fmt: skip
    items = [
        FunnelRow(
            event_id=str(r["_id"]), title=r["event"]["title"], club_name=r["event"]["club_snapshot"]["name"],
            views=r["views"], saves=r["saves"], registration_clicks=r["clicks"],
            view_to_save=r["view_to_save"], save_to_click=r["save_to_click"], view_to_click=r["view_to_click"],
        )
        for r in facet["items"]
    ]  # fmt: skip
    return EngagementOut(days=days, totals=totals, items=items)


# ------------------------------------------------------------------ busiest days / hours
def busiest_pipeline(tz: str) -> list[dict]:
    return [
        {"$match": {"status": "published"}},
        # IST weekday and hour of the *start*, computed server-side in the app timezone.
        {
            "$addFields": {
                "dow": {"$isoDayOfWeek": {"date": "$schedule.start", "timezone": tz}},
                "hr": {"$hour": {"date": "$schedule.start", "timezone": tz}},
            }
        },
        {
            "$facet": {
                "by_weekday": [{"$group": {"_id": "$dow", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}],
                "by_hour": [{"$group": {"_id": "$hr", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}],
                "heatmap": [
                    {"$group": {"_id": {"d": "$dow", "h": "$hr"}, "count": {"$sum": 1}}},
                    {"$sort": {"_id.d": 1, "_id.h": 1}},
                ],
            }
        },
    ]


async def busiest(db: AsyncDatabase) -> BusiestOut:
    tz = timeutil.get_settings().app_timezone
    facet = (await (await db.events.aggregate(busiest_pipeline(tz))).to_list(1))[0]
    by_weekday = {f["_id"]: f["count"] for f in facet["by_weekday"]}
    return BusiestOut(
        timezone=tz,
        total_events=sum(by_weekday.values()),
        by_weekday=[WeekdayCount(weekday=d, name=WEEKDAYS[d], count=by_weekday.get(d, 0)) for d in range(1, 8)],
        by_hour=[HourCount(hour=f["_id"], count=f["count"]) for f in facet["by_hour"]],
        heatmap=[HeatCell(weekday=f["_id"]["d"], hour=f["_id"]["h"], count=f["count"]) for f in facet["heatmap"]],
    )


# ------------------------------------------------------------------ club analytics
def club_pipeline(club_id: ObjectId, now: datetime) -> list[dict]:
    return [
        {"$match": {"club_id": club_id}},
        {
            "$facet": {
                "by_status": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}, {"$sort": {"count": -1, "_id": 1}}],
                "timing": [
                    {"$match": {"status": "published"}},
                    {
                        "$group": {
                            "_id": {"$cond": [{"$gt": ["$schedule.start", now]}, "upcoming", "past"]},
                            "count": {"$sum": 1},
                        }
                    },
                ],
                "engagement": [
                    {
                        "$group": {
                            "_id": None,
                            "views": {"$sum": "$stats.views"},
                            "saves": {"$sum": "$stats.saves"},
                            "clicks": {"$sum": "$stats.registration_clicks"},
                        }
                    }
                ],
                "top": [
                    {"$sort": {"stats.saves": -1, "stats.views": -1, "_id": 1}},
                    {"$limit": 5},
                    {"$project": {"title": 1, "status": 1, "stats": 1}},
                ],
            }
        },
    ]


async def club_analytics(db: AsyncDatabase, club_id: ObjectId, now: datetime) -> ClubAnalyticsOut:
    club = await db.clubs.find_one({"_id": club_id}, {"name": 1})
    if not club:
        raise not_found("Club")
    facet = (await (await db.events.aggregate(club_pipeline(club_id, now))).to_list(1))[0]
    timing = {t["_id"]: t["count"] for t in facet["timing"]}
    e = facet["engagement"][0] if facet["engagement"] else {"views": 0, "saves": 0, "clicks": 0}
    return ClubAnalyticsOut(
        club_id=str(club_id),
        name=club["name"],
        followers=await db.users.count_documents({"followed_club_ids": club_id}),
        posts=await db.posts.count_documents({"scope.type": "club", "scope.ref_id": club_id, "status": "active"}),
        events_by_status=[CountBy(key=f["_id"], count=f["count"]) for f in facet["by_status"]],
        upcoming_published=timing.get("upcoming", 0),
        past_published=timing.get("past", 0),
        views=e["views"], saves=e["saves"], registration_clicks=e["clicks"],
        view_to_save=_r(e["saves"], e["views"]), save_to_click=_r(e["clicks"], e["saves"]),
        top_events=[
            TopEvent(
                event_id=str(t["_id"]), title=t["title"], status=t["status"], saves=t["stats"]["saves"],
                views=t["stats"]["views"], registration_clicks=t["stats"]["registration_clicks"],
            )
            for t in facet["top"]
        ],
    )  # fmt: skip
