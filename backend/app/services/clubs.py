import re

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core import timeutil
from app.core.errors import conflict, not_found
from app.models.clubs import ClubCreate
from app.models.common import SCHEMA_VERSION


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "club"


async def request_club(db: AsyncDatabase, user_id: ObjectId, data: ClubCreate) -> dict:
    doc = {
        "name": data.name.strip(),
        "slug": slugify(data.name),
        "description": data.description,
        "category": data.category,
        "verified": False,
        "verified_at": None,
        "verified_by": None,
        "requested_by": user_id,
        "admin_ids": [],
        "created_at": timeutil.now(),
        "schema_v": SCHEMA_VERSION,
    }
    try:
        res = await db.clubs.insert_one(doc)
    except DuplicateKeyError:
        raise conflict("A club with this name already exists", "club_exists") from None
    doc["_id"] = res.inserted_id
    return doc


async def find_club(db: AsyncDatabase, id_or_slug: str) -> dict | None:
    if ObjectId.is_valid(id_or_slug):
        club = await db.clubs.find_one({"_id": ObjectId(id_or_slug)})
        if club:
            return club
    return await db.clubs.find_one({"slug": id_or_slug.lower()})


async def list_clubs(
    db: AsyncDatabase, skip: int, limit: int, *, verified: bool | None = True, q: str | None = None
) -> tuple[list[dict], int]:
    flt: dict = {}
    if verified is not None:
        flt["verified"] = verified
    if q:
        flt["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    total = await db.clubs.count_documents(flt)
    items = await db.clubs.find(flt).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    return items, total


async def verify_club(db: AsyncDatabase, club_id: ObjectId, admin_id: ObjectId) -> dict:
    club = await db.clubs.find_one_and_update(
        {"_id": club_id},
        {"$set": {"verified": True, "verified_at": timeutil.now(), "verified_by": admin_id}},
        return_document=True,
    )
    if not club:
        raise not_found("Club")
    return club


async def add_admin(db: AsyncDatabase, club_id: ObjectId, user_id: ObjectId) -> dict:
    """Add a user to ``admin_ids`` (single source of truth) and promote students to club_admin."""
    user = await db.users.find_one({"_id": user_id}, {"role": 1})
    if not user:
        raise not_found("User")
    club = await db.clubs.find_one_and_update(
        {"_id": club_id}, {"$addToSet": {"admin_ids": user_id}}, return_document=True
    )
    if not club:
        raise not_found("Club")
    await db.users.update_one({"_id": user_id, "role": "student"}, {"$set": {"role": "club_admin"}})
    return club


async def remove_admin(db: AsyncDatabase, club_id: ObjectId, user_id: ObjectId) -> dict:
    club = await db.clubs.find_one_and_update({"_id": club_id}, {"$pull": {"admin_ids": user_id}}, return_document=True)
    if not club:
        raise not_found("Club")
    # Demote only if they no longer administer any club.
    if not await db.clubs.find_one({"admin_ids": user_id}, {"_id": 1}):
        await db.users.update_one({"_id": user_id, "role": "club_admin"}, {"$set": {"role": "student"}})
    return club
