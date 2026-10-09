from fastapi import APIRouter

from app.core.deps import DB, CurrentUser
from app.core.errors import ErrorResponse
from app.core.security import create_access_token
from app.models.users import LoginIn, RegisterIn, TokenOut, UserOut
from app.services import users as svc
from app.services.serializers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


def _token(user: dict) -> TokenOut:
    return TokenOut(access_token=create_access_token(str(user["_id"])), user=user_out(user))


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=201,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a student account",
)
async def register(data: RegisterIn, db: DB) -> TokenOut:
    return _token(await svc.register(db, data))


@router.post("/login", response_model=TokenOut, responses={401: {"model": ErrorResponse}}, summary="Log in")
async def login(data: LoginIn, db: DB) -> TokenOut:
    return _token(await svc.authenticate(db, data))


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorResponse}}, summary="Current user")
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)
