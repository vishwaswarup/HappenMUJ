from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core import timeutil
from app.core.deps import DB, PlatformAdmin, require_club_admin_for
from app.core.errors import ErrorResponse
from app.models.analytics import BusiestOut, ClubAnalyticsOut, EngagementOut, OverviewOut
from app.models.common import to_oid
from app.services import analytics as svc

router = APIRouter(prefix="/analytics", tags=["analytics"])
_errors = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.get(
    "/overview",
    response_model=OverviewOut,
    responses=_errors,
    summary="Events per category and status; top clubs by saves",
)
async def overview(db: DB, _: PlatformAdmin) -> OverviewOut:
    return await svc.overview(db)


@router.get(
    "/engagement",
    response_model=EngagementOut,
    responses=_errors,
    summary="Per-event funnel: views -> saves -> registration clicks",
)
async def engagement(
    db: DB, _: PlatformAdmin,
    days: Annotated[int, Query(ge=1, le=90, description="Look-back window (interactions are kept 90 days)")] = 30,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    club_id: str | None = None,
) -> EngagementOut:  # fmt: skip
    return await svc.engagement(
        db, timeutil.now(), days=days, limit=limit, club_id=to_oid(club_id, "club id") if club_id else None
    )


@router.get(
    "/busiest-days", response_model=BusiestOut, responses=_errors, summary="Published events per IST weekday and hour"
)
async def busiest_days(db: DB, _: PlatformAdmin) -> BusiestOut:
    return await svc.busiest(db)


@router.get(
    "/clubs/{club_id}",
    response_model=ClubAnalyticsOut,
    responses=_errors,
    dependencies=[Depends(require_club_admin_for("club_id"))],
    summary="Club stats (platform admins, or the club's own admins)",
)
async def club_analytics(club_id: str, db: DB) -> ClubAnalyticsOut:
    return await svc.club_analytics(db, to_oid(club_id, "club id"), timeutil.now())
