"""Sign-up (name, personal email, password) and Google sign-in.

Google's servers are never contacted: ``google_auth.verify_credential`` is replaced by a stand-in that returns
the claims Google would, or raises what the real one raises.
"""

import pytest

from app.config import get_settings
from app.core.errors import AppError
from app.services import google_auth

PW = "password123"


def reg_body(**over):
    return {"name": "Aarav Sharma", "email": "aarav@gmail.com", "password": PW, **over}


@pytest.fixture
def google(monkeypatch):
    """Configure a client id and a fake Google. Usage: google.claims = {...}"""

    class Fake:
        claims = {"sub": "g-1", "email": "student@gmail.com", "email_verified": True, "name": "Google Student"}
        fail: AppError | None = None

    monkeypatch.setattr(get_settings(), "google_client_id", "test-client-id.apps.googleusercontent.com")

    async def fake_verify(credential: str):
        if Fake.fail:
            raise Fake.fail
        assert credential == "a-google-id-token"
        return dict(Fake.claims)

    monkeypatch.setattr(google_auth, "verify_credential", fake_verify)
    return Fake


async def g_login(client, token="a-google-id-token"):
    return await client.post("/auth/google", json={"credential": token})


# ---------------------------------------------------------------- password sign-up
async def test_register_with_a_personal_email_marks_it_unverified(client, db):
    r = await client.post("/auth/register", json=reg_body())
    assert r.status_code == 201, r.text
    u = r.json()["user"]
    assert u["email"] == "aarav@gmail.com" and u["role"] == "student"
    assert u["email_verified"] is False and u["auth_providers"] == ["password"]  # a typed-in address proves nothing
    stored = await db.users.find_one({"email": "aarav@gmail.com"})
    assert stored["google_sub"] is None and stored["password_hash"].startswith("$argon2")


async def test_college_email_is_not_required_or_checked(client):
    # sign-up takes any address the student owns; the college Outlook address is not needed
    assert (await client.post("/auth/register", json=reg_body(email="someone@outlook.com"))).status_code == 201


async def test_users_unique_google_index_is_partial(db):
    info = await db.users.index_information()
    assert info["google_sub_unique"]["unique"] is True
    assert info["google_sub_unique"]["partialFilterExpression"] == {"google_sub": {"$type": "string"}}


# ---------------------------------------------------------------- Google sign-in
async def test_auth_config_reports_whether_google_is_available(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    assert (await client.get("/auth/config")).json() == {"google_client_id": None}
    monkeypatch.setattr(get_settings(), "google_client_id", "abc.apps.googleusercontent.com")
    assert (await client.get("/auth/config")).json() == {"google_client_id": "abc.apps.googleusercontent.com"}


async def test_google_not_configured_is_a_clear_503(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_client_id", "")
    r = await g_login(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "google_not_configured"


async def test_first_google_sign_in_creates_a_verified_student(client, db, google):
    r = await g_login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    u = body["user"]
    assert body["access_token"] and u["role"] == "student" and u["name"] == "Google Student"
    assert u["email"] == "student@gmail.com" and u["email_verified"] is True and u["auth_providers"] == ["google"]
    stored = await db.users.find_one({"email": "student@gmail.com"})
    assert stored["google_sub"] == "g-1" and stored["password_hash"] is None and stored["schema_v"] == 1
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "student@gmail.com"


async def test_second_google_sign_in_returns_the_same_account(client, db, google):
    first = (await g_login(client)).json()["user"]["id"]
    google.claims = {**google.claims, "email": "renamed-in-google@gmail.com"}  # same Google id, different email
    second = (await g_login(client)).json()["user"]
    assert second["id"] == first and second["email"] == "student@gmail.com"
    assert await db.users.count_documents({}) == 2  # the platform admin + this one


async def test_google_signing_in_to_a_password_account_links_it_and_removes_the_password(client, db, google):
    # Someone pre-registers a victim's address with a password they know...
    pre = await client.post("/auth/register", json=reg_body(email="student@gmail.com"))
    assert pre.status_code == 201
    # ...then the real owner signs in with Google. The account is linked, and the attacker's password is gone.
    r = await g_login(client)
    assert r.status_code == 200 and r.json()["user"]["id"] == pre.json()["user"]["id"]
    u = r.json()["user"]
    assert u["email_verified"] is True and u["auth_providers"] == ["password", "google"]
    stored = await db.users.find_one({"email": "student@gmail.com"})
    assert stored["password_hash"] is None and stored["google_sub"] == "g-1"
    blocked = await client.post("/auth/login", json={"email": "student@gmail.com", "password": PW})
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "use_google_sign_in"


async def test_google_only_account_cannot_use_password_login(client, google):
    await g_login(client)
    r = await client.post("/auth/login", json={"email": "student@gmail.com", "password": "anything-at-all"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "use_google_sign_in"
    r = await client.post("/auth/login", json={"email": "nobody@gmail.com", "password": "anything-at-all"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "err",
    [
        AppError(401, "unauthorized", "Google sign-in failed. Please try again."),
        AppError(503, "google_unreachable", "x"),
    ],
)
async def test_google_failures_are_reported_not_swallowed(client, google, err):
    google.fail = err
    r = await g_login(client)
    assert r.status_code == err.status_code and r.json()["error"]["code"] == err.code


async def test_the_real_verifier_rejects_bad_tokens_and_unverified_emails(client, monkeypatch):
    """Exercise the real ``verify_credential`` with Google's library stubbed out (no network)."""
    monkeypatch.setattr(get_settings(), "google_client_id", "id.apps.googleusercontent.com")

    def raise_value_error(*a, **k):
        raise ValueError("Token used too late")

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", raise_value_error)
    r = await g_login(client, "not-a-real-token")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"

    unverified = {"sub": "x", "email": "a@gmail.com", "email_verified": False}
    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", lambda *a, **k: unverified)
    r = await g_login(client, "a-token-that-parses")
    assert r.status_code == 401 and "not verified" in r.json()["error"]["message"]

    seen = {}

    def good(token, request, audience):
        seen["audience"] = audience  # the token must be checked against OUR client id
        return {"sub": "g-9", "email": "ok@gmail.com", "email_verified": True, "name": "Ok"}

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", good)
    r = await g_login(client, "a-valid-token")
    assert r.status_code == 200 and seen["audience"] == "id.apps.googleusercontent.com"


async def test_users_validator_allows_google_only_accounts(db, google, client):
    await g_login(client)  # password_hash is null: the $jsonSchema validator must accept that
    assert await db.users.count_documents({"password_hash": None}) == 1


async def test_google_users_can_post_like_anyone_else(client, google):
    tok = (await g_login(client)).json()["access_token"]
    r = await client.post(
        "/posts", headers={"Authorization": f"Bearer {tok}"}, json={"title": "Hello", "body": "World"}
    )
    assert r.status_code == 201
