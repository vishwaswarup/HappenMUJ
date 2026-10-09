from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db as db_module
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.indexes import create_indexes
from app.routers import admin, auth, clubs, events, files, home, meta, saved, users
from app.services.settings import ensure_ranking_settings
from app.services.users import bootstrap_platform_admin
from app.validators import apply_validators


async def prepare_database() -> None:
    """Validators, indexes and platform-admin bootstrap. Idempotent; runs at every startup."""
    db = db_module.get_db()
    await apply_validators(db)
    await create_indexes(db)
    await bootstrap_platform_admin(db)
    await ensure_ranking_settings(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db_module.init_db()
    await prepare_database()
    yield
    await db_module.close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HappenMUJ API",
        version="0.1.0",
        description="Campus event discovery and community platform for Manipal University Jaipur.",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for r in (
        auth.router,
        users.router,
        clubs.router,
        events.router,
        home.router,
        saved.router,
        files.router,
        meta.router,
        admin.router,
    ):
        api.include_router(r)
    app.include_router(api)

    @app.get("/health", tags=["meta"], summary="Liveness + MongoDB connectivity")
    async def health() -> dict:
        db = db_module.get_db()
        hello = await db.command("hello")
        return {
            "status": "ok",
            "db": db.name,
            "replica_set": hello.get("setName"),
            "transactions_supported": bool(hello.get("setName")),
        }

    return app


app = create_app()
