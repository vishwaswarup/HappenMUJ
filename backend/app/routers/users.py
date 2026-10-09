from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import ErrorResponse
from app.models.common import to_oid
from app.models.users import UserOut, UserPatch
from app.services import users as svc
from app.services.serializers import present_user

router = APIRouter(prefix="/users", tags=["users"])
_errors = {401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.patch("/me", response_model=UserOut, responses=_errors, summary="Update profile and interests")
async def update_me(patch: UserPatch, db: DB, user: CurrentUser) -> UserOut:
    return await present_user(db, await svc.update_profile(db, user["_id"], patch))


@router.post("/me/follow/{club_id}", response_model=UserOut, responses=_errors, summary="Follow a verified club")
async def follow(club_id: str, db: DB, user: CurrentUser) -> UserOut:
    return await present_user(db, await svc.follow_club(db, user["_id"], to_oid(club_id, "club id")))


@router.delete("/me/follow/{club_id}", response_model=UserOut, responses=_errors, summary="Unfollow a club")
async def unfollow(club_id: str, db: DB, user: CurrentUser) -> UserOut:
    return await present_user(db, await svc.unfollow_club(db, user["_id"], to_oid(club_id, "club id")))
