from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.core.deps import DB, PlatformAdmin
from app.core.errors import ErrorResponse
from app.models.clubs import AddAdminIn, ClubOut
from app.models.common import Page, PageParams, to_oid
from app.models.users import RoleChange, UserOut
from app.services import clubs as clubs_svc
from app.services import users as users_svc
from app.services.serializers import club_out, user_out

router = APIRouter(prefix="/admin", tags=["admin"])
_errors = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.get("/clubs", response_model=Page[ClubOut], responses=_errors, summary="Clubs by verification status")
async def list_clubs(
    db: DB,
    _: PlatformAdmin,
    pp: Annotated[PageParams, Depends()],
    status: Literal["pending", "verified", "all"] = "pending",
) -> Page[ClubOut]:
    verified = {"pending": False, "verified": True, "all": None}[status]
    items, total = await clubs_svc.list_clubs(db, pp.skip, pp.page_size, verified=verified)
    return Page(items=[club_out(c) for c in items], total=total, page=pp.page, page_size=pp.page_size)


@router.post("/clubs/{club_id}/verify", response_model=ClubOut, responses=_errors)
async def verify_club(club_id: str, db: DB, admin: PlatformAdmin) -> ClubOut:
    return club_out(await clubs_svc.verify_club(db, to_oid(club_id, "club id"), admin["_id"]))


@router.post(
    "/clubs/{club_id}/admins",
    response_model=ClubOut,
    responses=_errors,
    summary="Add a club admin (promotes the user to club_admin)",
)
async def add_club_admin(club_id: str, body: AddAdminIn, db: DB, _: PlatformAdmin) -> ClubOut:
    return club_out(await clubs_svc.add_admin(db, to_oid(club_id, "club id"), to_oid(body.user_id, "user id")))


@router.delete("/clubs/{club_id}/admins/{user_id}", response_model=ClubOut, responses=_errors)
async def remove_club_admin(club_id: str, user_id: str, db: DB, _: PlatformAdmin) -> ClubOut:
    return club_out(await clubs_svc.remove_admin(db, to_oid(club_id, "club id"), to_oid(user_id, "user id")))


@router.get("/users", response_model=Page[UserOut], responses=_errors)
async def list_users(
    db: DB,
    _: PlatformAdmin,
    pp: Annotated[PageParams, Depends()],
    role: Literal["student", "club_admin", "platform_admin"] | None = None,
) -> Page[UserOut]:
    items, total = await users_svc.list_users(db, pp.skip, pp.page_size, role)
    return Page(items=[user_out(u) for u in items], total=total, page=pp.page, page_size=pp.page_size)


@router.patch("/users/{user_id}/role", response_model=UserOut, responses=_errors)
async def change_role(user_id: str, body: RoleChange, db: DB, admin: PlatformAdmin) -> UserOut:
    return user_out(await users_svc.set_role(db, admin["_id"], to_oid(user_id, "user id"), body.role))
