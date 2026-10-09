from datetime import UTC, datetime
from urllib.parse import urlencode

from bson import ObjectId


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def S(day: int, hour: int = 6) -> datetime:
    return utc(2026, 10, day, hour, 0)


async def get(client, **params):
    qs = urlencode(params, doseq=True)
    r = await client.get(f"/events?{qs}")
    assert r.status_code == 200, r.text
    return r.json()


def titles(body) -> list[str]:
    return [i["title"] for i in body["items"]]


async def setup_grid(client, freeze, make_club, make_doc):
    """2 categories x 2 clubs (+ extras) to exercise (A OR B) AND (C OR D)."""
    freeze()
    acm, _ = await make_club("ACM")
    ieee, _ = await make_club("IEEE")
    lit, _ = await make_club("LITMUS")
    rows = [
        ("acm-tech", acm, "technical", 10), ("acm-hack", acm, "hackathon", 11), ("acm-cult", acm, "cultural", 12),
        ("ieee-tech", ieee, "technical", 13), ("ieee-hack", ieee, "hackathon", 14), ("ieee-spo", ieee, "sports", 15),
        ("lit-tech", lit, "technical", 16), ("lit-cult", lit, "cultural", 17),
    ]  # fmt: skip
    for title, club, cat, day in rows:
        await make_doc(club, S(day), title=title, category=cat)
    return acm, ieee, lit


async def test_filter_or_within_group_and_between_groups(client, freeze, make_club, make_doc):
    await setup_grid(client, freeze, make_club, make_doc)
    body = await get(client, category=["technical", "hackathon"], club=["acm", "ieee"])
    # (technical OR hackathon) AND (acm OR ieee)
    assert titles(body) == ["acm-tech", "acm-hack", "ieee-tech", "ieee-hack"]
    assert body["total"] == 4
    # single group
    assert titles(await get(client, category=["cultural"])) == ["acm-cult", "lit-cult"]
    assert titles(await get(client, club=["litmus"])) == ["lit-tech", "lit-cult"]
    # AND narrows
    assert titles(await get(client, category="technical", club="ieee")) == ["ieee-tech"]
    assert (await get(client, category="gaming"))["total"] == 0


async def test_club_filter_accepts_id_or_slug(client, freeze, make_club, make_doc):
    acm, ieee, _ = await setup_grid(client, freeze, make_club, make_doc)
    by_id = await get(client, club=[acm["id"], ieee["id"]], category="sports")
    assert titles(by_id) == ["ieee-spo"]
    assert titles(await get(client, club=["acm", ieee["id"]], category="hackathon")) == ["acm-hack", "ieee-hack"]
    assert (await get(client, club="no-such-club"))["total"] == 0


async def test_facets_are_disjunctive_and_scoped(client, freeze, make_club, make_doc):
    acm, ieee, lit = await setup_grid(client, freeze, make_club, make_doc)
    body = await get(client, category=["technical"], club=["acm"])
    assert titles(body) == ["acm-tech"]
    # the frontend contract: facets = {category: {id: count}, club: {club id: count}}
    assert set(body["facets"]) == {"category", "club"}
    # category counts ignore the category filter but respect the club filter (acm only)
    assert body["facets"]["category"] == {"technical": 1, "hackathon": 1, "cultural": 1}
    # club counts ignore the club filter but respect the category filter (technical only), keyed by club id
    assert body["facets"]["club"] == {acm["id"]: 1, ieee["id"]: 1, lit["id"]: 1}
    # unfiltered: counts add up to total
    allb = await get(client)
    assert sum(allb["facets"]["category"].values()) == sum(allb["facets"]["club"].values()) == allb["total"] == 8


async def test_pagination_total_and_page_size_cap(client, freeze, make_club, make_doc):
    await setup_grid(client, freeze, make_club, make_doc)
    p1 = await get(client, page_size=3, page=1)
    p3 = await get(client, page_size=3, page=3)
    assert (p1["total"], p1["page"], p1["page_size"], len(p1["items"])) == (8, 1, 3, 3)
    assert len(p3["items"]) == 2 and p3["total"] == 8
    assert (await client.get("/events?page_size=51")).status_code == 422


async def test_only_public_events_in_catalogue(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, S(12), title="visible")
    for st in ("draft", "pending_review", "rejected", "cancelled"):
        await make_doc(club, S(12), title=st, status=st)
    body = await get(client)
    assert titles(body) == ["visible"]
    assert list(body["facets"]["category"].values()) == [1]


async def test_only_upcoming_events_even_with_a_date_window(client, freeze, make_club, make_doc):
    """Frontend contract: the catalogue is published AND upcoming (start > now), always."""
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, utc(2026, 10, 1, 6), title="past")
    await make_doc(club, utc(2026, 10, 9, 5, 0), hours=3, title="already started")  # started before now (06:30 UTC)
    await make_doc(club, S(12), title="future")
    assert titles(await get(client)) == ["future"]
    assert (await get(client, date_from="2026-10-01", date_to="2026-10-02"))[
        "total"
    ] == 0  # a window cannot resurrect the past


async def test_date_window_accepts_iso_instants_half_open(client, freeze, make_club, make_doc):
    """The frontend sends from.toISOString() / to.toISOString(): inclusive lower bound, exclusive upper bound."""
    freeze()
    club, _ = await make_club("ACM")
    # IST day 2026-10-13 = [2026-10-12T18:30Z, 2026-10-13T18:30Z)
    for title, start in {
        "before": utc(2026, 10, 12, 18, 29),
        "first instant": utc(2026, 10, 12, 18, 30),
        "last minute": utc(2026, 10, 13, 18, 29),
        "next day": utc(2026, 10, 13, 18, 30),
    }.items():
        await make_doc(club, start, title=title)
    got = await get(client, date_from="2026-10-12T18:30:00.000Z", date_to="2026-10-13T18:30:00.000Z")
    assert titles(got) == ["first instant", "last minute"]
    # offsets are honoured too
    got = await get(client, date_from="2026-10-13T00:00:00+05:30", date_to="2026-10-14T00:00:00+05:30")
    assert titles(got) == ["first instant", "last minute"]
    for bad in (
        {"date_from": "yesterday"},
        {"date_from": "2026-10-13T10:00:00"},
        {"date_from": "2026-10-14", "date_to": "2026-10-13"},
    ):
        assert (await client.get("/events", params=bad)).status_code == 422, bad


async def test_date_filters_use_ist_days_inclusive(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, utc(2026, 10, 12, 18, 29), title="12th 23:59 IST")
    await make_doc(club, utc(2026, 10, 12, 18, 30), title="13th 00:00 IST")
    await make_doc(club, utc(2026, 10, 13, 18, 29), title="13th 23:59 IST")
    await make_doc(club, utc(2026, 10, 13, 18, 30), title="14th 00:00 IST")
    assert titles(await get(client, date_from="2026-10-13", date_to="2026-10-13")) == [
        "13th 00:00 IST",
        "13th 23:59 IST",
    ]
    assert titles(await get(client, date_from="2026-10-13")) == ["13th 00:00 IST", "13th 23:59 IST", "14th 00:00 IST"]
    assert (await client.get("/events?date_from=2026-10-14&date_to=2026-10-13")).status_code == 422


async def test_sort_popularity(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, S(10), title="meh", stats={"views": 1, "saves": 0, "registration_clicks": 0})
    await make_doc(club, S(11), title="hot", stats={"views": 10, "saves": 20, "registration_clicks": 5})
    await make_doc(club, S(12), title="warm", stats={"views": 50, "saves": 2, "registration_clicks": 1})
    assert titles(await get(client, sort="popularity")) == ["hot", "warm", "meh"]
    assert titles(await get(client, sort="date")) == ["meh", "hot", "warm"]


# ---------------------------------------------------------------- text search
async def test_text_search_ranks_by_field_weights(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Robotix")
    # same term "quantum", placed in fields of decreasing weight; later start dates for the better matches
    await make_doc(club, S(10), title="Bake sale", description="we mention quantum once", one_liner="cakes")
    await make_doc(club, S(11), title="Open mic", one_liner="quantum of fun", description="songs")
    await make_doc(club, S(12), title="Chess night", tags=["quantum"], description="board games")
    await make_doc(club, S(13), title="Quantum computing intro", description="qubits")
    body = await get(client, q="quantum")
    assert titles(body) == ["Quantum computing intro", "Chess night", "Open mic", "Bake sale"]


async def test_text_search_matches_club_name_and_respects_filters(client, freeze, make_club, make_doc):
    freeze()
    robo, _ = await make_club("Robotix")
    other, _ = await make_club("Chess Club")
    await make_doc(robo, S(10), title="Line follower", category="technical")
    await make_doc(other, S(11), title="Blitz", category="gaming")
    await make_doc(other, S(12), title="Hidden", category="gaming", status="draft")
    assert titles(await get(client, q="robotix")) == ["Line follower"]  # club_snapshot.name is indexed
    assert titles(await get(client, q="blitz hidden")) == ["Blitz"]
    assert (await get(client, q="blitz", category="technical"))["total"] == 0
    assert (await client.get("/events?sort=relevance")).status_code == 422


async def test_search_facets_scoped_to_matches(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("ACM")
    await make_doc(club, S(10), title="Python bootcamp", category="technical")
    await make_doc(club, S(11), title="Python for artists", category="cultural")
    await make_doc(club, S(12), title="Dance", category="cultural")
    body = await get(client, q="python")
    assert body["facets"]["category"] == {"technical": 1, "cultural": 1}


async def test_invalid_category_filter(client):
    assert (await client.get("/events?category=nonsense")).status_code == 422


async def test_is_saved_only_when_authenticated(client, freeze, make_club, make_doc, make_user, db):
    freeze()
    club, _ = await make_club("ACM")
    ev = await make_doc(club, S(10), title="a")
    await make_doc(club, S(11), title="b")
    u = await make_user()
    await db.saved_events.insert_one(
        {"user_id": ObjectId(u.id), "event_id": ev["_id"], "status": "saved", "event_start": ev["schedule"]["start"]}
    )
    anon = await get(client)
    assert all(i["is_saved"] is None for i in anon["items"])
    r = await client.get("/events", headers=u.headers)
    assert {i["title"]: i["is_saved"] for i in r.json()["items"]} == {"a": True, "b": False}


async def test_catalogue_does_not_collide_with_mine(client, make_user):
    s = await make_user()
    assert (await client.get("/events/mine", headers=s.headers)).status_code == 403
