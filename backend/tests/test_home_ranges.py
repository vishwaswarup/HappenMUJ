from datetime import UTC, datetime


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


async def ids(client, path: str, **kw) -> list[str]:
    r = await client.get(path, **kw)
    assert r.status_code == 200, r.text
    return [e["id"] for e in r.json()["items"]]


# frozen now = 2026-10-09 12:00 IST
async def test_tomorrow_boundaries(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Club A")
    today_2330 = await make_doc(club, utc(2026, 10, 9, 18, 0))  # 23:30 IST today
    midnight = await make_doc(club, utc(2026, 10, 9, 18, 30))  # exactly 00:00 IST tomorrow (included)
    tmrw_0030 = await make_doc(club, utc(2026, 10, 9, 19, 0))  # 00:30 IST tomorrow
    tmrw_2359 = await make_doc(club, utc(2026, 10, 10, 18, 29))  # 23:59 IST tomorrow
    day_after = await make_doc(club, utc(2026, 10, 10, 18, 30))  # exactly 00:00 IST day after (excluded)
    got = await ids(client, "/home/tomorrow")
    assert got == [str(midnight["_id"]), str(tmrw_0030["_id"]), str(tmrw_2359["_id"])]
    assert str(today_2330["_id"]) not in got and str(day_after["_id"]) not in got


async def test_tomorrow_empty_is_valid(client, freeze):
    freeze()
    r = await client.get("/home/tomorrow")
    assert r.status_code == 200 and r.json() == {"items": []}


async def test_next_7_days_boundaries_and_order(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Club A")
    past_today = await make_doc(club, utc(2026, 10, 9, 3, 0))  # 08:30 IST: already started
    later_today = await make_doc(club, utc(2026, 10, 9, 17, 0))  # 22:30 IST today
    day7_last = await make_doc(club, utc(2026, 10, 15, 18, 29))  # 23:59 IST on the 15th: last included minute
    day8 = await make_doc(club, utc(2026, 10, 15, 18, 30))  # 00:00 IST on the 16th: excluded
    closed = await make_doc(club, utc(2026, 10, 10, 6, 0), registration={"required": False})
    got = await ids(client, "/home/next-7-days")
    # chronological; items without open registration are NOT pushed down
    assert got == [str(later_today["_id"]), str(closed["_id"]), str(day7_last["_id"])]
    assert str(past_today["_id"]) not in got and str(day8["_id"]) not in got
    items = (await client.get("/home/next-7-days")).json()["items"]
    assert [i["registration_open"] for i in items] == [True, False, True]


async def test_ranges_follow_ist_not_utc_date(client, freeze, make_club, make_doc):
    # now = 00:30 IST on the 10th (= 19:00 UTC on the 9th): tomorrow is the 11th IST
    freeze(utc(2026, 10, 9, 19, 0))
    club, _ = await make_club("Club A")
    on_10th = await make_doc(club, utc(2026, 10, 10, 6, 0))
    on_11th = await make_doc(club, utc(2026, 10, 11, 6, 0))
    assert await ids(client, "/home/tomorrow") == [str(on_11th["_id"])]
    assert str(on_10th["_id"]) in await ids(client, "/home/next-7-days")


async def test_range_sections_hide_nonpublic(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Club A")
    start = utc(2026, 10, 10, 6, 0)
    ok = await make_doc(club, start)
    for status in ("draft", "pending_review", "rejected", "cancelled"):
        await make_doc(club, start, status=status)
    await make_doc(club, start, cancelled_at=utc(2026, 10, 9, 1, 0))  # published but cancelled_at set
    assert await ids(client, "/home/tomorrow") == [str(ok["_id"])]
    assert await ids(client, "/home/next-7-days") == [str(ok["_id"])]


async def test_card_shape(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Club A")
    await make_doc(club, utc(2026, 10, 10, 6, 0), fee={"type": "not_specified", "amount": None, "currency": "INR"})
    card = (await client.get("/home/tomorrow")).json()["items"][0]
    assert set(card) == {
        "id", "title", "one_liner", "club", "category", "event_type", "tags", "poster_url", "schedule",
        "venue", "fee", "team", "registration", "registration_open", "featured", "stats", "is_saved",
    }  # fmt: skip
    assert card["fee"]["display"] == "Fee not specified" and card["is_saved"] is None
    assert "description" not in card and "url" not in card["registration"]
    assert card["club"]["slug"] == "club-a"


async def test_registration_open_rules(client, freeze, make_club, make_doc):
    freeze()
    club, _ = await make_club("Club A")
    s = utc(2026, 10, 12, 6, 0)
    reg = lambda **kw: {"required": True, "platform": "other", "url": "https://x.example.com", "deadline": None, **kw}  # noqa: E731
    cases = {
        "open_no_deadline": (reg(), True),
        "open_future_deadline": (reg(deadline=utc(2026, 10, 11, 0, 0)), True),
        "closed_deadline": (reg(deadline=utc(2026, 10, 8, 0, 0)), False),
        "not_required": (reg(required=False), False),
    }
    docs = {k: await make_doc(club, s, registration=r, title=k) for k, (r, _) in cases.items()}
    items = {i["title"]: i for i in (await client.get("/home/next-7-days")).json()["items"]}
    for k, (_, expected) in cases.items():
        assert items[k]["registration_open"] is expected, k
    assert docs
