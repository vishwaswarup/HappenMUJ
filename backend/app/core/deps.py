from collections.abc import Awaitable, Callable
from typing import Annotated

from bson import ObjectId
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app import db as db_module
from app.core.errors import forbidden, not_found, unauthorized
from app.core.security import decode_access_token
from app.models.common import to_oid

bearer = HTTPBearer(auto_error=False, description="JWT from POST /auth/login")


def get_database() -> AsyncDatabase:
    return db_module.get_db()


DB = Annotated[AsyncDatabase, Depends(get_database)]


async def optional_user(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None
) -> dict | None:
    if creds is None:
        return None
    user_id = decode_access_token(creds.credentials)
    if not user_id or not ObjectId.is_valid(user_id):
        raise unauthorized("Invalid or expired token")
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise unauthorized("Account no longer exists")
    return user


async def current_user(user: Annotated[dict | None, Depends(optional_user)]) -> dict:
    if user is None:
        raise unauthorized()
    return user


CurrentUser = Annotated[dict, Depends(current_user)]
OptionalUser = Annotated[dict | None, Depends(optional_user)]


def require_role(*roles: str) -> Callable[..., Awaitable[dict]]:
    async def dep(user: CurrentUser) -> dict:
        if user["role"] not in roles:
            raise forbidden(f"Requires role: {' or '.join(roles)}")
        return user

    return dep


require_platform_admin = require_role("platform_admin")
PlatformAdmin = Annotated[dict, Depends(require_platform_admin)]


async def ensure_club_admin(db: AsyncDatabase, user: dict, club_id: ObjectId) -> dict:
    """Platform admins pass; club admins must be in ``club.admin_ids`` of a *verified* club."""
    club = await db.clubs.find_one({"_id": club_id})
    if not club:
        raise not_found("Club")
    if user["role"] == "platform_admin":
        return club
    if user["role"] != "club_admin" or user["_id"] not in club.get("admin_ids", []):
        raise forbidden("You are not an admin of this club")
    if not club["verified"]:
        raise forbidden("This club has not been verified yet")
    return club


def require_club_admin_for(param: str = "club_id") -> Callable[..., Awaitable[dict]]:
    """Dependency factory: reads the club id from the path parameter ``param``."""

    async def dep(request: Request, db: DB, user: CurrentUser) -> dict:
        club_id = to_oid(request.path_params[param], "club id")
        await ensure_club_admin(db, user, club_id)
        return user

    return dep
