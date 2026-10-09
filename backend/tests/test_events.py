from datetime import UTC, datetime, timedelta

import pytest


# ---------------------------------------------------------------- validation per event_type
async def test_create_draft_workshop(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"]))
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["status"] == "draft" and ev["club"]["slug"] == "club-a" and ev["club"]["name"] == "Club A"
    assert ev["tags"] == ["ai", "genai"]  # normalized to lowercase
    assert ev["fee"]["display"] == "Free" and ev["team"]["display"] == "Individual"
    assert ev["details"]["bring_own_laptop"] is True
    assert ev["registration_open"] is True and ev["completed"] is False and ev["poster_url"] is None


async def test_workshop_with_competition_fields_rejected(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    body = event_payload(club["id"], details={"prizes": [{"rank": 1, "reward": "Rs 5000"}]})
    r = await client.post("/events", headers=owner.headers, json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


DETAILS = {
    "workshop": {"speaker": {"name": "A"}, "topics": ["x"], "duration_minutes": 90, "prerequisites": ["python"]},
    "competition": {"prizes": [{"rank": 1, "reward": "Rs 1000"}], "rounds": [{"name": "R1"}], "judging_criteria": ["x"]},
    "hackathon": {"themes": ["AI"], "tracks": ["web"], "duration_hours": 24, "max_teams": 30},
    "sports_match": {"sport": "football", "match_type": "league", "teams": [{"name": "CSE"}], "format": "5v5"},
    "cultural_show": {"performances": [{"title": "Dance", "performer": "X"}], "auditions_required": True,
                      "audition_date": "2026-11-01T10:00:00+05:30"},
    "seminar": {"speaker": {"name": "Dr X", "affiliation": "IIT"}, "topic": "Quantum", "q_and_a_enabled": True},
    "social": {"extra": {"dress_code": "casual"}},
    "other": {"extra": {"anything": [1, 2]}},
}  # fmt: skip


@pytest.mark.parametrize("etype", list(DETAILS))
async def test_each_event_type_shape_round_trips(client, make_club, event_payload, etype):
    club, owner = await make_club("Club A")
    r = await client.post(
        "/events", headers=owner.headers, json=event_payload(club["id"], event_type=etype, details=DETAILS[etype])
    )
    assert r.status_code == 201, r.text
    stored = r.json()["details"]
    for k in DETAILS[etype]:
        assert k in stored
    assert "event_type" not in stored  # discriminator is derived, not stored


async def test_events_of_many_shapes_coexist_in_one_collection(client, make_club, event_payload, db):
    club, owner = await make_club("Club A")
    for et, det in DETAILS.items():
        r = await client.post(
            "/events", headers=owner.headers, json=event_payload(club["id"], event_type=et, details=det)
        )
        assert r.status_code == 201
    shapes = {frozenset((await db.events.find_one({"event_type": et}))["details"]) for et in DETAILS}
    assert len(shapes) >= 6


async def test_details_is_free_form_but_guards_cross_type_fields(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    # free-form: a key the backend has never heard of is kept (the frontend's eventDetails.ts is the contract)
    r = await client.post(
        "/events", headers=owner.headers, json=event_payload(club["id"], details={"topics": ["x"], "nope": 1})
    )
    assert r.status_code == 201 and r.json()["details"]["nope"] == 1 and r.json()["details"]["topics"] == ["x"]
    # ...but a field that belongs to ANOTHER event type is still rejected
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], details={"tracks": ["web"]}))
    assert r.status_code == 422 and "do not belong" in str(r.json())
    r = await client.post(
        "/events", headers=owner.headers, json=event_payload(club["id"], details={"event_type": "hackathon"})
    )
    assert r.status_code == 422


async def test_details_accepts_the_shapes_the_frontend_form_sends(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    forms = {
        # hackathon prizes are plain lines (not {rank, reward} objects)
        "hackathon": {"themes": ["AI"], "prizes": ["1st: ₹25,000", "2nd: ₹10,000"], "max_teams": 30},
        # a date input yields 'YYYY-MM-DD', and a speaker may be given without a name
        "cultural_show": {"auditions_required": True, "audition_date": "2026-11-05", "artists": ["A"]},
        "seminar": {"speaker": {"affiliation": "IIT"}, "topic": "Quantum", "q_and_a_enabled": True},
        "competition": {"prizes": [{"rank": "1st", "reward": "₹5,000"}], "rounds": [{"name": "Prelims", "description": ""}]},
        "social": {"extra": {"notes": "Bring snacks"}},
        "sports_match": {"sport": "Football", "teams": [{"name": "CSE"}, {"name": "ECE"}]},
    }  # fmt: skip
    for etype, details in forms.items():
        r = await client.post(
            "/events", headers=owner.headers, json=event_payload(club["id"], event_type=etype, details=details)
        )
        assert r.status_code == 201, (etype, r.text)
        stored = r.json()["details"]
        assert stored == details, (etype, stored)  # stored exactly as sent: no injected defaults


async def test_patch_may_resend_club_id_but_not_move_the_event(client, make_club, make_event):
    club, owner = await make_club("Club A")
    other, _ = await make_club("Club B")
    ev = await make_event(club["id"], owner)
    # the edit form re-sends the whole input including club_id
    ok = await client.patch(
        f"/events/{ev['id']}", headers=owner.headers, json={"club_id": club["id"], "title": "Edited"}
    )
    assert ok.status_code == 200 and ok.json()["title"] == "Edited"
    moved = await client.patch(f"/events/{ev['id']}", headers=owner.headers, json={"club_id": other["id"]})
    assert moved.status_code == 409 and moved.json()["error"]["code"] == "club_change_not_allowed"


# ---------------------------------------------------------------- fee / team / registration rules
@pytest.mark.parametrize(
    "fee,ok",
    [
        ({"type": "fixed"}, False),
        ({"type": "per_team"}, False),
        ({"type": "per_participant"}, False),
        ({"type": "free", "amount": 10}, False),
        ({"type": "fixed", "amount": -1}, False),
        ({"type": "fixed", "amount": 199}, True),
        ({"type": "per_team", "amount": 500}, True),
        ({"type": "free"}, True),
    ],
)
async def test_fee_rules(client, make_club, event_payload, fee, ok):
    club, owner = await make_club("Club A")
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], fee=fee))
    assert (r.status_code == 201) is ok, r.text


async def test_fee_not_specified_is_default_and_never_free(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    body = event_payload(club["id"])
    del body["fee"]
    r = await client.post("/events", headers=owner.headers, json=body)
    assert r.json()["fee"]["type"] == "not_specified"
    assert r.json()["fee"]["display"] == "Fee not specified"
    assert r.json()["fee"]["display"] != "Free"


async def test_fee_display_strings(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    cases = [
        ({"type": "fixed", "amount": 199}, "₹199"),
        ({"type": "per_participant", "amount": 199}, "₹199 per participant"),
        ({"type": "per_team", "amount": 99.5}, "₹99.5 per team"),
        ({"type": "fixed", "amount": 1234567}, "₹12,34,567"),  # en-IN digit grouping, like the frontend
    ]
    for fee, expected in cases:
        r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], fee=fee))
        assert r.json()["fee"]["display"] == expected


@pytest.mark.parametrize(
    "team,ok,display",
    [
        ({"type": "range", "min": 2, "max": 4}, True, "2–4 members"),
        ({"type": "range", "min": 2}, False, None),
        ({"type": "range", "min": 5, "max": 2}, False, None),
        ({"type": "fixed", "min": 3, "max": 3}, True, "Exactly 3 members"),
        ({"type": "fixed", "min": 3}, True, "Exactly 3 members"),
        ({"type": "fixed", "min": 2, "max": 3}, False, None),
        ({"type": "individual", "min": 2}, False, None),
        ({"type": "not_specified"}, True, "Team size not specified"),
    ],
)
async def test_team_rules(client, make_club, event_payload, team, ok, display):
    club, owner = await make_club("Club A")
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], team=team))
    assert (r.status_code == 201) is ok, r.text
    if ok:
        assert r.json()["team"]["display"] == display


@pytest.mark.parametrize(
    "reg",
    [
        {"required": True, "url": "javascript:alert(1)"},
        {"required": True, "url": "ftp://x.com/f"},
        {"required": True, "url": "not a url"},
        {"required": True},  # required but no url
    ],
)
async def test_registration_url_rules(client, make_club, event_payload, reg):
    club, owner = await make_club("Club A")
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], registration=reg))
    assert r.status_code == 422


async def test_time_and_text_rules(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    now = datetime.now(UTC)
    bad_bodies = [
        {"schedule": {"start": (now + timedelta(days=1)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}},
        {"schedule": {"start": "2026-12-01T10:00:00", "end": "2026-12-01T12:00:00"}},  # naive
        {"one_liner": "x" * 161},
        {"one_liner": ""},
        {"category": "nonsense"},
        {"event_type": "party"},
    ]
    for over in bad_bodies:
        r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"], **over))
        assert r.status_code == 422, over
    ok = await client.post(
        "/events", headers=owner.headers,
        json=event_payload(club["id"], schedule={"start": "2030-01-01T10:00:00+05:30", "end": "2030-01-01T12:00:00+05:30"}),
    )  # fmt: skip
    assert ok.status_code == 201
    # offsets are converted to UTC
    assert ok.json()["schedule"]["start"].startswith("2030-01-01T04:30:00")


async def test_event_stored_in_utc_with_validator_fields(client, make_club, event_payload, db):
    club, owner = await make_club("Club A")
    ev = (await client.post("/events", headers=owner.headers, json=event_payload(club["id"]))).json()
    from bson import ObjectId

    doc = await db.events.find_one({"_id": ObjectId(ev["id"])})
    assert doc["schedule"]["start"].utcoffset() == timedelta(0)
    assert doc["schema_v"] == 1 and doc["stats"] == {"views": 0, "saves": 0, "registration_clicks": 0}
    assert doc["featured"] == {"is_featured": False, "featured_at": None}


# ---------------------------------------------------------------- authorization
async def test_student_cannot_create_events(client, make_club, make_user, event_payload):
    club, _ = await make_club("Club A")
    student = await make_user()
    r = await client.post("/events", headers=student.headers, json=event_payload(club["id"]))
    assert r.status_code == 403
    assert (await client.post("/events", json=event_payload(club["id"]))).status_code == 401


async def test_cross_club_access_denied(client, make_club, make_event, event_payload, admin):
    club_a, admin_a = await make_club("Club A")
    club_b, admin_b = await make_club("Club B")
    # cannot create for another club
    r = await client.post("/events", headers=admin_a.headers, json=event_payload(club_b["id"]))
    assert r.status_code == 403
    ev = await make_event(club_a["id"], admin_a)
    eid = ev["id"]
    for method, path, body in [
        ("PATCH", f"/events/{eid}", {"title": "Hijacked"}),
        ("POST", f"/events/{eid}/submit", None),
        ("POST", f"/events/{eid}/cancel", {"reason": "because"}),
        ("DELETE", f"/events/{eid}", None),
        ("POST", f"/events/{eid}/poster", None),
    ]:
        r = (
            await client.request(method, path, headers=admin_b.headers, json=body)
            if method != "POST" or body
            else await client.post(path, headers=admin_b.headers)
        )
        assert r.status_code in (403, 422), (method, path, r.status_code)
        if path.endswith("poster"):
            continue
        assert r.status_code == 403, (method, path)
    # B's managed list excludes A's event; asking for A's club is denied
    assert (await client.get("/events/mine", headers=admin_b.headers)).json()["total"] == 0
    assert (await client.get(f"/events/mine?club_id={club_a['id']}", headers=admin_b.headers)).status_code == 403
    # platform admin can see all
    assert (await client.get("/events/mine", headers=admin.headers)).json()["total"] == 1


async def test_unverified_club_admin_cannot_create(client, make_club, event_payload):
    club, owner = await make_club("Club U", verified=False)
    r = await client.post("/events", headers=owner.headers, json=event_payload(club["id"]))
    assert r.status_code == 403


# ---------------------------------------------------------------- lifecycle
async def test_full_lifecycle(client, make_club, make_event, admin):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner)
    eid = ev["id"]
    # draft is private
    assert (await client.get(f"/events/{eid}")).status_code == 404
    assert (await client.get(f"/events/{eid}", headers=owner.headers)).status_code == 200

    r = await client.post(f"/events/{eid}/submit", headers=owner.headers)
    assert r.json()["status"] == "pending_review"
    # cannot cancel unless published; cannot delete unless draft; cannot submit twice
    assert (
        await client.post(f"/events/{eid}/cancel", headers=owner.headers, json={"reason": "nope"})
    ).status_code == 409
    assert (await client.delete(f"/events/{eid}", headers=owner.headers)).status_code == 409
    assert (await client.post(f"/events/{eid}/submit", headers=owner.headers)).status_code == 409

    q = await client.get("/admin/events", headers=admin.headers)
    assert [e["id"] for e in q.json()["items"]] == [eid]

    r = await client.post(f"/admin/events/{eid}/reject", headers=admin.headers, json={"reason": "Add more detail"})
    assert r.json()["status"] == "rejected" and r.json()["rejection_reason"] == "Add more detail"
    assert (await client.get(f"/events/{eid}")).status_code == 404

    # edit while rejected, resubmit
    r = await client.patch(f"/events/{eid}", headers=owner.headers, json={"description": "More detail now"})
    assert r.json()["status"] == "rejected"
    r = await client.post(f"/events/{eid}/submit", headers=owner.headers)
    assert r.json()["status"] == "pending_review" and r.json()["rejection_reason"] is None

    r = await client.post(f"/admin/events/{eid}/approve", headers=admin.headers)
    assert r.json()["status"] == "published" and r.json()["published_at"]
    assert (await client.get(f"/events/{eid}")).status_code == 200  # public now
    # approving again is an invalid transition
    assert (await client.post(f"/admin/events/{eid}/approve", headers=admin.headers)).status_code == 409

    r = await client.post(f"/events/{eid}/cancel", headers=owner.headers, json={"reason": "Speaker unavailable"})
    assert r.json()["status"] == "cancelled" and r.json()["cancelled"] is True
    assert r.json()["cancel_reason"] == "Speaker unavailable" and r.json()["cancelled_at"]
    # a cancelled event stays readable by id (saved lists and shared links must explain what happened)
    anon = await client.get(f"/events/{eid}")
    assert anon.status_code == 200 and anon.json()["status"] == "cancelled" and anon.json()["cancel_reason"]
    assert (await client.get(f"/events/{eid}", headers=owner.headers)).status_code == 200
    assert (await client.patch(f"/events/{eid}", headers=owner.headers, json={"title": "x"})).status_code == 409


async def test_moderation_requires_platform_admin(client, make_club, make_event):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner, status="pending_review")
    for path in ("approve", "reject", "feature"):
        r = await client.post(f"/admin/events/{ev['id']}/{path}", headers=owner.headers, json={"reason": "xxx"})
        assert r.status_code == 403


async def test_cannot_submit_past_event(client, make_club, event_payload):
    club, owner = await make_club("Club A")
    past = {"start": "2020-01-01T10:00:00+05:30", "end": "2020-01-01T12:00:00+05:30"}
    ev = (await client.post("/events", headers=owner.headers, json=event_payload(club["id"], schedule=past))).json()
    r = await client.post(f"/events/{ev['id']}/submit", headers=owner.headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == "event_in_past"


async def test_delete_draft_only(client, make_club, make_event):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner)
    assert (await client.delete(f"/events/{ev['id']}", headers=owner.headers)).status_code == 204
    assert (await client.get(f"/events/{ev['id']}", headers=owner.headers)).status_code == 404


async def test_featuring(client, make_club, make_event, admin, db):
    club, owner = await make_club("Club A")
    draft = await make_event(club["id"], owner)
    pub = await make_event(club["id"], owner, status="published", admin=admin)
    assert (await client.post(f"/admin/events/{draft['id']}/feature", headers=admin.headers)).status_code == 409
    r = await client.post(f"/admin/events/{pub['id']}/feature", headers=admin.headers)
    assert r.json()["featured"] is True
    assert await db.events.count_documents({"featured.is_featured": True}) == 1
    r = await client.delete(f"/admin/events/{pub['id']}/feature", headers=admin.headers)
    assert r.json()["featured"] is False


async def test_completed_is_derived_not_stored(client, make_club, make_event, admin, db):
    from app.core import timeutil

    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner, status="published", admin=admin)
    assert (await client.get(f"/events/{ev['id']}")).json()["completed"] is False
    timeutil.freeze_time(datetime.now(UTC) + timedelta(days=30))
    assert (await client.get(f"/events/{ev['id']}")).json()["completed"] is True
    assert "completed" not in await db.events.find_one({"title": "Intro to GenAI"})


# ---------------------------------------------------------------- edits and change_log
async def test_edit_published_applies_immediately_and_logs(client, make_club, make_event, admin):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner, status="published", admin=admin)
    r = await client.patch(
        f"/events/{ev['id']}", headers=owner.headers,
        json={"venue": {"name": "AB1 Auditorium", "building": "AB1"}, "title": "Intro to GenAI v2"},
    )  # fmt: skip
    body = r.json()
    assert body["status"] == "published" and body["venue"]["name"] == "AB1 Auditorium"
    assert len(body["change_log"]) == 1
    assert set(body["change_log"][0]["fields"]) == {"venue", "title"}
    assert body["change_log"][0]["by"] == owner.id
    # no-op patch logs nothing
    r = await client.patch(f"/events/{ev['id']}", headers=owner.headers, json={"title": "Intro to GenAI v2"})
    assert len(r.json()["change_log"]) == 1


async def test_change_log_capped_at_20(client, make_club, make_event):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner)
    for i in range(25):
        r = await client.patch(f"/events/{ev['id']}", headers=owner.headers, json={"title": f"Title {i}"})
        assert r.status_code == 200
    assert len(r.json()["change_log"]) == 20


async def test_patch_revalidates_merged_event(client, make_club, make_event):
    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner)
    bad = [
        {"fee": {"type": "fixed"}},
        {"event_type": "hackathon"},  # old workshop details no longer fit
        {"schedule": {"start": "2030-01-02T10:00:00Z", "end": "2030-01-02T09:00:00Z"}},
        {"title": None},
    ]
    for body in bad:
        assert (await client.patch(f"/events/{ev['id']}", headers=owner.headers, json=body)).status_code == 422, body
    r = await client.patch(
        f"/events/{ev['id']}", headers=owner.headers,
        json={"event_type": "hackathon", "details": {"themes": ["AI"], "duration_hours": 24}},
    )  # fmt: skip
    assert r.status_code == 200 and r.json()["details"]["themes"] == ["AI"]


async def test_schedule_edit_updates_denormalized_saved_events(client, make_club, make_event, admin, db):
    from bson import ObjectId

    club, owner = await make_club("Club A")
    ev = await make_event(club["id"], owner, status="published", admin=admin)
    old = datetime.now(UTC)
    await db.saved_events.insert_many(
        [{"user_id": ObjectId(), "event_id": ObjectId(ev["id"]), "status": "saved", "event_start": old} for _ in range(3)]
    )  # fmt: skip
    new_start = datetime.now(UTC) + timedelta(days=9)
    r = await client.patch(
        f"/events/{ev['id']}", headers=owner.headers,
        json={"schedule": {"start": new_start.isoformat(), "end": (new_start + timedelta(hours=1)).isoformat()}},
    )  # fmt: skip
    assert r.status_code == 200
    starts = {s["event_start"] for s in await db.saved_events.find().to_list(None)}
    assert len(starts) == 1 and abs((starts.pop() - new_start).total_seconds()) < 1


async def test_club_rename_updates_event_snapshots(client, make_club, make_event, admin, db):
    club, owner = await make_club("Club A")
    other, other_owner = await make_club("Club B")
    ev = await make_event(club["id"], owner)
    ev2 = await make_event(other["id"], other_owner)
    r = await client.patch(f"/clubs/{club['id']}", headers=owner.headers, json={"name": "Club Alpha"})
    assert r.status_code == 200 and r.json()["name"] == "Club Alpha" and r.json()["slug"] == "club-a"
    got = (await client.get(f"/events/{ev['id']}", headers=owner.headers)).json()
    assert got["club"]["name"] == "Club Alpha"
    assert (await client.get(f"/events/{ev2['id']}", headers=other_owner.headers)).json()["club"]["name"] == "Club B"
    # other club's admin cannot rename; name clash rejected
    assert (
        await client.patch(f"/clubs/{club['id']}", headers=other_owner.headers, json={"name": "Hax"})
    ).status_code == 403
    assert (
        await client.patch(f"/clubs/{club['id']}", headers=owner.headers, json={"name": "club b"})
    ).status_code == 409


# ---------------------------------------------------------------- detail visibility, mine, meta
async def test_mine_filters(client, make_club, make_event, admin):
    club, owner = await make_club("Club A")
    await make_event(club["id"], owner)
    await make_event(club["id"], owner, status="published", admin=admin)
    r = await client.get("/events/mine", headers=owner.headers)
    assert r.json()["total"] == 2
    r = await client.get("/events/mine?status=draft", headers=owner.headers)
    assert r.json()["total"] == 1 and r.json()["items"][0]["status"] == "draft"
    r = await client.get(f"/events/mine?club_id={club['id']}&status=published", headers=owner.headers)
    assert r.json()["total"] == 1


async def test_mine_requires_staff(client, make_user):
    s = await make_user()
    assert (await client.get("/events/mine", headers=s.headers)).status_code == 403


async def test_invalid_ids(client):
    assert (await client.get("/events/not-an-id")).status_code == 422
    assert (await client.get("/events/000000000000000000000000")).status_code == 404


async def test_meta_categories(client):
    r = await client.get("/meta/categories")
    assert len(r.json()["categories"]) == 13 and "hackathon" in r.json()["categories"]
