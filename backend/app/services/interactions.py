"""event_interactions: the append-only log behind ranking and analytics (TTL 90 days).

Each recorded interaction also bumps the embedded counter on the event (computed pattern), in one
transaction so counter and log cannot drift apart on a partial failure.
"""

from datetime import timedelta

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app import db as db_module
from app.core import timeutil
from app.core.errors import AppError, bad_request, not_found
from app.models.common import SCHEMA_VERSION
from app.services.event_view import registration_open
from app.services.visibility import public_filter

VIEW_DEDUPE_WINDOW = timedelta(minutes=30)


async def insert_interaction(db: AsyncDatabase, session, event_id: ObjectId, user_id: ObjectId | None, kind: str):
    await db.event_interactions.insert_one(
        {"event_id": event_id, "user_id": user_id, "type": kind, "ts": timeutil.now(), "schema_v": SCHEMA_VERSION},
        session=session,
    )


async def inc_stat(db: AsyncDatabase, session, event_id: ObjectId, field: str, by: int = 1):
    await db.events.update_one({"_id": event_id}, {"$inc": {f"stats.{field}": by}}, session=session)


async def get_public_event(db: AsyncDatabase, event_id: ObjectId) -> dict:
    event = await db.events.find_one(public_filter(_id=event_id))
    if not event:
        raise not_found("Event")
    return event


async def record_view(db: AsyncDatabase, user: dict | None, event_id: ObjectId) -> bool:
    await get_public_event(db, event_id)
    user_id = user["_id"] if user else None
    if user_id is not None:
        since = timeutil.now() - VIEW_DEDUPE_WINDOW
        recent = await db.event_interactions.find_one(
            {"event_id": event_id, "type": "view", "user_id": user_id, "ts": {"$gte": since}}, {"_id": 1}
        )
        if recent:
            return False
    # PHASE2: rate-limit anonymous views (they cannot be de-duplicated per user).

    async def write(session):
        await insert_interaction(db, session, event_id, user_id, "view")
        await inc_stat(db, session, event_id, "views")

    await db_module.run_txn(write)
    return True


async def record_registration_click(db: AsyncDatabase, user: dict | None, event_id: ObjectId) -> dict:
    """Log the click and hand back the external URL. We never claim the student *registered*."""
    event = await get_public_event(db, event_id)
    reg = event.get("registration", {})
    if not reg.get("required") or not reg.get("url"):
        raise bad_request("This event has no external registration", "no_registration")
    if not registration_open(event, timeutil.now()):
        raise AppError(409, "registration_closed", "Registration for this event is closed")
    user_id = user["_id"] if user else None

    async def write(session):
        await insert_interaction(db, session, event_id, user_id, "registration_click")
        await inc_stat(db, session, event_id, "registration_clicks")
        if user_id is not None:
            await db.saved_events.update_one(
                {"user_id": user_id, "event_id": event_id},
                {"$set": {"status": "registration_initiated"}},
                session=session,
            )

    await db_module.run_txn(write)
    return {"url": reg["url"], "platform": reg.get("platform")}
