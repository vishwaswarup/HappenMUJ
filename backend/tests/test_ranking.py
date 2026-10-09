from datetime import UTC, datetime, timedelta

from bson import ObjectId

NOW = datetime(2026, 10, 9, 6, 30, tzinfo=UTC)


def S(days: float) -> datetime:
    return NOW + timedelta(days=days)


async def top(client, **kw):
    r = await client.get("/home/top-events", **kw)
    assert r.status_code == 200, r.text
    return r.json()


def names(body) -> list[str]:
    return [i["title"] for i in body["items"]]


async def test_top_events_excludes_ineligible(client, freeze, make_club, make_doc, interactions):
    freeze()
    club, _ = await make_club("ACM")
    ok = await make_doc(club, S(3), title="ok")
    reg_closed = await make_doc(
        club, S(3), title="deadline passed",
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": S(-1)},
    )  # fmt: skip
    no_reg_required = await make_doc(club, S(3), title="walk-in", registration={"required": False})
    already_started = await make_doc(club, S(-0.1), title="started")
    past = await make_doc(club, S(-5), title="past")
    others = [
        await make_doc(club, S(3), title=st, status=st) for st in ("draft", "pending_review", "rejected", "cancelled")
    ]
    for e in (ok, reg_closed, already_started, past, *others):
        await interactions(e, "save", NOW - timedelta(hours=1), 10)  # heavy engagement can't make them eligible
    assert sorted(names(await top(client))) == ["ok", "walk-in"]
    assert no_reg_required


async def test_top_events_not_padded_and_capped_at_10(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    assert (await top(client))["items"] == []
    for i in range(3):
        await make_doc(club, S(1 + i), title=f"e{i}")
    assert len((await top(client))["items"]) == 3  # no padding
    for i in range(3, 14):
        await make_doc(club, S(1 + i), title=f"e{i}")
    body = await top(client)
    assert len(body["items"]) == 10
    assert [i["rank"] for i in body["items"]] == list(range(1, 11))


async def test_old_engagement_does_not_dominate(client, freeze, make_club, make_doc, interactions):
    freeze()
    club, _ = await make_club("ACM")
    old_hit = await make_doc(
        club, S(4), title="old-hit", stats={"views": 5000, "saves": 800, "registration_clicks": 300}
    )
    fresh = await make_doc(club, S(4), title="fresh")
    # old-hit: lots of engagement, but all 30 days ago (outside the 7-day window)
    for kind in ("view", "save", "registration_click"):
        await interactions(old_hit, kind, NOW - timedelta(days=30), 200)
    for kind in ("view", "save", "registration_click"):
        await interactions(fresh, kind, NOW - timedelta(days=1), 3)
    body = await top(client)
    assert names(body) == ["fresh", "old-hit"]
    assert body["items"][1]["components"]["saves"] == 0


async def test_score_formula_and_breakdown(client, freeze, make_club, make_doc, interactions):
    freeze()
    club, _ = await make_club("ACM")
    a = await make_doc(club, S(7), title="A")  # no deadline: urgency 0.5
    b = await make_doc(
        club, S(7), title="B",
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": S(1)},
    )  # fmt: skip
    await interactions(a, "save", NOW - timedelta(days=1), 10)
    await interactions(b, "save", NOW - timedelta(days=1), 5)
    await interactions(a, "view", NOW - timedelta(days=1), 2)
    await interactions(b, "view", NOW - timedelta(days=1), 4)
    await interactions(b, "registration_click", NOW - timedelta(days=2), 3)
    body = await top(client)
    by = {i["title"]: i for i in body["items"]}
    ca, cb = by["A"]["components"], by["B"]["components"]
    assert ca["saves"] == 1.0 and cb["saves"] == 0.5
    assert ca["views"] == 0.5 and cb["views"] == 1.0
    assert ca["registration_clicks"] == 0.0 and cb["registration_clicks"] == 1.0
    assert abs(ca["proximity"] - 0.3679) < 1e-3  # exp(-7/7)
    assert ca["urgency"] == 0.5 and cb["urgency"] == 1.0  # B's deadline is within 72h
    expected_a = 0.30 * 1.0 + 0.20 * 0.5 + 0.20 * 0 + 0.20 * 0.3679 + 0.10 * 0.5
    assert abs(by["A"]["score"] - expected_a) < 1e-3
    for it in body["items"]:  # the flat score_breakdown (weighted terms) sums to the score
        assert abs(sum(it["score_breakdown"].values()) - it["score"]) < 1e-3
        assert set(it["score_breakdown"]) == {"saves", "views", "registration_clicks", "proximity", "urgency"}
    # per-item engagement inside the ranking window, as the frontend's RankedEvent expects
    assert by["A"]["window"] == {"saves": 10, "views": 2, "registration_clicks": 0}
    assert by["B"]["window"] == {"saves": 5, "views": 4, "registration_clicks": 3}
    assert "not an official endorsement" in body["disclaimer"]
    assert body["window_days"] == 7


async def test_proximity_breaks_ties(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, S(14), title="far")
    await make_doc(club, S(1), title="near")
    assert names(await top(client)) == ["near", "far"]


async def test_weights_are_read_from_settings(client, freeze, make_club, make_doc, interactions, db):
    freeze()
    club, _ = await make_club("ACM")
    popular_far = await make_doc(club, S(20), title="popular-far")
    quiet_near = await make_doc(club, S(1), title="quiet-near")
    await interactions(popular_far, "save", NOW - timedelta(days=1), 50)
    await db.settings.update_one(
        {"_id": "ranking"},
        {"$set": {"weights": {"saves": 0.0, "views": 0.0, "registration_clicks": 0.0, "proximity": 1.0, "urgency": 0.0}, "window_days": 7}},
        upsert=True,
    )  # fmt: skip
    assert names(await top(client)) == ["quiet-near", "popular-far"]
    assert quiet_near
    cfg = (await client.get("/home/top-events/config")).json()
    assert cfg["weights"]["proximity"] == 1.0 and "saves" in cfg["formula"]
    await db.settings.delete_many({})  # missing doc falls back to defaults
    assert (await client.get("/home/top-events/config")).json()["weights"]["saves"] == 0.30


async def test_window_days_setting(client, freeze, make_club, make_doc, interactions, db):
    freeze()
    club, _ = await make_club("ACM")
    e = await make_doc(club, S(3), title="e")
    await interactions(e, "save", NOW - timedelta(days=10), 5)
    assert (await top(client))["items"][0]["components"]["saves"] == 0
    await db.settings.update_one({"_id": "ranking"}, {"$set": {"window_days": 14}}, upsert=True)
    assert (await top(client))["items"][0]["components"]["saves"] == 1.0


# ---------------------------------------------------------------- suggested
async def sug(client, headers=None):
    r = await client.get("/home/suggested", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_suggested_scoring(client, freeze, make_club, make_doc, make_user):
    freeze()
    acm, _ = await make_club("ACM")
    ieee, _ = await make_club("IEEE")
    u = await make_user()
    await client.patch(
        "/users/me", headers=u.headers,
        json={"interests": ["AI", "Robotics"], "preferred_categories": ["hackathon"]},
    )  # fmt: skip
    await client.post(f"/users/me/follow/{ieee['id']}", headers=u.headers)
    # same start so the date term is equal; compare the other terms
    both = await make_doc(acm, S(5), title="ai+cat", tags=["ai", "robotics"], category="hackathon")
    club_only = await make_doc(ieee, S(5), title="club", tags=[], category="sports")
    one_tag = await make_doc(acm, S(5), title="one-tag", tags=["ai", "music"], category="sports")
    nothing = await make_doc(acm, S(5), title="nothing", tags=["music"], category="sports")
    body = await sug(client, u.headers)
    assert body["personalised"] is True
    assert names(body) == ["ai+cat", "club", "one-tag", "nothing"]
    by = {i["title"]: i["components"] for i in body["items"]}
    assert by["ai+cat"]["interest"] == 1.0 and by["ai+cat"]["category"] == 1 and by["ai+cat"]["club"] == 0
    assert by["one-tag"]["interest"] == 0.5
    assert by["club"]["club"] == 1
    assert both and club_only and one_tag and nothing


async def test_suggested_interest_match_is_case_insensitive(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    u = await make_user()
    await client.patch("/users/me", headers=u.headers, json={"interests": ["MaChInE LeArNiNg"]})
    await make_doc(club, S(3), title="ml", tags=["Machine Learning"])  # stored lowercase via db helper? set explicitly:
    from app import db as dbm

    await dbm.get_db().events.update_one({"title": "ml"}, {"$set": {"tags": ["machine learning"]}})
    body = await sug(client, u.headers)
    assert body["items"][0]["components"]["interest"] == 1.0


async def test_suggested_excludes_saved_and_ineligible(client, freeze, make_club, make_doc, make_user, db):
    freeze()
    club, _ = await make_club("ACM")
    u = await make_user()
    await client.patch("/users/me", headers=u.headers, json={"interests": ["ai"]})
    saved = await make_doc(club, S(3), title="saved", tags=["ai"])
    await make_doc(club, S(4), title="keep", tags=["ai"])
    await make_doc(club, S(-2), title="past", tags=["ai"])
    await make_doc(club, S(3), title="cancelled", tags=["ai"], status="cancelled")
    await make_doc(
        club, S(3), title="closed", tags=["ai"],
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": S(-1)},
    )  # fmt: skip
    await db.saved_events.insert_one(
        {
            "user_id": ObjectId(u.id),
            "event_id": saved["_id"],
            "status": "saved",
            "event_start": saved["schedule"]["start"],
        }
    )
    body = await sug(client, u.headers)
    assert names(body) == ["keep"]
    assert body["items"][0]["is_saved"] is False


async def test_suggested_deadline_and_date_terms(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    u = await make_user()
    await client.patch("/users/me", headers=u.headers, json={"preferred_categories": ["technical"]})
    urgent = await make_doc(
        club, S(10), title="urgent",
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": S(2)},
    )  # fmt: skip
    relaxed = await make_doc(
        club, S(10), title="relaxed",
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": S(8)},
    )  # fmt: skip
    body = await sug(client, u.headers)
    comps = {i["title"]: i["components"] for i in body["items"]}
    assert comps["urgent"]["deadline"] == 1 and comps["relaxed"]["deadline"] == 0
    assert abs(comps["urgent"]["date"] - 0.3679) < 1e-3  # exp(-10/10)
    assert names(body)[0] == "urgent" and urgent and relaxed


async def test_suggested_falls_back_to_popularity(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, S(3), title="meh", stats={"views": 1, "saves": 0, "registration_clicks": 0})
    await make_doc(club, S(5), title="hot", stats={"views": 9, "saves": 30, "registration_clicks": 4})
    await make_doc(club, S(-1), title="past", stats={"views": 999, "saves": 999, "registration_clicks": 999})
    anon = await sug(client)
    assert anon["personalised"] is False and names(anon) == ["hot", "meh"]
    u = await make_user()  # logged in but no interests/categories/follows
    body = await sug(client, u.headers)
    assert body["personalised"] is False and names(body) == ["hot", "meh"]
    assert body["items"][0]["is_saved"] is False


# ---------------------------------------------------------------- featured
async def test_featured_prefers_most_recent_feature(client, freeze, make_club, make_doc, admin):
    freeze()
    club, _ = await make_club("ACM")
    a = await make_doc(club, S(3), title="a")
    b = await make_doc(club, S(4), title="b")
    for e, minutes in ((a, 10), (b, 5)):
        await make_doc(club, S(9), title="pad")
        await client.post(f"/admin/events/{e['_id']}/feature", headers=admin.headers)
        # force featured_at ordering deterministically
        from app import db as dbm

        await dbm.get_db().events.update_one(
            {"_id": e["_id"]}, {"$set": {"featured.featured_at": NOW - timedelta(minutes=minutes)}}
        )
    body = (await client.get("/home/featured")).json()
    assert body["source"] == "featured" and body["title"] == "b"  # b featured more recently
    assert body["featured"] is True and body["status"] == "published"


async def test_featured_ignores_past_and_nonpublic_then_falls_back(client, freeze, make_club, make_doc, db):
    freeze()
    club, _ = await make_club("ACM")
    feat = {"is_featured": True, "featured_at": NOW}
    await make_doc(club, S(-3), title="past featured", featured=feat)
    await make_doc(club, S(3), title="cancelled featured", featured=feat, status="cancelled")
    poster = ObjectId()
    await make_doc(club, S(9), title="later with poster", poster_file_id=poster)
    await make_doc(club, S(6), title="no poster")
    await make_doc(club, S(2), title="closed", poster_file_id=poster, registration={"required": False})
    await make_doc(club, S(7), title="soonest with poster + open reg", poster_file_id=poster)
    body = (await client.get("/home/featured")).json()
    assert body["source"] == "fallback"
    assert body["title"] == "soonest with poster + open reg"
    assert body["poster_url"] == f"/api/v1/files/{poster}"


async def test_featured_none_when_nothing(client, freeze):
    freeze()
    r = await client.get("/home/featured")
    assert r.status_code == 200 and r.json() is None  # a JSON null, which the frontend maps to "no featured event"
