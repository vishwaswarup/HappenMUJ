from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core import timeutil
from app.core.deps import DB, CurrentUser, OptionalUser, require_role
from app.core.errors import ErrorResponse
from app.models.common import Page, PageParams, to_oid
from app.models.discovery import CataloguePage
from app.models.events import CancelIn, EventCreate, EventDetail, EventPatch
from app.services import discovery
from app.services import events as svc
from app.services.event_view import to_detail
from app.services.files import MAX_POSTER_BYTES

router = APIRouter(prefix="/events", tags=["events"])
_manage_errors = {
    401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
    404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
}  # fmt: skip
ClubStaff = Annotated[dict, Depends(require_role("club_admin", "platform_admin"))]


def _detail(doc: dict) -> EventDetail:
    return to_detail(doc, timeutil.now())


@router.get(
    "",
    response_model=CataloguePage,
    summary="Catalogue: search, filters (OR within a group, AND between groups), sort, facets",
)
async def catalogue(
    db: DB,
    user: OptionalUser,
    pp: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(min_length=1, max_length=100, description="Weighted full-text search")] = None,
    category: Annotated[list[str] | None, Query(description="Repeatable; OR within the group")] = None,
    club: Annotated[list[str] | None, Query(description="Repeatable club id or slug; OR within the group")] = None,
    date_from: Annotated[date | None, Query(description="IST calendar date, inclusive")] = None,
    date_to: Annotated[date | None, Query(description="IST calendar date, inclusive")] = None,
    sort: Literal["date", "popularity", "relevance"] | None = None,
) -> CataloguePage:
    now = timeutil.now()
    cards, total, facets = await discovery.catalogue(
        db, user, now, q=q, categories=category or [], clubs=club or [], date_from=date_from, date_to=date_to,
        sort=sort, skip=pp.skip, limit=pp.page_size,
    )  # fmt: skip
    return CataloguePage(items=cards, total=total, page=pp.page, page_size=pp.page_size, facets=facets)


@router.post(
    "",
    response_model=EventDetail,
    status_code=201,
    responses=_manage_errors,
    summary="Create a draft event (club admin of a verified club)",
)
async def create_event(data: EventCreate, db: DB, user: ClubStaff) -> EventDetail:
    return _detail(await svc.create_event(db, user, data))


# NOTE: declared before /{event_id} so "mine" is not parsed as an id.
@router.get("/mine", response_model=Page[EventDetail], responses=_manage_errors, summary="Events I manage, any status")
async def my_events(
    db: DB,
    user: ClubStaff,
    pp: Annotated[PageParams, Depends()],
    club_id: str | None = None,
    status: Literal["draft", "pending_review", "published", "rejected", "cancelled"] | None = None,
) -> Page[EventDetail]:
    items, total = await svc.list_managed(
        db, user, pp.skip, pp.page_size, to_oid(club_id, "club id") if club_id else None, status
    )
    return Page(items=[_detail(e) for e in items], total=total, page=pp.page, page_size=pp.page_size)


@router.get(
    "/{event_id}",
    response_model=EventDetail,
    responses={404: {"model": ErrorResponse}},
    summary="Event detail (public if published; its club admins and platform admins see any state)",
)
async def get_event(event_id: str, db: DB, user: OptionalUser) -> EventDetail:
    return _detail(await svc.get_visible_event(db, user, to_oid(event_id, "event id")))


@router.patch("/{event_id}", response_model=EventDetail, responses=_manage_errors, summary="Edit an event")
async def update_event(event_id: str, patch: EventPatch, db: DB, user: CurrentUser) -> EventDetail:
    return _detail(await svc.update_event(db, user, to_oid(event_id, "event id"), patch))


@router.post(
    "/{event_id}/submit",
    response_model=EventDetail,
    responses=_manage_errors,
    summary="draft|rejected -> pending_review",
)
async def submit_event(event_id: str, db: DB, user: CurrentUser) -> EventDetail:
    return _detail(await svc.submit_event(db, user, to_oid(event_id, "event id")))


@router.post(
    "/{event_id}/cancel", response_model=EventDetail, responses=_manage_errors, summary="published -> cancelled"
)
async def cancel_event(event_id: str, body: CancelIn, db: DB, user: CurrentUser) -> EventDetail:
    return _detail(await svc.cancel_event(db, user, to_oid(event_id, "event id"), body.reason))


@router.delete("/{event_id}", status_code=204, responses=_manage_errors, summary="Delete a draft")
async def delete_event(event_id: str, db: DB, user: CurrentUser) -> None:
    await svc.delete_draft(db, user, to_oid(event_id, "event id"))


@router.post(
    "/{event_id}/poster",
    response_model=EventDetail,
    responses={**_manage_errors, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
    summary="Upload/replace the poster (PNG/JPEG/WebP, max 5 MB, stored in GridFS)",
)
async def upload_poster(event_id: str, db: DB, user: CurrentUser, file: Annotated[UploadFile, File()]) -> EventDetail:
    data = await file.read(MAX_POSTER_BYTES + 1)  # never buffer more than the limit + 1 byte
    return _detail(await svc.set_poster(db, user, to_oid(event_id, "event id"), data, file.content_type))
