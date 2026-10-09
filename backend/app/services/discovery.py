"""Discovery pipelines: catalogue (with $facet), featured, Top 10, Suggested, date-range lists.

Pipeline *builders* are pure functions (no DB access) so docs/tests can print and ``explain()`` them.
Every one starts from ``public_filter()``: cancelled/draft/pending/rejected events never leak.
"""

from datetime import date, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core import timeutil
from app.core.errors import AppError
from app.models.discovery import (
    CategoryFacet,
    ClubFacet,
    Facets,
    FeaturedOut,
    RankedEventCard,
    ScoreBreakdown,
    ScoredEventCard,
)
from app.models.events import EventCard
from app.services.event_view import to_card
from app.services.settings import get_ranking_settings
from app.services.visibility import public_filter
from app.validators import CATEGORIES

DISCLAIMER = (
    "This ranking reflects student engagement (saves, views, registration clicks) and event timing. "
    "It is not an official endorsement by the university or any club."
)
# Fields a card never needs; dropped in the pipeline so large text never leaves the database.
CARD_EXCLUDE = {"description": 0, "details": 0, "contact": 0, "change_log": 0}
SUGGEST_WEIGHTS = {"interest": 0.35, "category": 0.20, "club": 0.20, "date": 0.15, "deadline": 0.10}


# ------------------------------------------------------------------ shared expressions
def registration_open_expr(now: datetime) -> dict:
    """required AND (deadline is null OR deadline > now) AND start > now."""
    return {
        "$and": [
            {"$eq": ["$registration.required", True]},
            {
                "$or": [
                    {"$eq": [{"$ifNull": ["$registration.deadline", None]}, None]},
                    {"$gt": ["$registration.deadline", now]},
                ]
            },
            {"$gt": ["$schedule.start", now]},
        ]
    }


def popularity_expr() -> dict:
    """General (all-time) popularity from the embedded computed counters."""
    return {
        "$add": [
            {"$multiply": [{"$ifNull": ["$stats.saves", 0]}, 3]},
            {"$multiply": [{"$ifNull": ["$stats.registration_clicks", 0]}, 2]},
            {"$ifNull": ["$stats.views", 0]},
        ]
    }


def eligible_filter(now: datetime) -> dict:
    """Public, not started, and (if registration is required) deadline not passed."""
    return public_filter(
        **{
            "schedule.start": {"$gt": now},
            "$or": [
                {"registration.required": {"$ne": True}},
                {"registration.deadline": None},
                {"registration.deadline": {"$gt": now}},
            ],
        }
    )


def card_tail(now: datetime) -> list[dict]:
    return [{"$addFields": {"registration_open": registration_open_expr(now)}}, {"$project": CARD_EXCLUDE}]


def _days_until(now: datetime) -> dict:
    return {"$divide": [{"$subtract": ["$schedule.start", now]}, 86_400_000]}


def _decay(now: datetime, scale: float) -> dict:
    """exp(-days_until_start / scale): sooner = closer to 1."""
    return {"$exp": {"$divide": [{"$multiply": [-1, _days_until(now)]}, scale]}}


# ------------------------------------------------------------------ Top 10
def top_events_pipeline(now: datetime, weights: dict[str, float], window_days: int, limit: int = 10) -> list[dict]:
    since = now - timedelta(days=window_days)

    def in_window(kind: str) -> dict:
        return {
            "$sum": {
                "$map": {
                    "input": {"$filter": {"input": "$ix", "cond": {"$eq": ["$$this._id", kind]}}},
                    "in": "$$this.n",
                }
            }
        }

    def norm(num: str, den: str) -> dict:
        return {"$cond": [{"$gt": [f"${den}", 0]}, {"$divide": [f"${num}", f"${den}"]}, 0]}

    w = weights
    return [
        {"$match": eligible_filter(now)},
        # Engagement only from the last `window_days`: old views cannot dominate.
        {
            "$lookup": {
                "from": "event_interactions",
                "localField": "_id",
                "foreignField": "event_id",
                "pipeline": [{"$match": {"ts": {"$gte": since}}}, {"$group": {"_id": "$type", "n": {"$sum": 1}}}],
                "as": "ix",
            }
        },
        {
            "$addFields": {
                "w_saves": in_window("save"),
                "w_views": in_window("view"),
                "w_clicks": in_window("registration_click"),
            }
        },
        # Max-normalisation across the whole eligible set (one partition, unbounded window).
        {
            "$setWindowFields": {
                "output": {
                    f"max_{k}": {"$max": f"$w_{k}", "window": {"documents": ["unbounded", "unbounded"]}}
                    for k in ("saves", "views", "clicks")
                }
            }
        },
        {
            "$addFields": {
                "components": {
                    "saves": norm("w_saves", "max_saves"),
                    "views": norm("w_views", "max_views"),
                    "clicks": norm("w_clicks", "max_clicks"),
                    "proximity": _decay(now, 7),
                    "urgency": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$eq": ["$registration.required", True]},
                                    {"$ne": [{"$ifNull": ["$registration.deadline", None]}, None]},
                                    {"$lte": ["$registration.deadline", now + timedelta(hours=72)]},
                                ]
                            },
                            1.0,
                            {"$cond": [{"$eq": ["$registration.required", True]}, 0.5, 0]},
                        ]
                    },
                }
            }
        },
        {
            "$addFields": {
                "contributions": {k: {"$multiply": [w[k], f"$components.{k}"]} for k in w},
            }
        },
        {
            "$addFields": {
                "score": {"$add": [f"$contributions.{k}" for k in w]},
            }
        },
        {"$sort": {"score": -1, "schedule.start": 1, "_id": 1}},
        {"$limit": limit},
        *card_tail(now),
        {"$project": {f: 0 for f in ("ix", "w_saves", "w_views", "w_clicks", "max_saves", "max_views", "max_clicks")}},
    ]  # fmt: skip


# ------------------------------------------------------------------ Suggested
def suggested_pipeline(now: datetime, user: dict, exclude_ids: list[ObjectId], limit: int = 10) -> list[dict]:
    interests = user.get("interests", [])
    prefs = user.get("preferred_categories", [])
    followed = user.get("followed_club_ids", [])
    w = SUGGEST_WEIGHTS
    match = eligible_filter(now)
    if exclude_ids:
        match["_id"] = {"$nin": exclude_ids}
    return [
        {"$match": match},
        {
            "$addFields": {
                "components": {
                    # |tags ∩ interests| / max(1, |interests|); both sides are lower-cased on write.
                    "interest": {
                        "$divide": [
                            {"$size": {"$setIntersection": [{"$ifNull": ["$tags", []]}, interests]}},
                            max(1, len(interests)),
                        ]
                    },
                    "category": {"$cond": [{"$in": ["$category", prefs]}, 1, 0]},
                    "club": {"$cond": [{"$in": ["$club_id", followed]}, 1, 0]},
                    "date": _decay(now, 10),
                    "deadline": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$eq": ["$registration.required", True]},
                                    {"$ne": [{"$ifNull": ["$registration.deadline", None]}, None]},
                                    {"$gt": ["$registration.deadline", now]},
                                    {"$lte": ["$registration.deadline", now + timedelta(days=5)]},
                                ]
                            },
                            1,
                            0,
                        ]
                    },
                }
            }
        },
        {"$addFields": {"contributions": {k: {"$multiply": [w[k], f"$components.{k}"]} for k in w}}},
        {"$addFields": {"score": {"$add": [f"$contributions.{k}" for k in w]}}},
        {"$sort": {"score": -1, "schedule.start": 1, "_id": 1}},
        {"$limit": limit},
        *card_tail(now),
    ]  # fmt: skip


def popular_upcoming_pipeline(now: datetime, exclude_ids: list[ObjectId], limit: int = 10) -> list[dict]:
    """Anonymous / no-signal fallback: upcoming events by general popularity."""
    match = eligible_filter(now)
    if exclude_ids:
        match["_id"] = {"$nin": exclude_ids}
    return [
        {"$match": match},
        {"$addFields": {"popularity": popularity_expr()}},
        {"$sort": {"popularity": -1, "schedule.start": 1, "_id": 1}},
        {"$limit": limit},
        *card_tail(now),
        {"$project": {"popularity": 0}},
    ]


# ------------------------------------------------------------------ date-range lists
def range_pipeline(now: datetime, start: datetime, end: datetime, limit: int) -> list[dict]:
    """Public events whose start is in [start, end), chronological; NOT reordered by registration state."""
    return [
        {"$match": public_filter(**{"schedule.start": {"$gte": start, "$lt": end}})},
        {"$sort": {"schedule.start": 1, "_id": 1}},
        {"$limit": limit},
        *card_tail(now),
    ]


# ------------------------------------------------------------------ catalogue
def catalogue_pipeline(
    now: datetime, *, q: str | None, categories: list[str], club_ids: list[ObjectId] | None,
    date_from: date | None, date_to: date | None, sort: str, skip: int, limit: int,
) -> list[dict]:  # fmt: skip
    base = public_filter()
    if date_from or date_to:
        rng: dict[str, datetime] = {}
        if date_from:
            rng["$gte"] = timeutil.ist_day_range(date_from)[0]
        if date_to:
            rng["$lt"] = timeutil.ist_day_range(date_to)[1]
        base["schedule.start"] = rng
    else:
        base["schedule.end"] = {"$gte": now}  # default: upcoming + ongoing (completed is derived)
    if q:
        base["$text"] = {"$search": q}
    cat_f = {"category": {"$in": categories}} if categories else {}
    club_f = {"club_id": {"$in": club_ids}} if club_ids is not None else {}

    def m(*filters: dict) -> list[dict]:
        merged = {k: v for f in filters for k, v in f.items()}
        return [{"$match": merged}] if merged else []

    sort_spec = {
        "date": {"schedule.start": 1, "_id": 1},
        "popularity": {"popularity": -1, "schedule.start": 1, "_id": 1},
        "relevance": {"_text_score": -1, "schedule.start": 1, "_id": 1},
    }[sort]
    pipeline: list[dict] = [{"$match": base}]  # $text must be in the first stage
    if q:
        pipeline.append({"$addFields": {"_text_score": {"$meta": "textScore"}}})
    pipeline.append(
        {
            "$facet": {
                # OR within a group, AND between groups: category $in AND club $in.
                "items": [
                    *m(cat_f, club_f),
                    {"$addFields": {"popularity": popularity_expr()}},
                    {"$sort": sort_spec},
                    {"$skip": skip},
                    {"$limit": limit},
                    *card_tail(now),
                    {"$project": {"popularity": 0, "_text_score": 0}},
                ],
                "total": [*m(cat_f, club_f), {"$count": "n"}],
                # Disjunctive facets: each group's counts ignore its own filter so users can widen a selection.
                "by_category": [
                    *m(club_f),
                    {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1, "_id": 1}},
                ],
                "by_club": [
                    *m(cat_f),
                    {
                        "$group": {
                            "_id": "$club_id",
                            "name": {"$first": "$club_snapshot.name"},
                            "slug": {"$first": "$club_snapshot.slug"},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1, "name": 1}},
                ],
            }
        }
    )
    return pipeline


# ------------------------------------------------------------------ service functions
async def agg(db: AsyncDatabase, pipeline: list[dict], n: int) -> list[dict]:
    """Run an aggregation on ``events`` (async PyMongo: aggregate() is awaited to get the cursor)."""
    return await (await db.events.aggregate(pipeline)).to_list(n)


async def saved_flags(db: AsyncDatabase, user: dict | None, event_ids: list[ObjectId]) -> set[ObjectId] | None:
    """Which of these events the user saved; None when anonymous (is_saved is omitted)."""
    if user is None:
        return None
    rows = await db.saved_events.find(
        {"user_id": user["_id"], "event_id": {"$in": event_ids}}, {"event_id": 1}
    ).to_list(None)
    return {r["event_id"] for r in rows}


async def to_cards(db: AsyncDatabase, docs: list[dict], user: dict | None, now: datetime) -> list[EventCard]:
    saved = await saved_flags(db, user, [d["_id"] for d in docs])
    return [to_card(d, now, None if saved is None else d["_id"] in saved) for d in docs]


def _breakdown(doc: dict) -> ScoreBreakdown:
    r = lambda d: {k: round(float(v), 4) for k, v in d.items()}  # noqa: E731
    return ScoreBreakdown(components=r(doc["components"]), contributions=r(doc["contributions"]))


async def _scored(db, docs, user, now, ranked: bool):
    cards = await to_cards(db, docs, user, now)
    out = []
    for i, (card, doc) in enumerate(zip(cards, docs, strict=True), start=1):
        extra: dict[str, Any] = {"score": round(float(doc["score"]), 4), "score_breakdown": _breakdown(doc)}
        if ranked:
            out.append(RankedEventCard(**card.model_dump(), rank=i, **extra))
        else:
            out.append(ScoredEventCard(**card.model_dump(), **extra))
    return out


async def top_events(db: AsyncDatabase, user: dict | None, now: datetime) -> list[RankedEventCard]:
    cfg = await get_ranking_settings(db)
    docs = await agg(db, top_events_pipeline(now, cfg["weights"], cfg["window_days"]), 10)
    return await _scored(db, docs, user, now, ranked=True)  # fewer than 10 is fine: no padding


def has_signal(user: dict) -> bool:
    return bool(user.get("interests") or user.get("preferred_categories") or user.get("followed_club_ids"))


async def suggested(
    db: AsyncDatabase, user: dict | None, now: datetime, limit: int
) -> tuple[bool, list[ScoredEventCard]]:
    saved_ids: list[ObjectId] = []
    if user is not None:
        rows = await db.saved_events.find({"user_id": user["_id"]}, {"event_id": 1}).to_list(None)
        saved_ids = [r["event_id"] for r in rows]
    if user is not None and has_signal(user):
        docs = await agg(db, suggested_pipeline(now, user, saved_ids, limit), limit)
        return True, await _scored(db, docs, user, now, ranked=False)
    docs = await agg(db, popular_upcoming_pipeline(now, saved_ids, limit), limit)
    cards = await to_cards(db, docs, user, now)
    zero = ScoreBreakdown(components={}, contributions={})
    return False, [ScoredEventCard(**c.model_dump(), score=0.0, score_breakdown=zero) for c in cards]


async def featured(db: AsyncDatabase, user: dict | None, now: datetime) -> FeaturedOut:
    pipe = [
        {"$match": public_filter(**{"featured.is_featured": True, "schedule.start": {"$gt": now}})},
        {"$sort": {"featured.featured_at": -1}},
        {"$limit": 1},
        *card_tail(now),
    ]
    docs = await agg(db, pipe, 1)
    source = "featured"
    if not docs:
        source = "fallback"  # soonest upcoming event with a poster and open registration
        pipe = [
            {"$match": eligible_filter(now) | {"poster_file_id": {"$ne": None}, "registration.required": True}},
            {"$sort": {"schedule.start": 1, "_id": 1}},
            *card_tail(now)[:1],
            {"$match": {"registration_open": True}},
            {"$limit": 1},
            *card_tail(now)[1:],
        ]
        docs = await agg(db, pipe, 1)
    if not docs:
        return FeaturedOut(source="none", event=None)
    return FeaturedOut(source=source, event=(await to_cards(db, docs, user, now))[0])


async def in_range(db: AsyncDatabase, user: dict | None, now: datetime, start: datetime, end: datetime, limit: int):
    docs = await agg(db, range_pipeline(now, start, end, limit), limit)
    return await to_cards(db, docs, user, now)


async def resolve_club_ids(db: AsyncDatabase, refs: list[str]) -> list[ObjectId]:
    ids = [ObjectId(r) for r in refs if ObjectId.is_valid(r)]
    slugs = [r.lower() for r in refs]
    clubs = await db.clubs.find(
        {"verified": True, "$or": [{"_id": {"$in": ids}}, {"slug": {"$in": slugs}}]}, {"_id": 1}
    ).to_list(None)
    return [c["_id"] for c in clubs]


async def catalogue(
    db: AsyncDatabase, user: dict | None, now: datetime, *, q: str | None, categories: list[str],
    clubs: list[str], date_from: date | None, date_to: date | None, sort: str | None, skip: int, limit: int,
):  # fmt: skip
    bad = [c for c in categories if c not in CATEGORIES]
    if bad:
        raise AppError(422, "invalid_category", f"Unknown categories: {bad}")
    if date_from and date_to and date_from > date_to:
        raise AppError(422, "invalid_date_range", "date_from must not be after date_to")
    if sort == "relevance" and not q:
        raise AppError(422, "invalid_sort", "sort=relevance requires q")
    club_ids = await resolve_club_ids(db, clubs) if clubs else None
    pipeline = catalogue_pipeline(
        now, q=q, categories=categories, club_ids=club_ids, date_from=date_from, date_to=date_to,
        sort=sort or ("relevance" if q else "date"), skip=skip, limit=limit,
    )  # fmt: skip
    facet = (await agg(db, pipeline, 1))[0]
    total = facet["total"][0]["n"] if facet["total"] else 0
    cards = await to_cards(db, facet["items"], user, now)
    facets = Facets(
        categories=[CategoryFacet(value=f["_id"], count=f["count"]) for f in facet["by_category"]],
        clubs=[ClubFacet(id=str(f["_id"]), name=f["name"], slug=f["slug"], count=f["count"]) for f in facet["by_club"]],
    )
    return cards, total, facets
