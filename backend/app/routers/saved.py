from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core import timeutil
from app.core.deps import DB, CurrentUser
from app.core.errors import ErrorResponse
from app.models.common import Page, PageParams, to_oid
from app.models.saved import CalendarOut, SavedEventOut, SavedRecord, SaveIn
from app.services import saved as svc

router = APIRouter(tags=["saved"])
_errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def _record(doc: dict) -> SavedRecord:
    return SavedRecord(
        id=str(doc["_id"]), event_id=str(doc["event_id"]), status=doc["status"],
        event_start=doc["event_start"], created_at=doc["created_at"],
    )  # fmt: skip


@router.post(
    "/saved-events",
    response_model=SavedRecord,
    status_code=201,
    responses=_errors,
    summary="Save an event (transaction; idempotent: saving twice returns 200 with the existing record)",
)
async def save_event(body: SaveIn, response: Response, db: DB, user: CurrentUser) -> SavedRecord:
    doc, created = await svc.save_event(db, user["_id"], to_oid(body.event_id, "event id"))
    if not created:
        response.status_code = 200
    return _record(doc)


@router.delete(
    "/saved-events/{event_id}",
    status_code=204,
    responses={401: {"model": ErrorResponse}},
    summary="Unsave (idempotent)",
)
async def unsave_event(event_id: str, db: DB, user: CurrentUser) -> None:
    await svc.unsave_event(db, user["_id"], to_oid(event_id, "event id"))


@router.get("/saved-events", response_model=Page[SavedEventOut], responses=_errors, summary="My saved events")
async def list_saved(
    db: DB, user: CurrentUser, pp: Annotated[PageParams, Depends()], upcoming: bool = False
) -> Page[SavedEventOut]:
    items, total = await svc.list_saved(
        db, user["_id"], timeutil.now(), upcoming=upcoming, skip=pp.skip, limit=pp.page_size
    )
    return Page(items=items, total=total, page=pp.page, page_size=pp.page_size)


@router.get(
    "/calendar",
    response_model=CalendarOut,
    responses=_errors,
    summary="Saved events in an IST month, grouped by IST date",
)
async def calendar(
    db: DB, user: CurrentUser,
    year: Annotated[int, Query(ge=2000, le=2100)], month: Annotated[int, Query(ge=1, le=12)],
) -> CalendarOut:  # fmt: skip
    return await svc.calendar(db, user["_id"], timeutil.now(), year, month)
