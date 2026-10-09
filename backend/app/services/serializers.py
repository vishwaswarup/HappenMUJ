from typing import Any

from app.models.clubs import ClubOut
from app.models.users import UserOut


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def user_out(u: dict) -> UserOut:
    return UserOut(
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
