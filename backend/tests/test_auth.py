import pytest

from app.config import get_settings


async def test_register_login_me(client):
    r = await client.post("/auth/register", json={"name": "A", "email": "A@Example.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "a@example.com"
    assert r.json()["user"]["role"] == "student"
    assert "password" not in r.text
    r = await client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    token = r.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["name"] == "A"


async def test_password_is_argon2_hashed(client, db):
    await client.post("/auth/register", json={"name": "A", "email": "a@example.com", "password": "password123"})
    u = await db.users.find_one({"email": "a@example.com"})
    assert u["password_hash"].startswith("$argon2")
    assert u["schema_v"] == 1


async def test_duplicate_email_conflict(client):
    body = {"name": "A", "email": "a@example.com", "password": "password123"}
    await client.post("/auth/register", json=body)
    r = await client.post("/auth/register", json={**body, "email": "A@example.com"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


async def test_wrong_password_and_unknown_user(client, make_user):
    u = await make_user(email="a@example.com")
    for email, pw in [("a@example.com", "nope-nope-1"), ("ghost@example.com", "password123")]:
        r = await client.post("/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"
    assert u


async def test_short_password_validation_error_shape(client):
    r = await client.post("/auth/register", json={"name": "A", "email": "a@example.com", "password": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_me_requires_valid_token(client):
    assert (await client.get("/auth/me")).status_code == 401
    r = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_email_domain_restriction(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_email_domains", "jaipur.manipal.edu")
    bad = await client.post("/auth/register", json={"name": "A", "email": "a@gmail.com", "password": "password123"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "email_domain_not_allowed"
    ok = await client.post(
        "/auth/register", json={"name": "A", "email": "a@jaipur.manipal.edu", "password": "password123"}
    )
    assert ok.status_code == 201


async def test_platform_admin_bootstrap(admin, db):
    assert admin.user["role"] == "platform_admin"
    from app.services.users import bootstrap_platform_admin

    before = (await db.users.find_one({"email": "admin@example.com"}))["password_hash"]
    await bootstrap_platform_admin(db)  # must not overwrite
    assert (await db.users.find_one({"email": "admin@example.com"}))["password_hash"] == before
    assert await db.users.count_documents({"role": "platform_admin"}) == 1


async def test_update_profile_normalizes_interests(client, make_user):
    u = await make_user()
    r = await client.patch(
        "/users/me",
        headers=u.headers,
        json={"interests": ["AI", " ai ", "Machine Learning"], "preferred_categories": ["technical", "hackathon"]},
    )
    assert r.status_code == 200
    assert r.json()["interests"] == ["ai", "machine learning"]
    bad = await client.patch("/users/me", headers=u.headers, json={"preferred_categories": ["nonsense"]})
    assert bad.status_code == 422
    empty = await client.patch("/users/me", headers=u.headers, json={})
    assert empty.status_code == 400


@pytest.mark.parametrize("method,path", [("PATCH", "/users/me"), ("POST", "/clubs"), ("GET", "/admin/users")])
async def test_protected_routes_need_auth(client, method, path):
    r = await client.request(method, path, json={})
    assert r.status_code == 401
