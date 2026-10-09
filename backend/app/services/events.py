from typing import Any

from bson import ObjectId
from pydantic import ValidationError
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app import db as db_module
from app.core import timeutil
from app.core.deps import ensure_club_admin
from app.core.errors import AppError, bad_request, forbidden, not_found
from app.models.common import SCHEMA_VERSION, to_oid
from app.models.events import EVENT_FIELDS, EventCreate, EventInput, EventPatch
from app.services import files

EDITABLE_STATUSES = ("draft", "pending_review", "rejected", "published")


def invalid_state(action: str, status: str) -> AppError:
    return AppError(409, "invalid_state", f"Cannot {action} an event that is {status}")


def _fields_from_input(inp: EventInput) -> dict[str, Any]:
    out = inp.model_dump(mode="python", exclude={"details"})
    # Free-form bag: store exactly the keys the client sent (no model defaults injected into nested objects).
    out["details"] = inp.details.model_dump(exclude={"event_type"}, exclude_unset=True) if inp.details else {}
    return out


# ------------------------------------------------------------------ create / read
async def create_event(db: AsyncDatabase, user: dict, data: EventCreate) -> dict:
    club = await ensure_club_admin(db, user, to_oid(data.club_id, "club id"))
    if not club["verified"]:
        raise forbidden("This club has not been verified yet")
    now = timeutil.now()
    doc = {
        **_fields_from_input(data),
        "club_id": club["_id"],
        # Extended-reference pattern: snapshot avoids a $lookup on every event card.
        "club_snapshot": {"name": club["name"], "slug": club["slug"]},
        "creator_id": user["_id"],
        "poster_file_id": None,
        "status": "draft",
        "rejection_reason": None,
        "cancel_reason": None,
        "cancelled_at": None,
        "featured": {"is_featured": False, "featured_at": None},
        "stats": {"views": 0, "saves": 0, "registration_clicks": 0},  # computed pattern
        "change_log": [],
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "schema_v": SCHEMA_VERSION,
    }
    doc["_id"] = (await db.events.insert_one(doc)).inserted_id
    return doc


async def get_event(db: AsyncDatabase, event_id: ObjectId) -> dict:
    doc = await db.events.find_one({"_id": event_id})
    if not doc:
        raise not_found("Event")
    return doc


async def can_manage(db: AsyncDatabase, user: dict | None, event: dict) -> bool:
    if user is None:
        return False
    if user["role"] == "platform_admin":
        return True
    if user["role"] != "club_admin":
        return False
    club = await db.clubs.find_one({"_id": event["club_id"]}, {"admin_ids": 1})
    return bool(club and user["_id"] in club["admin_ids"])


async def get_visible_event(db: AsyncDatabase, user: dict | None, event_id: ObjectId) -> dict:
    """Readable by id if published OR cancelled (a saved/shared link to a cancelled event must still
    explain what happened). Draft, pending and rejected events: only their club admins / platform admins."""
    event = await get_event(db, event_id)
    if event["status"] in ("published", "cancelled"):
        return event
    if await can_manage(db, user, event):
        return event
    raise not_found("Event")


async def load_for_manage(db: AsyncDatabase, user: dict, event_id: ObjectId) -> dict:
    """Load an event and require the caller to administer its (verified) club."""
    event = await get_event(db, event_id)
    await ensure_club_admin(db, user, event["club_id"])
    return event


async def list_managed(
    db: AsyncDatabase, user: dict, skip: int, limit: int, club_id: ObjectId | None, status: str | None
) -> tuple[list[dict], int]:
    flt: dict[str, Any] = {}
    if club_id is not None:
        await ensure_club_admin(db, user, club_id)
        flt["club_id"] = club_id
    elif user["role"] != "platform_admin":
        mine = await db.clubs.find({"admin_ids": user["_id"]}, {"_id": 1}).to_list(None)
        flt["club_id"] = {"$in": [c["_id"] for c in mine]}
    if status:
        flt["status"] = status
    total = await db.events.count_documents(flt)
    items = await db.events.find(flt).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return items, total


# ------------------------------------------------------------------ edit
async def update_event(db: AsyncDatabase, user: dict, event_id: ObjectId, patch: EventPatch) -> dict:
    event = await load_for_manage(db, user, event_id)
    if event["status"] not in EDITABLE_STATUSES:
        raise invalid_state("edit", event["status"])

    changes = patch.model_dump(exclude_unset=True)
    club_id = changes.pop("club_id", None)
    if club_id is not None and to_oid(club_id, "club id") != event["club_id"]:
        raise AppError(409, "club_change_not_allowed", "An event cannot be moved to another club")
    current = {k: event.get(k) for k in EVENT_FIELDS}
    merged = {**current, **changes}
    try:
        new_fields = _fields_from_input(EventInput.model_validate(merged))  # re-validate the whole event
    except ValidationError as e:
        details = [{"loc": [str(p) for p in x["loc"]], "msg": x["msg"], "type": x["type"]} for x in e.errors()]
        raise AppError(422, "validation_error", "Merged event is invalid", details) from None

    changed = [k for k in EVENT_FIELDS if new_fields[k] != event.get(k)]
    if not changed:
        return event
    now = timeutil.now()
    entry = {"at": now, "by": user["_id"], "fields": changed}
    update = {
        "$set": {**{k: new_fields[k] for k in changed}, "updated_at": now},
        # History is capped: keep only the last 20 edits.
        "$push": {"change_log": {"$each": [entry], "$slice": -20}},
    }
    flt = {"_id": event_id, "status": event["status"]}

    async def write(session):
        doc = await db.events.find_one_and_update(flt, update, return_document=ReturnDocument.AFTER, session=session)
        if doc is not None and "schedule" in changed:
            # Denormalized copy used by the calendar must follow the schedule.
            await db.saved_events.update_many(
                {"event_id": event_id}, {"$set": {"event_start": new_fields["schedule"]["start"]}}, session=session
            )
        return doc

    doc = await db_module.run_txn(write)
    if doc is None:
        raise AppError(409, "conflict", "Event changed while you were editing; reload and retry")
    return doc


# ------------------------------------------------------------------ lifecycle
async def _transition(
    db: AsyncDatabase, event_id: ObjectId, action: str, allowed: tuple[str, ...], changes: dict[str, Any]
) -> dict:
    doc = await db.events.find_one_and_update(
        {"_id": event_id, "status": {"$in": list(allowed)}},
        {"$set": {**changes, "updated_at": timeutil.now()}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:  # lost a race, or wrong state
        current = await get_event(db, event_id)
        raise invalid_state(action, current["status"])
    return doc


async def submit_event(db: AsyncDatabase, user: dict, event_id: ObjectId) -> dict:
    event = await load_for_manage(db, user, event_id)
    if event["status"] not in ("draft", "rejected"):
        raise invalid_state("submit", event["status"])
    if event["schedule"]["start"] <= timeutil.now():
        raise bad_request("An event that has already started cannot be submitted", "event_in_past")
    return await _transition(
        db, event_id, "submit", ("draft", "rejected"), {"status": "pending_review", "rejection_reason": None}
    )


async def cancel_event(db: AsyncDatabase, user: dict, event_id: ObjectId, reason: str) -> dict:
    await load_for_manage(db, user, event_id)
    now = timeutil.now()
    return await _transition(
        db, event_id, "cancel", ("published",), {"status": "cancelled", "cancel_reason": reason, "cancelled_at": now}
    )


async def delete_draft(db: AsyncDatabase, user: dict, event_id: ObjectId) -> None:
    event = await load_for_manage(db, user, event_id)
    res = await db.events.delete_one({"_id": event_id, "status": "draft"})
    if res.deleted_count == 0:
        raise invalid_state("delete", event["status"])
    await files.delete_file(event.get("poster_file_id"))


# ------------------------------------------------------------------ platform admin moderation
async def approve_event(db: AsyncDatabase, event_id: ObjectId) -> dict:
    now = timeutil.now()
    return await _transition(db, event_id, "approve", ("pending_review",), {"status": "published", "published_at": now})


async def reject_event(db: AsyncDatabase, event_id: ObjectId, reason: str) -> dict:
    return await _transition(
        db, event_id, "reject", ("pending_review",), {"status": "rejected", "rejection_reason": reason}
    )


async def set_featured(db: AsyncDatabase, event_id: ObjectId, featured: bool) -> dict:
    event = await get_event(db, event_id)
    if featured and event["status"] != "published":
        raise invalid_state("feature", event["status"])
    value = {"is_featured": featured, "featured_at": timeutil.now() if featured else None}
    return await db.events.find_one_and_update(
        {"_id": event_id},
        {"$set": {"featured": value, "updated_at": timeutil.now()}},
        return_document=ReturnDocument.AFTER,
    )


async def list_for_admin(db: AsyncDatabase, skip: int, limit: int, status: str | None) -> tuple[list[dict], int]:
    flt = {"status": status} if status else {}
    total = await db.events.count_documents(flt)
    items = await db.events.find(flt).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return items, total


# ------------------------------------------------------------------ posters
async def set_poster(db: AsyncDatabase, user: dict, event_id: ObjectId, data: bytes, declared_type: str | None) -> dict:
    event = await load_for_manage(db, user, event_id)
    content_type = files.validate_poster(data, declared_type)
    new_id = await files.save_poster(data, content_type, event_id)
    doc = await db.events.find_one_and_update(
        {"_id": event_id},
        {"$set": {"poster_file_id": new_id, "updated_at": timeutil.now()}},
        return_document=ReturnDocument.AFTER,
    )
    await files.delete_file(event.get("poster_file_id"))  # replace: drop the old one after the new one is safe
    return doc
