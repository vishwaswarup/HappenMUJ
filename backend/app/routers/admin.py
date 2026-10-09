from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.core import timeutil
from app.core.deps import DB, PlatformAdmin
from app.core.errors import ErrorResponse
from app.models.clubs import AddAdminIn, ClubOut
from app.models.common import Page, PageParams, to_oid
from app.models.events import EventDetail, RejectIn
from app.models.users import RoleChange, UserOut
from app.services import clubs as clubs_svc
from app.services import community as community_svc
from app.services import events as events_svc
from app.services import users as users_svc
from app.services.event_view import to_detail
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


@router.post("/clubs/{club_id}/verify", response_model=ClubOut, responses=_errors, summary="Verify a club")
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


@router.delete(
    "/clubs/{club_id}/admins/{user_id}",
    response_model=ClubOut,
    responses=_errors,
    summary="Remove a club admin (demotes to student if they administer no other club)",
)
async def remove_club_admin(club_id: str, user_id: str, db: DB, _: PlatformAdmin) -> ClubOut:
    return club_out(await clubs_svc.remove_admin(db, to_oid(club_id, "club id"), to_oid(user_id, "user id")))


@router.get("/users", response_model=Page[UserOut], responses=_errors, summary="All users, filterable by role")
async def list_users(
    db: DB,
    _: PlatformAdmin,
    pp: Annotated[PageParams, Depends()],
    role: Literal["student", "club_admin", "platform_admin"] | None = None,
) -> Page[UserOut]:
    items, total = await users_svc.list_users(db, pp.skip, pp.page_size, role)
    return Page(items=[user_out(u) for u in items], total=total, page=pp.page, page_size=pp.page_size)


@router.patch("/users/{user_id}/role", response_model=UserOut, responses=_errors, summary="Change a user's role")
async def change_role(user_id: str, body: RoleChange, db: DB, admin: PlatformAdmin) -> UserOut:
    return user_out(await users_svc.set_role(db, admin["_id"], to_oid(user_id, "user id"), body.role))


# ---- event moderation
EventStatusFilter = Literal["draft", "pending_review", "published", "rejected", "cancelled", "all"]


def _ev(doc: dict) -> EventDetail:
    return to_detail(doc, timeutil.now())


@router.get(
    "/events", response_model=Page[EventDetail], responses=_errors, summary="Events by status (default: review queue)"
)
async def list_events(
    db: DB, _: PlatformAdmin, pp: Annotated[PageParams, Depends()], status: EventStatusFilter = "pending_review"
) -> Page[EventDetail]:
    items, total = await events_svc.list_for_admin(db, pp.skip, pp.page_size, None if status == "all" else status)
    return Page(items=[_ev(e) for e in items], total=total, page=pp.page, page_size=pp.page_size)


@router.post(
    "/events/{event_id}/approve", response_model=EventDetail, responses=_errors, summary="pending_review -> published"
)
async def approve_event(event_id: str, db: DB, _: PlatformAdmin) -> EventDetail:
    return _ev(await events_svc.approve_event(db, to_oid(event_id, "event id")))


@router.post(
    "/events/{event_id}/reject", response_model=EventDetail, responses=_errors, summary="pending_review -> rejected"
)
async def reject_event(event_id: str, body: RejectIn, db: DB, _: PlatformAdmin) -> EventDetail:
    return _ev(await events_svc.reject_event(db, to_oid(event_id, "event id"), body.reason))


@router.post(
    "/events/{event_id}/feature", response_model=EventDetail, responses=_errors, summary="Feature a published event"
)
async def feature_event(event_id: str, db: DB, _: PlatformAdmin) -> EventDetail:
    return _ev(await events_svc.set_featured(db, to_oid(event_id, "event id"), True))


@router.delete(
    "/events/{event_id}/feature", response_model=EventDetail, responses=_errors, summary="Remove featured flag"
)
async def unfeature_event(event_id: str, db: DB, _: PlatformAdmin) -> EventDetail:
    return _ev(await events_svc.set_featured(db, to_oid(event_id, "event id"), False))


# ---- community moderation (soft delete via status)
@router.post("/posts/{post_id}/remove", status_code=204, responses=_errors, summary="Remove any post")
async def remove_post(post_id: str, db: DB, admin: PlatformAdmin) -> None:
    await community_svc.remove_post(db, admin, to_oid(post_id, "post id"), admin_override=True)


@router.post("/comments/{comment_id}/remove", status_code=204, responses=_errors, summary="Remove any comment")
async def remove_comment(comment_id: str, db: DB, admin: PlatformAdmin) -> None:
    await community_svc.remove_comment(db, admin, to_oid(comment_id, "comment id"), admin_override=True)
