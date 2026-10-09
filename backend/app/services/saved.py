"""Saved events and the calendar.

``saved_events`` is a separate collection (unbounded per user, queried from both sides, needs a unique
constraint). Save/unsave touch three collections, so they run in a multi-document transaction.
"""

from datetime import datetime

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app import db as db_module
from app.core import timeutil
from app.core.errors import AppError
from app.models.common import SCHEMA_VERSION
from app.models.saved import CalendarDay, CalendarOut, SavedEventOut
from app.services import interactions
from app.services.discovery import card_tail
from app.services.event_view import to_card


# Transaction steps are module-level functions so tests can force a failure part-way through.
async def insert_saved(db: AsyncDatabase, session, user_id: ObjectId, event: dict) -> dict:
    doc = {
        "user_id": user_id,
        "event_id": event["_id"],
        "status": "saved",
        "event_start": event["schedule"]["start"],  # denormalised: calendar range-queries without a $lookup
        "created_at": timeutil.now(),
        "schema_v": SCHEMA_VERSION,
    }
    doc["_id"] = (await db.saved_events.insert_one(doc, session=session)).inserted_id
    return doc


async def delete_saved(db: AsyncDatabase, session, user_id: ObjectId, event_id: ObjectId) -> bool:
    res = await db.saved_events.delete_one({"user_id": user_id, "event_id": event_id}, session=session)
    return res.deleted_count == 1


async def dec_saves(db: AsyncDatabase, session, event_id: ObjectId) -> None:
    # Never below zero, even if a counter has drifted.
    await db.events.update_one(
        {"_id": event_id, "stats.saves": {"$gt": 0}}, {"$inc": {"stats.saves": -1}}, session=session
    )


async def remove_save_interaction(db: AsyncDatabase, session, event_id: ObjectId, user_id: ObjectId) -> None:
    """Retract this user's latest 'save' so save/unsave cycles cannot inflate windowed ranking."""
    last = await db.event_interactions.find_one(
        {"event_id": event_id, "user_id": user_id, "type": "save"}, {"_id": 1}, sort=[("ts", -1)], session=session
    )
    if last:
        await db.event_interactions.delete_one({"_id": last["_id"]}, session=session)


async def save_event(db: AsyncDatabase, user_id: ObjectId, event_id: ObjectId) -> tuple[dict, bool]:
    """Returns (saved_doc, created). Saving twice returns the existing record."""
    event = await interactions.get_public_event(db, event_id)
    existing = await db.saved_events.find_one({"user_id": user_id, "event_id": event_id})
    if existing:
        return existing, False

    async def write(session):
        saved = await insert_saved(db, session, user_id, event)
        await interactions.inc_stat(db, session, event_id, "saves")
        await interactions.insert_interaction(db, session, event_id, user_id, "save")
        return saved

    try:
        return await db_module.run_txn(write), True
    except DuplicateKeyError:  # lost a race with a concurrent save: the unique index is the arbiter
        return await db.saved_events.find_one({"user_id": user_id, "event_id": event_id}), False


async def unsave_event(db: AsyncDatabase, user_id: ObjectId, event_id: ObjectId) -> bool:
    async def write(session):
        if not await delete_saved(db, session, user_id, event_id):
            return False
        await dec_saves(db, session, event_id)
        await remove_save_interaction(db, session, event_id, user_id)
        return True

    return await db_module.run_txn(write)


def _lookup_event(now: datetime) -> list[dict]:
    return [
        {
            "$lookup": {
                "from": "events",
                "localField": "event_id",
                "foreignField": "_id",
                "pipeline": card_tail(now),
                "as": "event",
            }
        },
        {"$unwind": "$event"},
    ]


def _to_out(row: dict, now: datetime) -> SavedEventOut:
    ev = row["event"]
    return SavedEventOut(
        id=str(row["_id"]), status=row["status"], saved_at=row["created_at"], cancelled=ev["status"] == "cancelled",
        event=to_card(ev, now, is_saved=True),
    )  # fmt: skip


async def list_saved(
    db: AsyncDatabase, user_id: ObjectId, now: datetime, *, upcoming: bool, skip: int, limit: int
) -> tuple[list[SavedEventOut], int]:
    flt: dict = {"user_id": user_id}
    if upcoming:
        flt["event_start"] = {"$gte": now}
    total = await db.saved_events.count_documents(flt)
    pipeline = [
        {"$match": flt},
        {"$sort": {"event_start": 1 if upcoming else -1, "_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        *_lookup_event(now),
    ]
    rows = await (await db.saved_events.aggregate(pipeline)).to_list(limit)
    return [_to_out(r, now) for r in rows], total


def calendar_pipeline(user_id: ObjectId, now: datetime, year: int, month: int) -> list[dict]:
    start, end = timeutil.month_range(year, month)
    return [
        # Range query on the denormalised event_start: served by the {user_id, event_start} index.
        {"$match": {"user_id": user_id, "event_start": {"$gte": start, "$lt": end}}},
        {"$sort": {"event_start": 1, "_id": 1}},
        *_lookup_event(now),
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "date": "$event_start", "format": "%Y-%m-%d", "timezone": timeutil.get_settings().app_timezone
                    }
                },
                "rows": {"$push": "$$ROOT"},
            }
        },
        {"$sort": {"_id": 1}},
    ]  # fmt: skip


async def calendar(db: AsyncDatabase, user_id: ObjectId, now: datetime, year: int, month: int) -> CalendarOut:
    if not 1 <= month <= 12:
        raise AppError(422, "invalid_month", "month must be between 1 and 12")
    groups = await (await db.saved_events.aggregate(calendar_pipeline(user_id, now, year, month))).to_list(None)
    days = [CalendarDay(date=g["_id"], items=[_to_out(r, now) for r in g["rows"]]) for g in groups]
    return CalendarOut(year=year, month=month, timezone=timeutil.get_settings().app_timezone, days=days)
