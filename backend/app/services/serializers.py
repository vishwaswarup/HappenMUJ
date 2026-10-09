from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.models.clubs import ClubOut
from app.models.users import UserOut


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def user_out(u: dict, managed_club_ids: list[str] | None = None) -> UserOut:
    return UserOut(
        managed_club_ids=managed_club_ids or [],
        id=str(u["_id"]),
        name=u["name"],
        email=u["email"],
        role=u["role"],
        interests=u.get("interests", []),
        preferred_categories=u.get("preferred_categories", []),
        followed_club_ids=[str(i) for i in u.get("followed_club_ids", [])],
        created_at=u["created_at"],
    )


def club_out(c: dict) -> ClubOut:
    return ClubOut(
        id=str(c["_id"]),
        name=c["name"],
        slug=c["slug"],
        description=c.get("description", ""),
        category=c["category"],
        verified=c["verified"],
        verified_at=c.get("verified_at"),
        verified_by=_s(c.get("verified_by")),
        requested_by=_s(c.get("requested_by")),
        admin_ids=[str(i) for i in c.get("admin_ids", [])],
        created_at=c["created_at"],
    )


async def present_users(db: AsyncDatabase, users: list[dict]) -> list[UserOut]:
    """User payloads with `managed_club_ids`, resolved with ONE query (clubs.admin_ids is the source of truth)."""
    ids = [u["_id"] for u in users]
    managed: dict[Any, list[str]] = {i: [] for i in ids}
    if ids:
        async for c in db.clubs.find({"admin_ids": {"$in": ids}}, {"admin_ids": 1}).sort("name", 1):
            for a in c["admin_ids"]:
                if a in managed:
                    managed[a].append(str(c["_id"]))
    return [user_out(u, managed[u["_id"]]) for u in users]


async def present_user(db: AsyncDatabase, user: dict) -> UserOut:
    return (await present_users(db, [user]))[0]
