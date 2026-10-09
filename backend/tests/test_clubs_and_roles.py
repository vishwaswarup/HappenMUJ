import httpx
import pytest
from fastapi import Depends, FastAPI

from app.core.deps import require_club_admin_for, require_role
from app.core.errors import register_error_handlers


async def test_club_request_starts_unverified_and_hidden(client, make_user):
    u = await make_user()
    r = await client.post("/clubs", headers=u.headers, json={"name": "ACM SIGAI", "category": "technical"})
    assert r.status_code == 201
    club = r.json()
    assert club["slug"] == "acm-sigai" and club["verified"] is False
    assert club["requested_by"] == u.id and club["admin_ids"] == []
    # not public
    assert (await client.get("/clubs")).json()["total"] == 0
    assert (await client.get(f"/clubs/{club['id']}")).status_code == 404
    # visible to requester
    assert (await client.get("/clubs/acm-sigai", headers=u.headers)).status_code == 200


async def test_duplicate_club_name_conflict(client, make_user):
    u = await make_user()
    await client.post("/clubs", headers=u.headers, json={"name": "ACM"})
    r = await client.post("/clubs", headers=u.headers, json={"name": "acm"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "club_exists"


async def test_student_cannot_use_admin_endpoints(client, make_user):
    u = await make_user()
    for method, path in [("GET", "/admin/clubs"), ("GET", "/admin/users")]:
        r = await client.request(method, path, headers=u.headers)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"
    r = await client.post("/admin/clubs/000000000000000000000000/verify", headers=u.headers)
    assert r.status_code == 403


async def test_verify_flow_and_public_listing(client, admin, make_user):
    u = await make_user()
    club = (await client.post("/clubs", headers=u.headers, json={"name": "IEEE"})).json()
    pending = await client.get("/admin/clubs?status=pending", headers=admin.headers)
    assert [c["id"] for c in pending.json()["items"]] == [club["id"]]
    r = await client.post(f"/admin/clubs/{club['id']}/verify", headers=admin.headers)
    assert r.json()["verified"] is True and r.json()["verified_by"] == admin.id and r.json()["verified_at"]
    listing = (await client.get("/clubs")).json()
    assert listing["total"] == 1 and listing["page"] == 1 and listing["page_size"] == 20
    assert (await client.get("/clubs?q=iee")).json()["total"] == 1
    assert (await client.get("/clubs?q=zzz")).json()["total"] == 0
    assert (await client.get("/clubs/ieee")).json()["id"] == club["id"]  # by slug
    assert (await client.get("/admin/clubs?status=pending", headers=admin.headers)).json()["total"] == 0


async def test_page_size_capped(client):
    assert (await client.get("/clubs?page_size=51")).status_code == 422


async def test_add_and_remove_admin_changes_role(client, admin, make_user, make_club):
    club, owner = await make_club("Club A")
    assert club["admin_ids"] == [owner.id]
    me = (await client.get("/auth/me", headers=owner.headers)).json()
    assert me["role"] == "club_admin"

    second = await make_user("Second")
    r = await client.post(f"/admin/clubs/{club['id']}/admins", headers=admin.headers, json={"user_id": second.id})
    assert set(r.json()["admin_ids"]) == {owner.id, second.id}
    # idempotent
    r = await client.post(f"/admin/clubs/{club['id']}/admins", headers=admin.headers, json={"user_id": second.id})
    assert len(r.json()["admin_ids"]) == 2

    r = await client.delete(f"/admin/clubs/{club['id']}/admins/{second.id}", headers=admin.headers)
    assert r.json()["admin_ids"] == [owner.id]
    assert (await client.get("/auth/me", headers=second.headers)).json()["role"] == "student"


async def test_removed_admin_keeps_role_if_admin_elsewhere(client, admin, make_club):
    club_a, owner = await make_club("Club A")
    club_b, _ = await make_club("Club B")
    await client.post(f"/admin/clubs/{club_b['id']}/admins", headers=admin.headers, json={"user_id": owner.id})
    await client.delete(f"/admin/clubs/{club_a['id']}/admins/{owner.id}", headers=admin.headers)
    assert (await client.get("/auth/me", headers=owner.headers)).json()["role"] == "club_admin"


async def test_follow_unfollow(client, make_user, make_club):
    club, _ = await make_club("Club A")
    unverified, _ = await make_club("Club U", verified=False)
    u = await make_user()
    r = await client.post(f"/users/me/follow/{club['id']}", headers=u.headers)
    assert r.json()["followed_club_ids"] == [club["id"]]
    r = await client.post(f"/users/me/follow/{club['id']}", headers=u.headers)  # idempotent
    assert r.json()["followed_club_ids"] == [club["id"]]
    assert (await client.post(f"/users/me/follow/{unverified['id']}", headers=u.headers)).status_code == 404
    assert (await client.post("/users/me/follow/not-an-id", headers=u.headers)).status_code == 422
    r = await client.delete(f"/users/me/follow/{club['id']}", headers=u.headers)
    assert r.json()["followed_club_ids"] == []


async def test_platform_admin_role_management(client, admin, make_user):
    u = await make_user()
    r = await client.patch(f"/admin/users/{u.id}/role", headers=admin.headers, json={"role": "club_admin"})
    assert r.json()["role"] == "club_admin"
    assert (
        await client.patch(f"/admin/users/{admin.id}/role", headers=admin.headers, json={"role": "student"})
    ).status_code == 400
    assert (
        await client.patch(f"/admin/users/{u.id}/role", headers=admin.headers, json={"role": "root"})
    ).status_code == 422
    lst = await client.get("/admin/users?role=club_admin", headers=admin.headers)
    assert lst.json()["total"] == 1


# ---- cross-club authorization (dependency-level; real event endpoints arrive in M2) ----


@pytest.fixture
async def guarded_client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/clubs/{club_id}/manage")
    async def manage(club_id: str, user=Depends(require_club_admin_for("club_id"))):
        return {"ok": True, "user": str(user["_id"])}

    @app.get("/staff")
    async def staff(user=Depends(require_role("club_admin", "platform_admin"))):
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_cross_club_access_denied(guarded_client, admin, make_club, make_user):
    club_a, admin_a = await make_club("Club A")
    club_b, admin_b = await make_club("Club B")
    student = await make_user()

    assert (await guarded_client.get(f"/clubs/{club_a['id']}/manage", headers=admin_a.headers)).status_code == 200
    # club admin of A cannot touch B (and vice versa)
    r = await guarded_client.get(f"/clubs/{club_b['id']}/manage", headers=admin_a.headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert (await guarded_client.get(f"/clubs/{club_a['id']}/manage", headers=admin_b.headers)).status_code == 403
    # students denied, platform admin allowed, anonymous 401, unknown club 404
    assert (await guarded_client.get(f"/clubs/{club_a['id']}/manage", headers=student.headers)).status_code == 403
    assert (await guarded_client.get(f"/clubs/{club_a['id']}/manage", headers=admin.headers)).status_code == 200
    assert (await guarded_client.get(f"/clubs/{club_a['id']}/manage")).status_code == 401
    assert (
        await guarded_client.get("/clubs/000000000000000000000000/manage", headers=admin.headers)
    ).status_code == 404


async def test_unverified_club_admin_denied(guarded_client, make_club):
    club, owner = await make_club("Club U", verified=False)
    r = await guarded_client.get(f"/clubs/{club['id']}/manage", headers=owner.headers)
    assert r.status_code == 403


async def test_require_role(guarded_client, make_user, make_club):
    student = await make_user()
    _, ca = await make_club("Club X")
    assert (await guarded_client.get("/staff", headers=student.headers)).status_code == 403
    assert (await guarded_client.get("/staff", headers=ca.headers)).status_code == 200
