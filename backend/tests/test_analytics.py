from datetime import UTC, datetime, timedelta

from bson import ObjectId

NOW = datetime(2026, 10, 9, 6, 30, tzinfo=UTC)


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


async def test_analytics_admin_only(client, make_user, make_club):
    club, owner = await make_club("ACM")
    student = await make_user()
    for path in ("/analytics/overview", "/analytics/engagement", "/analytics/busiest-days"):
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=student.headers)).status_code == 403
        assert (await client.get(path, headers=owner.headers)).status_code == 403  # club admins: own club only
    assert (await client.get(f"/analytics/clubs/{club['id']}")).status_code == 401


async def test_overview_numbers(client, freeze, make_club, make_doc, admin, make_user):
    freeze()
    acm, _ = await make_club("ACM")
    ieee, _ = await make_club("IEEE")
    await make_club("Pending", verified=False)
    await make_doc(
        acm, NOW + timedelta(days=1), category="technical", stats={"views": 10, "saves": 5, "registration_clicks": 2}
    )
    await make_doc(
        acm, NOW + timedelta(days=2), category="technical", stats={"views": 1, "saves": 1, "registration_clicks": 0}
    )
    await make_doc(
        ieee, NOW + timedelta(days=3), category="sports", stats={"views": 4, "saves": 9, "registration_clicks": 1}
    )
    await make_doc(
        ieee,
        NOW + timedelta(days=3),
        category="sports",
        status="draft",
        stats={"views": 0, "saves": 50, "registration_clicks": 0},
    )
    await make_doc(ieee, NOW + timedelta(days=3), category="cultural", status="cancelled")
    body = (await client.get("/analytics/overview", headers=admin.headers)).json()
    assert body["totals"]["events"] == 5 and body["totals"]["clubs"] == 3 and body["totals"]["verified_clubs"] == 2
    assert body["totals"]["users"] >= 4
    assert {c["key"]: c["count"] for c in body["events_by_category"]} == {"technical": 2, "sports": 1}  # published only
    assert {c["key"]: c["count"] for c in body["events_by_status"]} == {"published": 3, "draft": 1, "cancelled": 1}
    top = body["top_clubs_by_saves"]
    assert [c["slug"] for c in top] == ["ieee", "acm"]  # drafts' saves don't count
    assert (top[0]["saves"], top[0]["events"], top[0]["views"]) == (9, 1, 4)
    assert (top[1]["saves"], top[1]["events"], top[1]["registration_clicks"]) == (6, 2, 2)


async def test_overview_empty_database(client, admin):
    body = (await client.get("/analytics/overview", headers=admin.headers)).json()
    assert body["events_by_category"] == [] and body["top_clubs_by_saves"] == []


async def test_engagement_funnel_and_rates(client, freeze, make_club, make_doc, interactions, admin):
    freeze()
    club, _ = await make_club("ACM")
    a = await make_doc(club, NOW + timedelta(days=3), title="A")
    b = await make_doc(club, NOW + timedelta(days=3), title="B")
    c = await make_doc(club, NOW + timedelta(days=3), title="C")
    recent = NOW - timedelta(days=2)
    for ev, v, s, k in ((a, 10, 4, 2), (b, 3, 0, 0), (c, 0, 1, 1)):
        await interactions(ev, "view", recent, v) if v else None
        await interactions(ev, "save", recent, s) if s else None
        await interactions(ev, "registration_click", recent, k) if k else None
    await interactions(b, "view", NOW - timedelta(days=60), 100)  # outside the default 30-day window
    body = (await client.get("/analytics/engagement", headers=admin.headers)).json()
    assert body["days"] == 30
    rows = {r["title"]: r for r in body["items"]}
    assert [r["title"] for r in body["items"]] == ["A", "B", "C"]  # by views desc
    a_row = rows["A"]
    assert (a_row["views"], a_row["saves"], a_row["registration_clicks"]) == (10, 4, 2)
    assert (a_row["view_to_save"], a_row["save_to_click"], a_row["view_to_click"]) == (0.4, 0.5, 0.2)
    assert (
        rows["B"]["views"] == 3 and rows["B"]["view_to_save"] == 0 and rows["B"]["save_to_click"] == 0
    )  # no div-by-zero
    assert rows["C"]["view_to_save"] == 0 and rows["C"]["save_to_click"] == 1.0
    t = body["totals"]
    assert (t["views"], t["saves"], t["registration_clicks"]) == (13, 5, 3)
    assert (t["view_to_save"], t["save_to_click"], t["view_to_click"]) == (0.3846, 0.6, 0.2308)
    wide = (await client.get("/analytics/engagement?days=90", headers=admin.headers)).json()
    assert wide["totals"]["views"] == 113
    one = (await client.get("/analytics/engagement?limit=1", headers=admin.headers)).json()
    assert len(one["items"]) == 1 and one["totals"]["views"] == 13  # totals cover all rows, not just the page
    assert (await client.get("/analytics/engagement?days=91", headers=admin.headers)).status_code == 422


async def test_engagement_club_filter_and_empty(client, freeze, make_club, make_doc, interactions, admin):
    freeze()
    acm, _ = await make_club("ACM")
    ieee, _ = await make_club("IEEE")
    ea = await make_doc(acm, NOW + timedelta(days=3), title="acm-ev")
    ei = await make_doc(ieee, NOW + timedelta(days=3), title="ieee-ev")
    await interactions(ea, "view", NOW - timedelta(days=1), 2)
    await interactions(ei, "view", NOW - timedelta(days=1), 5)
    body = (await client.get(f"/analytics/engagement?club_id={ieee['id']}", headers=admin.headers)).json()
    assert [r["title"] for r in body["items"]] == ["ieee-ev"] and body["totals"]["views"] == 5
    empty = (await client.get(f"/analytics/engagement?club_id={ObjectId()}", headers=admin.headers)).json()
    assert empty["items"] == [] and empty["totals"]["views"] == 0


async def test_busiest_days_uses_ist_weekday_and_hour(client, freeze, make_club, make_doc, admin):
    freeze()
    club, _ = await make_club("ACM")
    # 2026-10-12 is a Monday
    await make_doc(club, utc(2026, 10, 12, 6, 0))  # Mon 11:30 IST
    await make_doc(club, utc(2026, 10, 12, 6, 15))  # Mon 11:45 IST
    await make_doc(club, utc(2026, 10, 12, 19, 0))  # 00:30 IST on TUESDAY (UTC date is still Monday)
    await make_doc(club, utc(2026, 10, 18, 18, 29))  # Sun 23:59 IST
    await make_doc(club, utc(2026, 10, 12, 6, 0), status="draft")  # ignored
    body = (await client.get("/analytics/busiest-days", headers=admin.headers)).json()
    assert body["timezone"] == "Asia/Kolkata" and body["total_events"] == 4
    wd = {w["weekday"]: (w["name"], w["count"]) for w in body["by_weekday"]}
    assert (
        len(wd) == 7 and wd[1] == ("Monday", 2) and wd[2] == ("Tuesday", 1) and wd[7] == ("Sunday", 1) and wd[3][1] == 0
    )
    hours = {h["hour"]: h["count"] for h in body["by_hour"]}
    assert hours == {11: 2, 0: 1, 23: 1}
    cells = {(c["weekday"], c["hour"]): c["count"] for c in body["heatmap"]}
    assert cells == {(1, 11): 2, (2, 0): 1, (7, 23): 1}


async def test_club_analytics_and_authorization(client, freeze, make_club, make_doc, make_user, admin, db):
    freeze()
    acm, acm_admin = await make_club("ACM")
    ieee, ieee_admin = await make_club("IEEE")
    await make_doc(acm, NOW + timedelta(days=2), title="up", stats={"views": 20, "saves": 8, "registration_clicks": 4})
    await make_doc(
        acm, NOW - timedelta(days=5), title="gone", stats={"views": 10, "saves": 2, "registration_clicks": 1}
    )
    await make_doc(acm, NOW + timedelta(days=9), title="draft", status="draft")
    await make_doc(
        ieee, NOW + timedelta(days=2), title="other club", stats={"views": 999, "saves": 999, "registration_clicks": 0}
    )
    f1, f2 = await make_user(), await make_user()
    for f in (f1, f2):
        await client.post(f"/users/me/follow/{acm['id']}", headers=f.headers)
    await client.post(
        "/posts", headers=f1.headers, json={"title": "t", "body": "b", "scope": {"type": "club", "ref_id": acm["id"]}}
    )

    r = await client.get(f"/analytics/clubs/{acm['id']}", headers=acm_admin.headers)
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["name"], b["followers"], b["posts"]) == ("ACM", 2, 1)
    assert (b["views"], b["saves"], b["registration_clicks"]) == (30, 10, 5)
    assert (b["view_to_save"], b["save_to_click"]) == (0.3333, 0.5)
    assert (b["upcoming_published"], b["past_published"]) == (1, 1)
    assert {s["key"]: s["count"] for s in b["events_by_status"]} == {"published": 2, "draft": 1}
    assert [t["title"] for t in b["top_events"]][:2] == ["up", "gone"]
    # platform admin may read any club; another club's admin and students may not
    assert (await client.get(f"/analytics/clubs/{acm['id']}", headers=admin.headers)).status_code == 200
    assert (await client.get(f"/analytics/clubs/{acm['id']}", headers=ieee_admin.headers)).status_code == 403
    assert (await client.get(f"/analytics/clubs/{acm['id']}", headers=f1.headers)).status_code == 403
    assert (await client.get(f"/analytics/clubs/{ObjectId()}", headers=admin.headers)).status_code == 404
