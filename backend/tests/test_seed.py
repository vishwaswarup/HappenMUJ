from datetime import UTC, datetime, timedelta

import pytest

from app.seed import run_seed


async def check_seed_counts_and_shapes(seeded, db):
    c = seeded["counts"]
    assert c["clubs"] == 12 and await db.clubs.count_documents({"verified": True}) == 10
    assert (
        await db.users.count_documents({"role": "student"}) >= 40
        and await db.users.count_documents({"role": "platform_admin"}) == 1
    )
    assert c["events"] == 55 and c["saved_events"] == 400
    assert 2900 <= c["event_interactions"] <= 3100
    assert c["posts"] == 20 and c["comments"] == 120 and c["reactions"] == 300
    # events of every type and every category coexist, with different `details` shapes
    assert len(await db.events.distinct("event_type")) == 8
    assert sorted(await db.events.distinct("category")) == sorted(
        ["technical", "cultural", "debating", "sports", "academic", "career", "hackathon", "workshop", "competition", "seminar", "social", "gaming", "other"]
    )  # fmt: skip
    shapes = {
        frozenset((await db.events.find_one({"event_type": t}))["details"])
        for t in await db.events.distinct("event_type")
    }
    assert len(shapes) >= 6
    status = seeded["events_by_status"]
    assert {"published", "cancelled", "pending_review", "draft", "rejected"} <= set(status)
    # fee/team variety, including "not specified"
    assert await db.events.count_documents({"fee.type": "not_specified"}) >= 5
    assert len(await db.events.distinct("fee.type")) == 5 and len(await db.events.distinct("team.type")) >= 4
    assert await db.events.count_documents({"featured.is_featured": True}) == 3
    posters = await db.events.count_documents({"poster_file_id": {"$ne": None}})
    assert 0.55 * 55 <= posters <= 0.85 * 55 and c["posters (fs.files)"] == posters


async def check_seed_counters_are_consistent(seeded, db):
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
    # interactions are spread over the last 14 days (well inside the 90-day TTL)
    now = datetime.now(UTC)
    oldest = await db.event_interactions.find_one({}, sort=[("ts", 1)])
    assert now - timedelta(days=14, hours=1) <= oldest["ts"] <= now
    # threading never exceeds 2 levels
    assert await db.comments.count_documents({"parent_id": {"$ne": None}}) > 0
    parents = await db.comments.distinct("parent_id", {"parent_id": {"$ne": None}})
    assert await db.comments.count_documents({"_id": {"$in": parents}, "parent_id": {"$ne": None}}) == 0


async def check_seeded_api_homepage_is_fully_populated(seeded, client):
    login = await client.post(
        "/auth/login", json={"email": seeded["credentials"]["student"][0], "password": "password123"}
    )
    stu = {"Authorization": f"Bearer {login.json()['access_token']}"}
    f = (await client.get("/home/featured")).json()
    assert f["source"] == "featured" and f["event"]["featured"] is True
    top = (await client.get("/home/top-events")).json()["items"]
    assert len(top) == 10 and [i["rank"] for i in top] == list(range(1, 11))
    assert top[0]["score"] >= top[-1]["score"]
    assert len((await client.get("/home/next-7-days")).json()["items"]) >= 5
    assert len((await client.get("/home/tomorrow")).json()["items"]) >= 1
    sug = (await client.get("/home/suggested", headers=stu)).json()
    assert sug["personalized"] is True and len(sug["items"]) == 10
    assert (await client.get("/home/suggested")).json()["personalized"] is False
    cat = (await client.get("/events")).json()
    assert cat["total"] > 20 and len(cat["facets"]["categories"]) >= 10
    assert (await client.get("/clubs")).json()["total"] == 10  # the 2 pending clubs are hidden
    assert (await client.get("/posts")).json()["total"] == 20
    # nothing non-public leaks: every card the catalogue/top-10 returns resolves publicly, and its status is published
    for item in [*cat["items"], *top]:
        detail = await client.get(f"/events/{item['id']}")
        assert detail.status_code == 200 and detail.json()["status"] == "published"


async def check_seeded_credentials_work_and_roles_hold(seeded, client):
    for role, expected in (("student", "student"), ("club_admin", "club_admin"), ("platform_admin", "platform_admin")):
        email, pw = seeded["credentials"][role]
        r = await client.post("/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, (role, r.text)
        assert r.json()["user"]["role"] == expected


async def check_seeded_analytics_return_sensible_numbers(seeded, client):
    email, pw = seeded["credentials"]["platform_admin"]
    tok = (await client.post("/auth/login", json={"email": email, "password": pw})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    o = (await client.get("/analytics/overview", headers=h)).json()
    assert o["totals"]["events"] == 55 and sum(c["count"] for c in o["events_by_status"]) == 55
    published = next(c["count"] for c in o["events_by_status"] if c["key"] == "published")
    assert sum(c["count"] for c in o["events_by_category"]) == published == 45
    assert o["top_clubs_by_saves"][0]["saves"] >= o["top_clubs_by_saves"][-1]["saves"]
    e = (await client.get("/analytics/engagement?days=30", headers=h)).json()
    assert e["totals"]["views"] > 2000 and e["totals"]["saves"] == 400
    assert 0 < e["totals"]["view_to_save"] < 1
    b = (await client.get("/analytics/busiest-days", headers=h)).json()
    assert b["total_events"] == 45 and sum(w["count"] for w in b["by_weekday"]) == 45
    club_admin_email, _ = seeded["credentials"]["club_admin"]
    t2 = (await client.post("/auth/login", json={"email": club_admin_email, "password": "password123"})).json()
    cid = (await client.get("/clubs?q=acm")).json()["items"][0]["id"]
    r = await client.get(f"/analytics/clubs/{cid}", headers={"Authorization": f"Bearer {t2['access_token']}"})
    assert r.status_code == 200 and r.json()["name"] == "ACM"


async def test_seed_is_deterministic_and_refuses_to_overwrite(db):
    first = await run_seed(db, reset=True)
    titles1 = sorted(e["title"] for e in await db.events.find().to_list(None))
    statuses1 = sorted((e["title"], e["status"], e["fee"]["type"]) for e in await db.events.find().to_list(None))
    second = await run_seed(db, reset=True)
    statuses2 = sorted((e["title"], e["status"], e["fee"]["type"]) for e in await db.events.find().to_list(None))
    assert statuses1 == statuses2 and first["counts"] == second["counts"]
    assert titles1 == sorted(e["title"] for e in await db.events.find().to_list(None))
    with pytest.raises(SystemExit):  # without --reset it must not mix with existing data
        await run_seed(db, reset=False)


async def test_seed_end_to_end(db, client):
    """Seed once (it takes ~20s), then verify data, counters, the public API and analytics."""
    # reset=True drops and re-creates the (test) database, then restores indexes/validators/admin
    seeded = await run_seed(db, reset=True)
    await check_seed_counts_and_shapes(seeded, db)
    await check_seed_counters_are_consistent(seeded, db)
    await check_seeded_api_homepage_is_fully_populated(seeded, client)
    await check_seeded_credentials_work_and_roles_hold(seeded, client)
    await check_seeded_analytics_return_sensible_numbers(seeded, client)
