"""The shapes and paths the React frontend (happenmuj-frontend/src/lib/api/http.ts) depends on."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.main import app

NOW = datetime(2026, 10, 9, 6, 30, tzinfo=UTC)


@pytest.fixture
async def api_client():
    """A client for the `/api` prefix, which is what VITE_API_BASE_URL=/api produces."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as c:
        yield c


async def test_api_prefix_alias_serves_the_same_routes(api_client, client):
    r = await api_client.post("/auth/register", json={"name": "A", "email": "a@example.com", "password": "password123"})
    assert r.status_code == 201
    login = await api_client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert set(login.json()) >= {"access_token", "user"}
    # same data through the versioned prefix
    v1 = await client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert v1.status_code == 200 and v1.json()["email"] == "a@example.com"
    assert (await api_client.get("/clubs")).status_code == 200
    # the alias is hidden from Swagger so /docs lists each endpoint once
    paths = app.openapi()["paths"]
    assert "/api/v1/clubs" in paths and "/api/clubs" not in paths


async def test_cors_allows_the_vite_dev_server(api_client):
    pre = await api_client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = await api_client.options(
        "/auth/login", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers


async def test_register_accepts_interests_and_user_has_managed_club_ids(api_client, client, make_club, admin):
    r = await api_client.post(
        "/auth/register",
        json={"name": "S", "email": "s@example.com", "password": "password123", "interests": ["AI", " ai ", "Music"]},
    )
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["interests"] == ["ai", "music"] and user["managed_club_ids"] == [] and user["role"] == "student"
    club, owner = await make_club("ACM")
    other, _ = await make_club("IEEE")
    # a club admin's /auth/me, login and PATCH responses all carry the clubs they manage
    me = (await api_client.get("/auth/me", headers=owner.headers)).json()
    assert me["role"] == "club_admin" and me["managed_club_ids"] == [club["id"]]
    assert set(me) >= {
        "id",
        "name",
        "email",
        "role",
        "interests",
        "preferred_categories",
        "followed_club_ids",
        "managed_club_ids",
    }
    patched = (await api_client.patch("/users/me", headers=owner.headers, json={"interests": ["x"]})).json()
    assert patched["managed_club_ids"] == [club["id"]]
    # admin of two clubs
    await client.post(f"/admin/clubs/{other['id']}/admins", headers=admin.headers, json={"user_id": owner.id})
    again = (await api_client.get("/auth/me", headers=owner.headers)).json()
    assert set(again["managed_club_ids"]) == {club["id"], other["id"]}
    listed = (await client.get("/admin/users?role=club_admin", headers=admin.headers)).json()["items"]
    assert any(set(u["managed_club_ids"]) == {club["id"], other["id"]} for u in listed)


async def test_every_event_shape_carries_status_and_cancelled_cards_stay_readable(
    api_client, freeze, make_club, make_doc, make_user
):
    freeze()
    club, _ = await make_club("ACM")
    ev = await make_doc(club, NOW + timedelta(days=2), title="gone", status="cancelled", cancelled_at=NOW)
    live = await make_doc(club, NOW + timedelta(days=3), title="live")
    u = await make_user()
    for path in ("/home/tomorrow", "/home/next-7-days", "/events"):
        for item in (await api_client.get(path)).json()["items"]:
            assert item["status"] == "published"
    # cancelled: absent from discovery, readable by id (detail + saved-list flag path)
    assert "gone" not in [i["title"] for i in (await api_client.get("/events")).json()["items"]]
    d = (await api_client.get(f"/events/{ev['_id']}")).json()
    assert d["status"] == "cancelled" and d["cancelled"] is True
    # a user who saved it before it was cancelled still sees it in their list, flagged
    await api_client.post("/saved-events", headers=u.headers, json={"event_id": str(live["_id"])})
    from app import db as dbm

    await dbm.get_db().events.update_one({"_id": live["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": NOW}})
    saved = (await api_client.get("/saved-events", headers=u.headers)).json()["items"][0]
    assert saved["cancelled"] is True and saved["event"]["status"] == "cancelled" and saved["status"] == "saved"
    assert set(saved) >= {"event", "status", "saved_at", "cancelled"}


async def test_saved_list_returns_all_items_by_default(api_client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    u = await make_user()
    docs = [await make_doc(club, NOW + timedelta(days=1, minutes=i)) for i in range(25)]
    for d in docs:
        assert (
            await api_client.post("/saved-events", headers=u.headers, json={"event_id": str(d["_id"])})
        ).status_code == 201
    body = (await api_client.get("/saved-events", headers=u.headers)).json()  # no page_size, like the adapter
    assert body["total"] == 25 and len(body["items"]) == 25


async def test_home_payload_shapes(api_client, freeze, make_club, make_doc, interactions):
    freeze()
    club, _ = await make_club("ACM")
    a = await make_doc(club, NOW + timedelta(days=2), title="A")
    await interactions(a, "view", NOW - timedelta(days=1), 3)
    # suggested: {items, personalised}
    sug = (await api_client.get("/home/suggested")).json()
    assert set(sug) == {"items", "personalised"} and sug["personalised"] is False
    # top: items with rank, flat numeric score_breakdown, window; plus a disclaimer
    top = (await api_client.get("/home/top-events")).json()
    item = top["items"][0]
    assert item["rank"] == 1 and "disclaimer" in top
    assert all(isinstance(v, int | float) for v in item["score_breakdown"].values())
    assert item["window"] == {"saves": 0, "views": 3, "registration_clicks": 0}
    # featured: a bare card, or null (the fallback needs a poster, and A has none)
    assert (await api_client.get("/home/featured")).json() is None
    from bson import ObjectId

    from app import db as dbm

    await dbm.get_db().events.update_one({"_id": a["_id"]}, {"$set": {"poster_file_id": ObjectId()}})
    feat = (await api_client.get("/home/featured")).json()
    assert feat["id"] == str(a["_id"]) and feat["source"] == "fallback" and feat["status"] == "published"
    cfg = (await api_client.get("/home/top-events/config")).json()
    assert (
        set(cfg["weights"]) == {"saves", "views", "registration_clicks", "proximity", "urgency"}
        and cfg["window_days"] == 7
    )


async def test_old_settings_document_with_clicks_key_still_works(api_client, freeze, make_club, make_doc, db):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, NOW + timedelta(days=2))
    await db.settings.update_one(
        {"_id": "ranking"},
        {
            "$set": {
                "weights": {"saves": 0.3, "views": 0.2, "clicks": 0.2, "proximity": 0.2, "urgency": 0.1},
                "window_days": 7,
            }
        },
        upsert=True,
    )
    cfg = (await api_client.get("/home/top-events/config")).json()
    assert "clicks" not in cfg["weights"] and cfg["weights"]["registration_clicks"] == 0.2
    assert len((await api_client.get("/home/top-events")).json()["items"]) == 1
