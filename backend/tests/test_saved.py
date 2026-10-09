import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

NOW = datetime(2026, 10, 9, 6, 30, tzinfo=UTC)


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


async def save(client, actor, event_id):
    return await client.post("/saved-events", headers=actor.headers, json={"event_id": str(event_id)})


async def counts(db, event):
    ev = await db.events.find_one({"_id": event["_id"]})
    return {
        "saves": ev["stats"]["saves"],
        "saved_docs": await db.saved_events.count_documents({"event_id": event["_id"]}),
        "save_interactions": await db.event_interactions.count_documents({"event_id": event["_id"], "type": "save"}),
    }


@pytest.fixture
async def world(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    ev = await make_doc(club, NOW + timedelta(days=3), title="Hack Night")
    user = await make_user()
    return club, ev, user


async def test_save_writes_three_collections(client, world, db):
    _, ev, user = world
    r = await save(client, user, ev["_id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "saved" and body["event_id"] == str(ev["_id"])
    assert body["event_start"].startswith("2026-10-12T06:30")
    assert await counts(db, ev) == {"saves": 1, "saved_docs": 1, "save_interactions": 1}
    doc = await db.saved_events.find_one({})
    assert doc["event_start"] == ev["schedule"]["start"] and doc["schema_v"] == 1


async def test_save_is_idempotent(client, world, db):
    _, ev, user = world
    first = await save(client, user, ev["_id"])
    second = await save(client, user, ev["_id"])
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert await counts(db, ev) == {"saves": 1, "saved_docs": 1, "save_interactions": 1}


async def test_concurrent_saves_create_exactly_one(client, world, db):
    _, ev, user = world
    rs = await asyncio.gather(*[save(client, user, ev["_id"]) for _ in range(6)])
    assert all(r.status_code in (200, 201) for r in rs)
    assert sorted(r.status_code for r in rs).count(201) == 1
    assert len({r.json()["id"] for r in rs}) == 1
    assert await counts(db, ev) == {"saves": 1, "saved_docs": 1, "save_interactions": 1}


async def test_different_users_each_count(client, world, db, make_user):
    _, ev, u1 = world
    u2 = await make_user()
    await save(client, u1, ev["_id"])
    await save(client, u2, ev["_id"])
    assert (await counts(db, ev))["saves"] == 2


async def test_unsave_reverses_everything_and_is_idempotent(client, world, db):
    _, ev, user = world
    await save(client, user, ev["_id"])
    r = await client.delete(f"/saved-events/{ev['_id']}", headers=user.headers)
    assert r.status_code == 204
    assert await counts(db, ev) == {"saves": 0, "saved_docs": 0, "save_interactions": 0}
    r = await client.delete(f"/saved-events/{ev['_id']}", headers=user.headers)  # again: no-op, never negative
    assert r.status_code == 204
    assert (await counts(db, ev))["saves"] == 0


async def test_save_unsave_cycles_cannot_inflate_ranking(client, world, db):
    _, ev, user = world
    for _ in range(5):
        await save(client, user, ev["_id"])
        await client.delete(f"/saved-events/{ev['_id']}", headers=user.headers)
    assert await db.event_interactions.count_documents({"type": "save"}) == 0


async def test_cannot_save_nonpublic_or_unknown(client, world, make_doc):
    club, ev, user = world
    for status in ("draft", "pending_review", "rejected", "cancelled"):
        d = await make_doc(club, NOW + timedelta(days=2), status=status)
        assert (await save(client, user, d["_id"])).status_code == 404
    assert (await save(client, user, ObjectId())).status_code == 404
    assert (await client.post("/saved-events", headers=user.headers, json={"event_id": "bad"})).status_code == 422
    assert (await client.post("/saved-events", json={"event_id": str(ev["_id"])})).status_code == 401


async def test_saved_endpoints_require_auth(client):
    assert (await client.get("/saved-events")).status_code == 401
    assert (await client.delete(f"/saved-events/{ObjectId()}")).status_code == 401
    assert (await client.get("/calendar?year=2026&month=10")).status_code == 401


# ---------------------------------------------------------------- transaction rollback
async def test_save_rolls_back_on_midway_failure(client, world, db, monkeypatch):
    _, ev, user = world
    from app.services import interactions

    async def boom(*a, **k):
        raise RuntimeError("simulated crash after two of three writes")

    monkeypatch.setattr(interactions, "insert_interaction", boom)
    with pytest.raises(RuntimeError):
        await save(client, user, ev["_id"])
    # the saved_events insert and the stats.saves $inc both happened inside the txn, then rolled back
    assert await counts(db, ev) == {"saves": 0, "saved_docs": 0, "save_interactions": 0}
    monkeypatch.undo()
    assert (await save(client, user, ev["_id"])).status_code == 201  # system is healthy afterwards
    assert await counts(db, ev) == {"saves": 1, "saved_docs": 1, "save_interactions": 1}


async def test_unsave_rolls_back_on_midway_failure(client, world, db, monkeypatch):
    _, ev, user = world
    await save(client, user, ev["_id"])
    from app.services import saved

    async def boom(*a, **k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(saved, "remove_save_interaction", boom)
    with pytest.raises(RuntimeError):
        await client.delete(f"/saved-events/{ev['_id']}", headers=user.headers)
    # delete + decrement were rolled back: still saved, counter intact
    assert await counts(db, ev) == {"saves": 1, "saved_docs": 1, "save_interactions": 1}


async def test_without_transaction_the_failure_would_leave_partial_state(world, db):
    """Control experiment: the same three writes outside a transaction DO leave partial state."""
    _, ev, user = world
    await db.saved_events.insert_one({"user_id": ObjectId(user.id), "event_id": ev["_id"], "status": "saved",
                                      "event_start": ev["schedule"]["start"]})  # fmt: skip
    await db.events.update_one({"_id": ev["_id"]}, {"$inc": {"stats.saves": 1}})
    # ...crash before the interaction insert: counters and log now disagree
    assert (await counts(db, ev)) == {"saves": 1, "saved_docs": 1, "save_interactions": 0}


# ---------------------------------------------------------------- list
async def test_list_saved_upcoming_and_cancelled_flag(client, freeze, make_club, make_doc, make_user, admin, db):
    freeze()
    club, _ = await make_club("ACM")
    user = await make_user()
    soon = await make_doc(club, NOW + timedelta(days=1), title="soon")
    later = await make_doc(club, NOW + timedelta(days=9), title="later")
    cancelled = await make_doc(club, NOW + timedelta(days=4), title="will be cancelled")
    past = await make_doc(club, NOW + timedelta(days=2), title="soon-then-past")
    for e in (later, soon, cancelled, past):
        assert (await save(client, user, e["_id"])).status_code == 201
    await db.events.update_one({"_id": cancelled["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": NOW}})
    await db.saved_events.update_one({"event_id": past["_id"]}, {"$set": {"event_start": NOW - timedelta(days=1)}})

    r = await client.get("/saved-events", headers=user.headers)
    body = r.json()
    assert body["total"] == 4
    assert [i["event"]["title"] for i in body["items"]] == ["later", "will be cancelled", "soon", "soon-then-past"]
    by = {i["event"]["title"]: i for i in body["items"]}
    assert by["will be cancelled"]["cancelled"] is True  # still visible to its owner, flagged
    assert by["soon"]["cancelled"] is False and by["soon"]["event"]["is_saved"] is True
    assert by["soon"]["event"]["registration_open"] is True and by["soon"]["status"] == "saved"

    up = (await client.get("/saved-events?upcoming=true", headers=user.headers)).json()
    assert [i["event"]["title"] for i in up["items"]] == ["soon", "will be cancelled", "later"]
    assert up["total"] == 3
    page = (await client.get("/saved-events?upcoming=true&page_size=2&page=2", headers=user.headers)).json()
    assert [i["event"]["title"] for i in page["items"]] == ["later"] and page["total"] == 3


async def test_saved_lists_are_per_user(client, world, make_user):
    _, ev, u1 = world
    u2 = await make_user()
    await save(client, u1, ev["_id"])
    assert (await client.get("/saved-events", headers=u2.headers)).json()["total"] == 0
    assert (await client.get("/saved-events", headers=u1.headers)).json()["total"] == 1


# ---------------------------------------------------------------- calendar
async def test_calendar_groups_by_ist_date_and_month(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    user = await make_user()
    spec = {
        "sep-30 23:59 IST": utc(2026, 9, 30, 18, 29),  # September
        "oct-1 00:00 IST": utc(2026, 9, 30, 18, 30),  # first instant of October
        "oct-12 23:30 IST": utc(2026, 10, 12, 18, 0),  # UTC date is the 12th too
        "oct-13 00:30 IST": utc(2026, 10, 12, 19, 0),  # UTC date still the 12th, IST date the 13th
        "oct-31 23:50 IST": utc(2026, 10, 31, 18, 20),
        "nov-1 00:00 IST": utc(2026, 10, 31, 18, 30),  # November
    }
    for title, start in spec.items():
        e = await make_doc(club, start, title=title)
        await save(client, user, e["_id"])
    r = await client.get("/calendar?year=2026&month=10", headers=user.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == "Asia/Kolkata" and (body["year"], body["month"]) == (2026, 10)
    days = {d["date"]: [i["event"]["title"] for i in d["items"]] for d in body["days"]}
    assert days == {
        "2026-10-01": ["oct-1 00:00 IST"],
        "2026-10-12": ["oct-12 23:30 IST"],
        "2026-10-13": ["oct-13 00:30 IST"],
        "2026-10-31": ["oct-31 23:50 IST"],
    }
    assert [d["date"] for d in body["days"]] == sorted(days)  # chronological
    nov = (await client.get("/calendar?year=2026&month=11", headers=user.headers)).json()
    assert [d["date"] for d in nov["days"]] == ["2026-11-01"]
    sep = (await client.get("/calendar?year=2026&month=9", headers=user.headers)).json()
    assert [d["date"] for d in sep["days"]] == ["2026-09-30"]


async def test_calendar_multiple_per_day_ordered_and_flags(client, freeze, make_club, make_doc, make_user, db):
    freeze()
    club, _ = await make_club("ACM")
    user = await make_user()
    late = await make_doc(club, utc(2026, 10, 20, 12, 0), title="late")
    early = await make_doc(club, utc(2026, 10, 20, 4, 0), title="early")
    for e in (late, early):
        await save(client, user, e["_id"])
    await db.events.update_one({"_id": late["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": NOW}})
    day = (await client.get("/calendar?year=2026&month=10", headers=user.headers)).json()["days"][0]
    assert [i["event"]["title"] for i in day["items"]] == ["early", "late"]
    assert [i["cancelled"] for i in day["items"]] == [False, True]


async def test_calendar_december_and_validation(client, make_user, freeze, make_club, make_doc):
    freeze()
    user = await make_user()
    club, _ = await make_club("ACM")
    e = await make_doc(club, utc(2026, 12, 31, 17, 0), title="nye")  # 22:30 IST on Dec 31
    await save(client, user, e["_id"])
    assert (await client.get("/calendar?year=2026&month=12", headers=user.headers)).json()["days"][0][
        "date"
    ] == "2026-12-31"
    assert (await client.get("/calendar?year=2027&month=1", headers=user.headers)).json()["days"] == []
    for q in ("year=2026&month=13", "year=2026&month=0", "year=1999&month=1", "month=1"):
        assert (await client.get(f"/calendar?{q}", headers=user.headers)).status_code == 422


async def test_schedule_edit_moves_calendar_entry(client, make_club, make_event, admin, make_user, freeze):
    # real endpoints end to end: a rescheduled event moves in the saved user's calendar
    freeze()
    club, owner = await make_club("ACM")
    ev = await make_event(club["id"], owner, status="published", admin=admin)
    user = await make_user()
    assert (await save(client, user, ev["id"])).status_code == 201
    new_start = NOW + timedelta(days=40)
    r = await client.patch(
        f"/events/{ev['id']}", headers=owner.headers,
        json={"schedule": {"start": new_start.isoformat(), "end": (new_start + timedelta(hours=1)).isoformat()}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    month = new_start.astimezone(UTC)
    cal = (await client.get(f"/calendar?year={month.year}&month={month.month}", headers=user.headers)).json()
    assert len(cal["days"]) == 1 and cal["days"][0]["items"][0]["event"]["id"] == ev["id"]


# ---------------------------------------------------------------- views
async def test_view_dedupe_30_minutes_per_user(client, freeze, world, db, make_user):
    _, ev, user = world
    other = await make_user()
    r1 = await client.post(f"/events/{ev['_id']}/view", headers=user.headers)
    assert r1.json() == {"recorded": True}
    freeze(NOW + timedelta(minutes=29))
    assert (await client.post(f"/events/{ev['_id']}/view", headers=user.headers)).json() == {"recorded": False}
    # another user is independent
    assert (await client.post(f"/events/{ev['_id']}/view", headers=other.headers)).json() == {"recorded": True}
    freeze(NOW + timedelta(minutes=31))
    assert (await client.post(f"/events/{ev['_id']}/view", headers=user.headers)).json() == {"recorded": True}
    stored = await db.events.find_one({"_id": ev["_id"]})
    assert stored["stats"]["views"] == 3
    assert await db.event_interactions.count_documents({"type": "view"}) == 3


async def test_anonymous_view_recorded_with_null_user(client, world, db):
    _, ev, _ = world
    assert (await client.post(f"/events/{ev['_id']}/view")).json() == {"recorded": True}
    i = await db.event_interactions.find_one({"type": "view"})
    assert i["user_id"] is None and i["event_id"] == ev["_id"]


async def test_view_nonpublic_is_404(client, world, make_doc):
    club, ev, _ = world
    d = await make_doc(club, NOW + timedelta(days=2), status="draft")
    assert (await client.post(f"/events/{d['_id']}/view")).status_code == 404


# ---------------------------------------------------------------- registration click
async def test_registration_click_returns_url_and_marks_saved(client, world, db, make_user):
    _, ev, user = world
    await save(client, user, ev["_id"])
    bystander = await make_user()
    r = await client.post(f"/events/{ev['_id']}/registration-click", headers=user.headers)
    assert r.status_code == 200 and r.json() == {"url": "https://x.example.com", "platform": "other"}
    assert (await db.saved_events.find_one({"event_id": ev["_id"]}))["status"] == "registration_initiated"
    assert (await db.events.find_one({"_id": ev["_id"]}))["stats"]["registration_clicks"] == 1
    listing = (await client.get("/saved-events", headers=user.headers)).json()
    assert listing["items"][0]["status"] == "registration_initiated"
    # clicking without having saved: recorded, nothing to flip
    await client.post(f"/events/{ev['_id']}/registration-click", headers=bystander.headers)
    assert await db.event_interactions.count_documents({"type": "registration_click"}) == 2
    assert await db.saved_events.count_documents({}) == 1
    # anonymous click allowed
    assert (await client.post(f"/events/{ev['_id']}/registration-click")).status_code == 200


async def test_registration_click_errors(client, freeze, world, make_doc):
    club, ev, user = world
    walk_in = await make_doc(club, NOW + timedelta(days=2), registration={"required": False})
    r = await client.post(f"/events/{walk_in['_id']}/registration-click", headers=user.headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_registration"
    closed = await make_doc(
        club, NOW + timedelta(days=2),
        registration={"required": True, "platform": "other", "url": "https://x.example.com", "deadline": NOW - timedelta(hours=1)},
    )  # fmt: skip
    r = await client.post(f"/events/{closed['_id']}/registration-click", headers=user.headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "registration_closed"
    draft = await make_doc(club, NOW + timedelta(days=2), status="draft")
    assert (await client.post(f"/events/{draft['_id']}/registration-click")).status_code == 404


async def test_saving_feeds_top_events_ranking(client, freeze, make_club, make_doc, make_user):
    freeze()
    club, _ = await make_club("ACM")
    a = await make_doc(club, NOW + timedelta(days=5), title="A")
    b = await make_doc(club, NOW + timedelta(days=5), title="B")
    users = [await make_user() for _ in range(3)]
    for u in users:
        await save(client, u, b["_id"])
    await save(client, users[0], a["_id"])
    items = (await client.get("/home/top-events")).json()["items"]
    assert [i["title"] for i in items] == ["B", "A"]
    assert items[0]["score_breakdown"]["components"]["saves"] == 1.0
    # unsaving takes the engagement back out
    for u in users:
        await client.delete(f"/saved-events/{b['_id']}", headers=u.headers)
    items = (await client.get("/home/top-events")).json()["items"]
    assert [i["title"] for i in items] == ["A", "B"]
