from fastapi import APIRouter

from app.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.errors import ErrorResponse
from app.core.security import create_access_token
from app.models.users import AuthConfigOut, GoogleLoginIn, LoginIn, RegisterIn, TokenOut, UserOut
from app.services import google_auth
from app.services import users as svc
from app.services.serializers import present_user

router = APIRouter(prefix="/auth", tags=["auth"])


async def _token(db, user: dict) -> TokenOut:
    return TokenOut(access_token=create_access_token(str(user["_id"])), user=await present_user(db, user))


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=201,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a student account",
)
async def register(data: RegisterIn, db: DB) -> TokenOut:
    return await _token(db, await svc.register(db, data))


@router.post("/login", response_model=TokenOut, responses={401: {"model": ErrorResponse}}, summary="Log in")
async def login(data: LoginIn, db: DB) -> TokenOut:
    return await _token(db, await svc.authenticate(db, data))


@router.get("/me", response_model=UserOut, responses={401: {"model": ErrorResponse}}, summary="Current user")
async def me(db: DB, user: CurrentUser) -> UserOut:
    return await present_user(db, user)


@router.get("/config", response_model=AuthConfigOut, summary="Public sign-in settings (is Google sign-in available?)")
async def auth_config() -> AuthConfigOut:
    return AuthConfigOut(google_client_id=get_settings().google_client_id or None)


@router.post(
    "/google",
    response_model=TokenOut,
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Sign in or sign up with Google (send the ID token Google gave the browser)",
)
async def google_login(data: GoogleLoginIn, db: DB) -> TokenOut:
    claims = await google_auth.verify_credential(data.credential)
    return await _token(db, await svc.login_with_google(db, claims))
