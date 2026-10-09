from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.core import timeutil
from app.core.errors import AppError, bad_request, conflict, not_found, unauthorized
from app.core.security import hash_password, verify_password
from app.models.common import SCHEMA_VERSION, normalize_terms
from app.models.users import LoginIn, RegisterIn, UserPatch


def _check_domain(email: str) -> None:
    domains = get_settings().email_domains
    if domains and email.rsplit("@", 1)[-1] not in domains:
        raise AppError(422, "email_domain_not_allowed", f"Email must be one of: {', '.join('@' + d for d in domains)}")


async def register(db: AsyncDatabase, data: RegisterIn) -> dict:
    email = data.email.lower()
    _check_domain(email)
    doc = {
        "name": data.name.strip(),
        "email": email,
        "password_hash": hash_password(data.password),
        "role": "student",
        "interests": [],
        "preferred_categories": [],
        "followed_club_ids": [],
        "created_at": timeutil.now(),
        "schema_v": SCHEMA_VERSION,
    }
    try:
        res = await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise conflict("An account with this email already exists", "email_taken") from None
    doc["_id"] = res.inserted_id
    return doc


async def authenticate(db: AsyncDatabase, data: LoginIn) -> dict:
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise unauthorized("Invalid email or password")
    return user


async def get_user(db: AsyncDatabase, user_id: ObjectId) -> dict:
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise not_found("User")
    return user


async def update_profile(db: AsyncDatabase, user_id: ObjectId, patch: UserPatch) -> dict:
    changes: dict = {}
    if patch.name is not None:
        changes["name"] = patch.name.strip()
    if patch.interests is not None:
        changes["interests"] = normalize_terms(patch.interests)
    if patch.preferred_categories is not None:
        changes["preferred_categories"] = patch.preferred_categories
    if not changes:
        raise bad_request("Nothing to update")
    user = await db.users.find_one_and_update({"_id": user_id}, {"$set": changes}, return_document=True)
    if not user:
        raise not_found("User")
    return user


async def follow_club(db: AsyncDatabase, user_id: ObjectId, club_id: ObjectId) -> dict:
    club = await db.clubs.find_one({"_id": club_id, "verified": True}, {"_id": 1})
    if not club:
        raise not_found("Club")
    return await db.users.find_one_and_update(
        {"_id": user_id}, {"$addToSet": {"followed_club_ids": club_id}}, return_document=True
    )


async def unfollow_club(db: AsyncDatabase, user_id: ObjectId, club_id: ObjectId) -> dict:
    return await db.users.find_one_and_update(
        {"_id": user_id}, {"$pull": {"followed_club_ids": club_id}}, return_document=True
    )


async def bootstrap_platform_admin(db: AsyncDatabase) -> None:
    """Create the platform admin from env on startup if missing (never overwrites a password)."""
    s = get_settings()
    email = s.platform_admin_email.lower()
    await db.users.update_one(
        {"email": email},
        {
            "$set": {"role": "platform_admin"},
            "$setOnInsert": {
                "name": "Platform Admin",
                "password_hash": hash_password(s.platform_admin_password),
                "interests": [],
                "preferred_categories": [],
                "followed_club_ids": [],
                "created_at": timeutil.now(),
                "schema_v": SCHEMA_VERSION,
            },
        },
        upsert=True,
    )


async def list_users(db: AsyncDatabase, skip: int, limit: int, role: str | None = None) -> tuple[list[dict], int]:
    flt = {"role": role} if role else {}
    total = await db.users.count_documents(flt)
    items = await db.users.find(flt).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return items, total


async def set_role(db: AsyncDatabase, actor_id: ObjectId, user_id: ObjectId, role: str) -> dict:
    if actor_id == user_id:
        raise bad_request("You cannot change your own role", "cannot_change_own_role")
    user = await db.users.find_one_and_update({"_id": user_id}, {"$set": {"role": role}}, return_document=True)
    if not user:
        raise not_found("User")
    return user
