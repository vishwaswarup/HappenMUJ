import os

# Must be set before the app is imported: tests never touch the dev database.
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27018/?replicaSet=rs0")
os.environ["DB_NAME"] = "happenmuj_test"
os.environ["ALLOWED_EMAIL_DOMAINS"] = ""
os.environ["PLATFORM_ADMIN_EMAIL"] = "admin@example.com"
os.environ["PLATFORM_ADMIN_PASSWORD"] = "admin-password-1"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

# Tests only: cheap argon2 parameters (production keeps the library defaults).
from argon2 import PasswordHasher  # noqa: E402

from app import db as db_module  # noqa: E402
from app.core import (
    security,  # noqa: E402
    timeutil,  # noqa: E402
)
from app.db import COLLECTIONS  # noqa: E402
from app.main import app, prepare_database  # noqa: E402

security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _database():
    db = await db_module.init_db()
    assert db.name.endswith("_test"), "refusing to run tests against a non-test database"
    await db.client.drop_database(db.name)
    await prepare_database()
    yield db
    await db.client.drop_database(db.name)
    await db_module.close_db()


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def _clean(_database):
    """Empty every collection between tests (indexes and validators stay), then re-bootstrap admin."""
    from app.services.users import bootstrap_platform_admin

    for name in [*COLLECTIONS, "fs.files", "fs.chunks"]:
        await _database[name].delete_many({})
    await bootstrap_platform_admin(_database)
    yield
    timeutil.reset_clock()


@pytest.fixture
def db(_database):
    return _database


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


class Actor:
    def __init__(self, user: dict, token: str):
        self.user, self.token = user, token
        self.id = user["id"]
        self.headers = {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def make_user(client):
    counter = 0

    async def _make(name: str = "Student", email: str | None = None, password: str = "password123") -> Actor:
        nonlocal counter
        counter += 1
        r = await client.post(
            "/auth/register", json={"name": name, "email": email or f"user{counter}@example.com", "password": password}
        )
        assert r.status_code == 201, r.text
        body = r.json()
        return Actor(body["user"], body["access_token"])

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def admin(client):
    r = await client.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-1"})
    assert r.status_code == 200, r.text
    return Actor(r.json()["user"], r.json()["access_token"])


@pytest_asyncio.fixture(loop_scope="session")
async def make_club(client, admin, make_user):
    """Create a verified club with one club-admin user. Returns (club, club_admin_actor)."""
    counter = 0

    async def _make(name: str | None = None, verified: bool = True):
        nonlocal counter
        counter += 1
        owner = await make_user(f"Owner {counter}")
        r = await client.post(
            "/clubs", headers=owner.headers, json={"name": name or f"Club {counter}", "category": "technical"}
        )
        assert r.status_code == 201, r.text
        club = r.json()
        if verified:
            r = await client.post(f"/admin/clubs/{club['id']}/verify", headers=admin.headers)
            assert r.status_code == 200, r.text
            club = r.json()
        r = await client.post(f"/admin/clubs/{club['id']}/admins", headers=admin.headers, json={"user_id": owner.id})
        assert r.status_code == 200, r.text
        club = r.json()
        owner.user["role"] = "club_admin"
        return club, owner

    return _make


@pytest.fixture
def event_payload():
    """Build a valid event body; override any field via kwargs."""
    from datetime import UTC, datetime, timedelta

    def _make(club_id: str, **over) -> dict:
        start = datetime.now(UTC) + timedelta(days=5)
        body = {
            "club_id": club_id,
            "title": "Intro to GenAI",
            "one_liner": "Hands-on workshop on building with LLMs.",
            "description": "Bring a laptop.",
            "category": "technical",
            "event_type": "workshop",
            "tags": ["AI", "GenAI"],
            "schedule": {"start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat()},
            "venue": {"name": "AB3 Seminar Hall", "building": "AB3"},
            "fee": {"type": "free"},
            "team": {"type": "individual"},
            "registration": {"required": True, "platform": "google_forms", "url": "https://forms.gle/x"},
            "details": {"topics": ["LLMs"], "bring_own_laptop": True},
        }
        body.update(over)
        return body

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def make_event(client, event_payload):
    async def _make(club_id: str, actor, *, status: str = "draft", admin=None, **over) -> dict:
        r = await client.post("/events", headers=actor.headers, json=event_payload(club_id, **over))
        assert r.status_code == 201, r.text
        ev = r.json()
        if status in ("pending_review", "published", "cancelled"):
            r = await client.post(f"/events/{ev['id']}/submit", headers=actor.headers)
            assert r.status_code == 200, r.text
        if status in ("published", "cancelled"):
            r = await client.post(f"/admin/events/{ev['id']}/approve", headers=admin.headers)
            assert r.status_code == 200, r.text
        if status == "cancelled":
            r = await client.post(f"/events/{ev['id']}/cancel", headers=actor.headers, json={"reason": "Speaker ill"})
            assert r.status_code == 200, r.text
        return r.json() if status != "draft" else ev

    return _make


NOW = None  # set per test via freeze()


@pytest.fixture
def freeze():
    """Freeze the app clock. Default: 2026-10-09 12:00 IST (06:30 UTC)."""
    from datetime import UTC, datetime

    def _freeze(dt: datetime | None = None) -> datetime:
        dt = dt or datetime(2026, 10, 9, 6, 30, tzinfo=UTC)
        timeutil.freeze_time(dt)
        return dt

    return _freeze


@pytest_asyncio.fixture(loop_scope="session")
async def make_doc(db):
    """Insert a published event document directly (full control over time/stats/status)."""
    from datetime import timedelta

    from bson import ObjectId

    from app.core import timeutil as tu

    n = 0

    async def _make(club: dict, start, *, hours: int = 2, **over) -> dict:
        nonlocal n
        n += 1
        now = tu.now()
        doc = {
            "title": f"Event {n}",
            "one_liner": f"One liner {n}",
            "description": "",
            "club_id": ObjectId(club["id"]),
            "club_snapshot": {"name": club["name"], "slug": club["slug"]},
            "creator_id": ObjectId(),
            "category": "technical",
            "event_type": "workshop",
            "tags": [],
            "poster_file_id": None,
            "schedule": {"start": start, "end": start + timedelta(hours=hours)},
            "venue": {"name": "AB3", "building": "AB3", "room": None},
            "fee": {"type": "free", "amount": None, "currency": "INR"},
            "team": {"type": "individual", "min": None, "max": None},
            "registration": {"required": True, "platform": "other", "url": "https://x.example.com", "deadline": None},
            "contact": None,
            "details": {},
            "status": "published",
            "rejection_reason": None,
            "cancel_reason": None,
            "cancelled_at": None,
            "featured": {"is_featured": False, "featured_at": None},
            "stats": {"views": 0, "saves": 0, "registration_clicks": 0},
            "change_log": [],
            "created_at": now,
            "updated_at": now,
            "published_at": now,
            "schema_v": 1,
        }
        doc.update(over)
        doc["_id"] = (await db.events.insert_one(doc)).inserted_id
        return doc

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def interactions(db):
    from bson import ObjectId

    async def _add(event, kind: str, ts, count: int = 1):
        await db.event_interactions.insert_many(
            [{"event_id": event["_id"], "user_id": ObjectId(), "type": kind, "ts": ts} for _ in range(count)]
        )

    return _add
