from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, CurrentUser, OptionalUser, require_club_admin_for
from app.core.errors import ErrorResponse, not_found
from app.models.clubs import ClubCreate, ClubOut, ClubPatch
from app.models.common import Page, PageParams, to_oid
from app.services import clubs as svc
from app.services.serializers import club_out

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=Page[ClubOut], summary="Verified clubs (powers 'Browse by Club')")
async def list_clubs(
    db: DB, pp: Annotated[PageParams, Depends()], q: Annotated[str | None, Query(max_length=80)] = None
) -> Page[ClubOut]:
    items, total = await svc.list_clubs(db, pp.skip, pp.page_size, verified=True, q=q)
    return Page(items=[club_out(c) for c in items], total=total, page=pp.page, page_size=pp.page_size)


@router.get("/{id_or_slug}", response_model=ClubOut, responses={404: {"model": ErrorResponse}})
async def get_club(id_or_slug: str, db: DB, user: OptionalUser) -> ClubOut:
    club = await svc.find_club(db, id_or_slug)
    # Unverified clubs are visible only to their requester, their admins and platform admins.
    if club and not club["verified"]:
        allowed = user and (
            user["role"] == "platform_admin"
            or user["_id"] == club.get("requested_by")
            or user["_id"] in club["admin_ids"]
        )
        if not allowed:
            club = None
    if not club:
        raise not_found("Club")
    return club_out(club)


@router.post(
    "",
    response_model=ClubOut,
    status_code=201,
    responses={409: {"model": ErrorResponse}},
    summary="Request a new club (starts unverified)",
)
async def request_club(data: ClubCreate, db: DB, user: CurrentUser) -> ClubOut:
    return club_out(await svc.request_club(db, user["_id"], data))


@router.patch(
    "/{club_id}",
    response_model=ClubOut,
    responses={403: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    dependencies=[Depends(require_club_admin_for("club_id"))],
    summary="Edit a club (rename refreshes event snapshots in a transaction)",
)
async def update_club(club_id: str, patch: ClubPatch, db: DB) -> ClubOut:
    return club_out(await svc.update_club(db, to_oid(club_id, "club id"), patch))
