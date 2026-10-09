from datetime import UTC, datetime, timedelta

import pytest

from app.seed import CLUBS, DEMO_ADMIN, DEMO_STUDENT, PASSWORD, E, run_seed

ACM_ADMIN = "acm@muj-demo.edu"


async def login(client, email: str, password: str = PASSWORD) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, (email, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def check_counts_and_shapes(seeded, db):
    c = seeded["counts"]
    assert c["clubs"] == 16 == len(CLUBS) and await db.clubs.count_documents({"verified": True}) == 16
    assert c["events"] == 40 == len(E) and c["saved_events"] == 180 and c["event_interactions"] == 1600
    assert (c["posts"], c["comments"], c["reactions"]) == (12, 50, 100)
    # the demo platform admin exists (the test environment's own bootstrap admin may add a second one)
    assert await db.users.count_documents({"email": DEMO_ADMIN, "role": "platform_admin"}) == 1
    assert await db.users.count_documents({"role": "club_admin"}) == 16  # one admin per club
    assert await db.users.count_documents({"role": "student"}) == 25
    status = seeded["events_by_status"]
    assert status == {"published": 31, "cancelled": 3, "pending_review": 4, "draft": 1, "rejected": 1}
    # the real MUJ club slugs, lowercase and hyphenated
    slugs = set(await db.clubs.distinct("slug"))
    assert {"acm", "ieee-sb", "ieee-cs", "ieee-wie", "litmus", "randomize", "garuda", "de-artistry-club",
            "the-musical-club-tmc", "choreographia", "rotaract", "omphalos", "cinephilia", "marksoc",
            "managia", "glitch"} == slugs  # fmt: skip
    cats = {n: cat for n, cat, _ in CLUBS}
    assert cats["LITMUS"] == "debating" and cats["GLITCH"] == "gaming" and cats["ROTARACT"] == "social"
    # events of many shapes coexist, with fee/team variety including "not specified"
    assert len(await db.events.distinct("event_type")) >= 7
    types = await db.events.distinct("event_type")
    shapes = {frozenset((await db.events.find_one({"event_type": t}))["details"]) for t in types}
    assert len(shapes) >= 6
    assert await db.events.count_documents({"fee.type": "not_specified"}) >= 3
    assert len(await db.events.distinct("fee.type")) >= 4
    assert await db.events.count_documents({"featured.is_featured": True}) == 1  # exactly one featured
    posters = await db.events.count_documents({"poster_file_id": {"$ne": None}})
    assert 0.5 * 40 <= posters <= 0.9 * 40 and c["posters (fs.files)"] == posters
    # every club has events
    assert len(await db.events.distinct("club_id")) == 16


async def check_counters_are_consistent(db):
    async for e in db.events.find():
        for stat, kind in (("saves", "save"), ("views", "view"), ("registration_clicks", "registration_click")):
            n = await db.event_interactions.count_documents({"event_id": e["_id"], "type": kind})
            assert e["stats"][stat] == n, (e["title"], stat)
        assert e["stats"]["saves"] == await db.saved_events.count_documents({"event_id": e["_id"]})
    async for p in db.posts.find():
        assert p["comment_count"] == await db.comments.count_documents({"post_id": p["_id"], "status": "active"})
        assert len(p["recent_comments"]) == min(3, p["comment_count"])
        kinds = {
            k: await db.reactions.count_documents({"target_id": p["_id"], "kind": k}) for k in ("like", "insightful")
        }
        assert p["reaction_counts"] == kinds
    # schema versioning pattern: EVERY document in every collection carries schema_v: 1
    for coll in (
        "users",
        "clubs",
        "events",
        "saved_events",
        "event_interactions",
        "posts",
        "comments",
        "reactions",
        "settings",
    ):
        assert await db[coll].estimated_document_count() > 0, coll
        assert await db[coll].count_documents({"schema_v": {"$ne": 1}}) == 0, f"{coll} has documents without schema_v"
    now = datetime.now(UTC)
    oldest = await db.event_interactions.find_one({}, sort=[("ts", 1)])
    assert now - timedelta(days=14, hours=1) <= oldest["ts"] <= now
    parents = await db.comments.distinct("parent_id", {"parent_id": {"$ne": None}})
    assert parents and await db.comments.count_documents({"_id": {"$in": parents}, "parent_id": {"$ne": None}}) == 0


async def check_demo_logins_and_roles(client):
    expect = {DEMO_STUDENT: ("student", []), ACM_ADMIN: ("club_admin", None), DEMO_ADMIN: ("platform_admin", [])}
    for email, (role, managed) in expect.items():
        r = await client.post("/auth/login", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, (email, r.text)
        u = r.json()["user"]
        assert u["role"] == role
        if managed is not None:
            assert u["managed_club_ids"] == managed
        else:
            assert len(u["managed_club_ids"]) == 1  # the ACM admin manages exactly ACM


async def check_homepage_is_populated(client):
    stu = await login(client, DEMO_STUDENT)
    f = (await client.get("/home/featured")).json()
    assert f["source"] == "featured" and f["featured"] is True and f["title"] == "HackMUJ 24h"
    top = (await client.get("/home/top-events")).json()["items"]
    assert len(top) == 10 and [i["rank"] for i in top] == list(range(1, 11))
    assert len((await client.get("/home/next-7-days")).json()["items"]) >= 5
    assert len((await client.get("/home/tomorrow")).json()["items"]) >= 5
    sug = (await client.get("/home/suggested", headers=stu)).json()
    assert sug["personalised"] is True and len(sug["items"]) >= 5
    assert (await client.get("/home/suggested")).json()["personalised"] is False
    cat = (await client.get("/events?page_size=50")).json()
    assert cat["total"] == 26 and set(cat["facets"]) == {"category", "club"}  # published AND upcoming
    assert sum(cat["facets"]["category"].values()) == cat["total"]
    assert (await client.get("/clubs?page_size=50")).json()["total"] == 16
    assert (await client.get("/posts")).json()["total"] == 12
    # nothing non-public leaks into discovery; cancelled stays readable by id; pending/draft/rejected do not
    ids = {i["id"] for i in cat["items"]} | {i["id"] for i in top}
    for item in cat["items"]:
        d = (await client.get(f"/events/{item['id']}")).json()
        assert d["status"] == "published" and item["status"] == "published"
    acm = await login(client, ACM_ADMIN)
    mine = (await client.get("/events/mine?page_size=50", headers=acm)).json()["items"]
    assert {m["status"] for m in mine} >= {"published", "draft"}  # ACM has a published event and a draft
    admin = await login(client, DEMO_ADMIN)
    cancelled = (await client.get("/admin/events?status=cancelled", headers=admin)).json()["items"]
    assert len(cancelled) == 3
    for ev in cancelled:
        assert ev["id"] not in ids
        r = await client.get(f"/events/{ev['id']}")
        assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["cancel_reason"]
    pending = (await client.get("/admin/events?status=pending_review", headers=admin)).json()["items"]
    assert len(pending) == 4 and (await client.get(f"/events/{pending[0]['id']}")).status_code == 404


async def check_demo_students_overlapping_saves(client):
    stu = await login(client, DEMO_STUDENT)
    saved = (await client.get("/saved-events", headers=stu)).json()["items"]
    assert len(saved) >= 6
    spans = sorted((s["event"]["schedule"]["start"], s["event"]["schedule"]["end"], s["event"]["title"]) for s in saved)
    overlaps = [(a[2], b[2]) for i, a in enumerate(spans) for b in spans[i + 1 :] if b[0] < a[1]]
    assert ("Intro to Generative AI", "Open Mic Night") in overlaps  # the pair the calendar warns about
    assert any(s["status"] in ("saved", "registration_initiated") for s in saved)


async def check_analytics(client):
    admin = await login(client, DEMO_ADMIN)
    o = (await client.get("/analytics/overview", headers=admin)).json()
    assert o["totals"]["events"] == 40 and sum(c["count"] for c in o["events_by_status"]) == 40
    assert sum(c["count"] for c in o["events_by_category"]) == 31
    e = (await client.get("/analytics/engagement?days=30", headers=admin)).json()
    assert e["totals"]["saves"] == 180 and e["totals"]["views"] == 1300 and 0 < e["totals"]["view_to_save"] < 1
    b = (await client.get("/analytics/busiest-days", headers=admin)).json()
    assert b["total_events"] == 31 == sum(w["count"] for w in b["by_weekday"])
    acm = await login(client, ACM_ADMIN)
    cid = (await client.get("/clubs/acm")).json()["id"]
    r = await client.get(f"/analytics/clubs/{cid}", headers=acm)
    assert r.status_code == 200 and r.json()["name"] == "ACM"


async def test_seed_end_to_end(db, client):
    """Seed once (about 10 s), then verify data, counters, the public API and analytics."""
    seeded = await run_seed(db, reset=True)
    await check_counts_and_shapes(seeded, db)
    await check_counters_are_consistent(db)
    assert seeded["credentials"] == {
        "student": (DEMO_STUDENT, PASSWORD), "club_admin": (ACM_ADMIN, PASSWORD), "platform_admin": (DEMO_ADMIN, PASSWORD)
    }  # fmt: skip
    await check_demo_logins_and_roles(client)
    await check_homepage_is_populated(client)
    await check_demo_students_overlapping_saves(client)
    await check_analytics(client)


async def test_seed_is_deterministic_and_refuses_to_overwrite(db):
    first = await run_seed(db, reset=True)

    async def fingerprint():
        return sorted(
            (e["title"], e["status"], e["fee"]["type"], e["category"]) for e in await db.events.find().to_list(None)
        )

    one = await fingerprint()
    second = await run_seed(db, reset=True)  # idempotent: --reset twice gives the same dataset
    assert one == await fingerprint() and first["counts"] == second["counts"]
    with pytest.raises(SystemExit):  # without --reset it must not mix with existing data
        await run_seed(db, reset=False)
