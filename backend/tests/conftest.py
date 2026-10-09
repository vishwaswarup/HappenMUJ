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

from app import db as db_module  # noqa: E402
from app.core import timeutil  # noqa: E402
from app.db import COLLECTIONS  # noqa: E402
from app.main import app, prepare_database  # noqa: E402


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
