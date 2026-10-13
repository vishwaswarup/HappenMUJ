import pytest

from app.config import Settings, get_settings, is_local_uri
from app.core import ratelimit
from app.main import app, lifespan

GOOD = dict(
    jwt_secret="x" * 40,
    platform_admin_password="a-long-real-password",
    platform_admin_email="ops@example.org",
    cors_origins="https://happenmuj.example.org",
)


def test_production_problems_flags_placeholders_and_accepts_real_values():
    placeholders = dict(
        jwt_secret="change-me-in-production-use-32+-bytes",
        platform_admin_password="demo1234",
        platform_admin_email="admin@muj-demo.edu",
        cors_origins="http://localhost:5173",
    )
    assert len(Settings(app_env="production", **placeholders).production_problems()) == 4
    assert Settings(app_env="production", **GOOD).production_problems() == []


async def test_startup_refuses_unsafe_production_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")  # test env uses placeholder-ish values
    monkeypatch.setattr(get_settings(), "platform_admin_password", "demo1234")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        async with lifespan(app):
            pass


@pytest.mark.parametrize(
    ("uri", "local"),
    [
        ("mongodb://localhost:27018/?replicaSet=rs0", True),
        ("mongodb://127.0.0.1:27017", True),
        ("mongodb+srv://u:p@cluster0.abc.mongodb.net/db", False),
        ("mongodb://u:p@db.example.com:27017/db", False),
    ],
)
def test_is_local_uri(uri, local):
    assert is_local_uri(uri) is local


async def test_auth_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_auth", 3)
    ratelimit.reset()
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    codes = [(await client.post("/auth/login", json=body)).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    r = await client.post("/auth/login", json=body)
    assert r.json()["error"]["code"] == "rate_limited"
    ratelimit.reset()


async def test_api_health_alias(client):
    import httpx

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/health")).json()["status"] == "ok"
        assert (await c.get("/health")).status_code == 200


async def test_bootstrap_admin_has_sign_in_fields(db):
    admin = await db.users.find_one({"email": "admin@example.com"})
    assert admin["email_verified"] is True and admin["auth_providers"] == ["password"]
