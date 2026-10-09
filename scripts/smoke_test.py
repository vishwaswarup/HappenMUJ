#!/usr/bin/env python3
"""End-to-end smoke test of a RUNNING HappenMUJ stack, through the same paths the frontend uses.

    python3 scripts/smoke_test.py                       # API at http://localhost:8000/api (seeded database)
    python3 scripts/smoke_test.py http://localhost:5173/api     # or through the Vite dev proxy

Standard library only. Needs the demo seed (`python -m app.seed --reset`). It CREATES data (a new event,
a post...), so re-seed afterwards if you want a pristine demo. Exit code 0 = everything passed.
"""

import json
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api").rstrip("/")
IST = ZoneInfo("Asia/Kolkata")
PASSED: list[str] = []


def call(method, path, *, token=None, body=None, query=None, raw=None, headers=None, expect=None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    h = {"Accept": "application/json", **(headers or {})}
    data = raw
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            status, payload = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    parsed = json.loads(payload) if payload else None
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} -> {status} (expected {expect}): {str(parsed)[:300]}")
    return status, parsed


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"FAILED: {name} {detail}")
    PASSED.append(name)
    print(f"  ok  {name}")


def login(email: str, password: str = "demo1234") -> tuple[str, dict]:
    _, r = call("POST", "/auth/login", body={"email": email, "password": password}, expect=200)
    return r["access_token"], r["user"]


def all_catalogue(token=None, **query) -> list[dict]:
    out, page = [], 1
    while True:
        _, r = call("GET", "/events", token=token, query={**query, "page": page, "page_size": 50}, expect=200)
        out += r["items"]
        if len(out) >= r["total"] or not r["items"]:
            return out
        page += 1


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def tiny_png() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x20\x40\xc0" * 8 for _ in range(8))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def multipart(field: str, filename: str, ctype: str, content: bytes) -> tuple[bytes, dict]:
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def main() -> None:
    print(f"Smoke test against {BASE}\n")

    print("auth")
    st_tok, student = login("student@muj-demo.edu")
    ac_tok, acm_admin = login("acm@muj-demo.edu")
    ad_tok, admin = login("admin@muj-demo.edu")
    check("student login", student["role"] == "student" and student["managed_club_ids"] == [])
    check("club admin login manages exactly one club", acm_admin["role"] == "club_admin" and len(acm_admin["managed_club_ids"]) == 1)
    check("platform admin login", admin["role"] == "platform_admin")
    _, me = call("GET", "/auth/me", token=st_tok, expect=200)
    check("/auth/me has the frontend's fields", set(me) >= {"id", "name", "email", "role", "interests", "preferred_categories", "followed_club_ids", "managed_club_ids"})
    check("student interests seeded", "ai" in me["interests"] and len(me["followed_club_ids"]) == 3)
    s, err = call("POST", "/auth/login", body={"email": "student@muj-demo.edu", "password": "wrong-password"})
    check("bad password -> 401 with the standard error body", s == 401 and err["error"]["code"] == "unauthorized")
    uniq = uuid.uuid4().hex[:8]
    _, reg = call("POST", "/auth/register", body={"name": "Smoke Test", "email": f"smoke{uniq}@muj-demo.edu", "password": "demo1234", "interests": ["AI", "ai", "Music"]}, expect=201)
    check("register accepts interests (normalised)", reg["user"]["interests"] == ["ai", "music"] and "access_token" in reg)

    print("clubs")
    _, clubs = call("GET", "/clubs", query={"page_size": 50}, expect=200)
    by_slug = {c["slug"]: c for c in clubs["items"]}
    check("16 verified clubs with the real slugs", clubs["total"] == 16 and {"acm", "ieee-sb", "the-musical-club-tmc", "de-artistry-club", "glitch"} <= set(by_slug))
    acm_id, ieee_id = by_slug["acm"]["id"], by_slug["ieee-sb"]["id"]
    check("acm admin manages ACM", acm_admin["managed_club_ids"] == [acm_id])

    print("catalogue: OR within a group, AND between groups, facets")
    every = all_catalogue()
    check("catalogue is published + upcoming only", all(e["status"] == "published" and parse(e["schedule"]["start"]) > datetime.now(UTC) - timedelta(seconds=5) for e in every), f"({len(every)} events)")
    cats = sorted({e["category"] for e in every})
    two_cats = ["technical", "cultural"] if {"technical", "cultural"} <= set(cats) else cats[:2]
    clubs_sel = [acm_id, ieee_id]
    got = all_catalogue(category=two_cats, club=clubs_sel)
    expected = [e for e in every if e["category"] in two_cats and e["club"]["id"] in clubs_sel]
    check("(cat1 OR cat2) AND (club1 OR club2) matches the expected set", {e["id"] for e in got} == {e["id"] for e in expected} and len(got) > 0, f"got {len(got)} expected {len(expected)}")
    only_cats = all_catalogue(category=two_cats)
    check("OR within the category group (union of both categories)", {e["id"] for e in only_cats} == {e["id"] for e in every if e["category"] in two_cats} and len({e["category"] for e in only_cats}) == 2)
    only_clubs = all_catalogue(club=clubs_sel)
    check("OR within the club group", {e["club"]["id"] for e in only_clubs} == set(clubs_sel))
    check("AND narrows (intersection is smaller than either group alone)", len(got) < len(only_cats) and len(got) <= len(only_clubs))
    check("club filter also accepts a slug", {e["id"] for e in all_catalogue(club=["acm"])} == {e["id"] for e in every if e["club"]["id"] == acm_id})
    _, page = call("GET", "/events", query={"category": two_cats, "club": clubs_sel, "page_size": 50}, expect=200)
    exp_cat_facet = {}
    for e in every:  # category facet: club filter applied, category filter ignored
        if e["club"]["id"] in clubs_sel:
            exp_cat_facet[e["category"]] = exp_cat_facet.get(e["category"], 0) + 1
    exp_club_facet = {}
    for e in every:  # club facet: category filter applied, club filter ignored
        if e["category"] in two_cats:
            exp_club_facet[e["club"]["id"]] = exp_club_facet.get(e["club"]["id"], 0) + 1
    check("facets {category:{id:n}, club:{id:n}}: each ignores its own group's filter", page["facets"] == {"category": exp_cat_facet, "club": exp_club_facet})
    card = every[0]
    check("event card has the contract fields", set(card) >= {"id", "title", "one_liner", "club", "category", "event_type", "tags", "poster_url", "schedule", "venue", "fee", "team", "registration", "registration_open", "featured", "status", "stats"})
    check("fee.display never assumes free", all(e["fee"]["display"] == "Fee not specified" for e in every if e["fee"]["type"] == "not_specified") and any(e["fee"]["type"] == "not_specified" for e in every))
    _, srch = call("GET", "/events", query={"q": "generative"}, expect=200)
    check("text search finds 'generative'", any("Generative" in e["title"] for e in srch["items"]))
    _, bypop = call("GET", "/events", query={"sort": "popularity", "page_size": 5}, expect=200)
    check("sort=popularity works", len(bypop["items"]) == 5)

    print("home sections")
    _, feat = call("GET", "/home/featured", expect=200)
    check("featured is a bare card", feat["featured"] is True and feat["title"] == "HackMUJ 24h" and "id" in feat)
    _, top = call("GET", "/home/top-events", expect=200)
    check("top-10 returns 10 ranked items", [i["rank"] for i in top["items"]] == list(range(1, 11)))
    it = top["items"][0]
    check("top-10 items carry score_breakdown (numbers) and window", all(isinstance(v, int | float) for v in it["score_breakdown"].values()) and set(it["window"]) == {"saves", "views", "registration_clicks"})
    check("top-10 has the disclaimer", "not an official endorsement" in top["disclaimer"])
    scores = [i["score"] for i in top["items"]]
    check("top-10 sorted by score", scores == sorted(scores, reverse=True))
    _, cfg = call("GET", "/home/top-events/config", expect=200)
    check("ranking config", set(cfg["weights"]) == {"saves", "views", "registration_clicks", "proximity", "urgency"} and cfg["window_days"] == 7)
    _, sug_anon = call("GET", "/home/suggested", expect=200)
    _, sug = call("GET", "/home/suggested", token=st_tok, expect=200)
    check("suggested {items, personalised}: anonymous vs signed in", sug_anon["personalised"] is False and sug["personalised"] is True and len(sug["items"]) > 0)

    now = datetime.now(UTC)
    today_ist = now.astimezone(IST).date()
    midnight = lambda d: datetime(d.year, d.month, d.day, tzinfo=IST)  # noqa: E731
    t_from, t_to = midnight(today_ist + timedelta(days=1)), midnight(today_ist + timedelta(days=2))
    _, tmr = call("GET", "/home/tomorrow", expect=200)
    check("tomorrow = [00:00 IST tomorrow, 00:00 IST the day after)", len(tmr["items"]) > 0 and all(t_from <= parse(e["schedule"]["start"]) < t_to for e in tmr["items"]))
    check("tomorrow contains every published event in that window", {e["id"] for e in tmr["items"]} == {e["id"] for e in every if t_from <= parse(e["schedule"]["start"]) < t_to})
    n_to = midnight(today_ist + timedelta(days=7))
    _, n7 = call("GET", "/home/next-7-days", expect=200)
    starts = [parse(e["schedule"]["start"]) for e in n7["items"]]
    check("next-7-days = [now, 00:00 IST today+7)", len(starts) > 0 and all(now - timedelta(seconds=5) <= s < n_to for s in starts) and starts == sorted(starts))
    check("next-7-days contains every published event in that window", {e["id"] for e in n7["items"]} == {e["id"] for e in every if now <= parse(e["schedule"]["start"]) < n_to} or abs(len(n7["items"]) - len([e for e in every if now <= parse(e["schedule"]["start"]) < n_to])) <= 1)

    print("event page, cancelled events, views")
    ev = n7["items"][0]
    _, detail = call("GET", f"/events/{ev['id']}", expect=200)
    check("detail has description, details, contact, registration.url, venue.room, reasons", set(detail) >= {"description", "details", "contact", "registration", "venue", "rejection_reason", "cancel_reason", "published_at"} and "url" in detail["registration"] and "room" in detail["venue"])
    _, adm_all = call("GET", "/admin/events", token=ad_tok, query={"status": "cancelled", "page_size": 50}, expect=200)
    cancelled = adm_all["items"]
    check("cancelled events exist and are readable by id without logging in", len(cancelled) >= 1 and call("GET", f"/events/{cancelled[0]['id']}", expect=200)[1]["status"] == "cancelled")
    check("cancelled events are not in the catalogue", not ({e["id"] for e in cancelled} & {e["id"] for e in every}))
    _, pend = call("GET", "/admin/events", token=ad_tok, query={"status": "pending_review"}, expect=200)
    check("pending events are not public", call("GET", f"/events/{pend['items'][0]['id']}")[0] == 404)
    s, _ = call("POST", f"/events/{ev['id']}/view")
    check("record a view", s == 200)

    print("saved events and the registration click")
    target = next(e for e in every if e["registration"]["required"] and e["registration_open"] and not e.get("is_saved"))
    _, tdetail = call("GET", f"/events/{target['id']}", token=st_tok, expect=200)
    s1, _ = call("POST", "/saved-events", token=st_tok, body={"event_id": target["id"]})
    s2, _ = call("POST", "/saved-events", token=st_tok, body={"event_id": target["id"]})
    check("save is idempotent (201 then 200)", (s1, s2) == (201, 200))
    _, saved = call("GET", "/saved-events", token=st_tok, expect=200)
    mine = next(x for x in saved["items"] if x["event"]["id"] == target["id"])
    check("saved list shape {event, status, saved_at, cancelled}", mine["status"] == "saved" and mine["cancelled"] is False and "saved_at" in mine)
    check("all saved events are returned (>= the 6 seeded)", len(saved["items"]) >= 7)
    s, click = call("POST", f"/events/{target['id']}/registration-click", token=st_tok)
    check("registration click returns {url}", s == 200 and click["url"].startswith("http"))
    _, saved2 = call("GET", "/saved-events", token=st_tok, expect=200)
    check("click sets the saved status to registration_initiated", next(x for x in saved2["items"] if x["event"]["id"] == target["id"])["status"] == "registration_initiated")
    s, _ = call("DELETE", f"/saved-events/{target['id']}", token=st_tok)
    s_again, _ = call("DELETE", f"/saved-events/{target['id']}", token=st_tok)
    _, saved3 = call("GET", "/saved-events", token=st_tok, expect=200)
    check("unsave is idempotent and removes it", (s, s_again) == (204, 204) and all(x["event"]["id"] != target["id"] for x in saved3["items"]))
    pair = sorted(((x["event"]["schedule"]["start"], x["event"]["schedule"]["end"], x["event"]["title"]) for x in saved3["items"]))
    overlaps = [(a[2], b[2]) for i, a in enumerate(pair) for b in pair[i + 1 :] if b[0] < a[1]]
    check("the demo student's saved events contain an overlapping pair", ("Intro to Generative AI", "Open Mic Night") in overlaps)

    print("club admin: create -> poster -> submit; platform admin: approve, feature")
    start = (now + timedelta(days=10)).astimezone(IST).replace(hour=15, minute=0, second=0, microsecond=0)
    new_event = {  # exactly what EventForm builds
        "title": f"Smoke Test Workshop {uniq}", "one_liner": "Created by the smoke test.", "description": "Checks the whole flow.",
        "club_id": acm_id, "category": "workshop", "event_type": "workshop", "tags": ["smoke", "test"],
        "schedule": {"start": iso(start), "end": iso(start + timedelta(hours=2))},
        "venue": {"name": "AB3 Seminar Hall", "building": "AB3", "room": None},
        "fee": {"type": "fixed", "amount": 199, "currency": "INR"},
        "team": {"type": "individual", "min": None, "max": None},
        "registration": {"required": True, "platform": "google_forms", "url": "https://forms.example.com/smoke", "deadline": iso(start - timedelta(days=1))},
        "contact": {"name": "Smoke", "email": "smoke@example.com"},
        "details": {"speaker": {"name": "Dr Test"}, "topics": ["A", "B"], "duration_minutes": 120, "bring_own_laptop": True},
    }  # fmt: skip
    _, created = call("POST", "/events", token=ac_tok, body=new_event, expect=201)
    eid = created["id"]
    check("club admin creates a draft", created["status"] == "draft" and created["fee"]["display"] == "₹199")
    body, hdr = multipart("file", "poster.png", "image/png", tiny_png())
    _, withposter = call("POST", f"/events/{eid}/poster", token=ac_tok, raw=body, headers=hdr, expect=200)
    check("poster upload (multipart)", withposter["poster_url"] and withposter["poster_url"].startswith("/api/"))
    purl = withposter["poster_url"].removeprefix("/api")
    req = urllib.request.Request(BASE + purl)
    with urllib.request.urlopen(req) as r:
        check("poster streams back as an image", r.status == 200 and r.headers["content-type"] == "image/png")
    _, edited = call("PATCH", f"/events/{eid}", token=ac_tok, body={**new_event, "title": new_event["title"] + " v2"}, expect=200)
    check("PATCH with the full form payload (club_id included) works", edited["title"].endswith("v2"))
    _, mine_ev = call("GET", "/events/mine", token=ac_tok, query={"page_size": 50}, expect=200)
    check("my events lists drafts too", any(m["id"] == eid and m["status"] == "draft" for m in mine_ev["items"]))
    check("a student cannot create events", call("POST", "/events", token=st_tok, body=new_event)[0] == 403)
    _, other = call("GET", "/events/mine", token=login("ieee-sb@muj-demo.edu")[0], query={"page_size": 50}, expect=200)
    check("another club's admin does not see it", all(m["id"] != eid for m in other["items"]))
    _, sub = call("POST", f"/events/{eid}/submit", token=ac_tok, expect=200)
    check("submit for review", sub["status"] == "pending_review")
    _, queue = call("GET", "/admin/events", token=ad_tok, query={"status": "pending_review", "page_size": 50}, expect=200)
    check("admin sees it in the review queue", any(q["id"] == eid for q in queue["items"]))
    check("club admin cannot approve", call("POST", f"/admin/events/{eid}/approve", token=ac_tok)[0] == 403)
    call("POST", f"/admin/events/{eid}/approve", token=ad_tok, expect=200)
    check("approved event appears in the public catalogue", any(e["id"] == eid for e in all_catalogue()))
    call("POST", f"/admin/events/{eid}/feature", token=ad_tok, expect=200)
    _, f2 = call("GET", "/home/featured", expect=200)
    check("feature on makes it the featured event", f2["id"] == eid)
    call("DELETE", f"/admin/events/{eid}/feature", token=ad_tok, expect=200)
    check("feature off restores the previous one", call("GET", "/home/featured", expect=200)[1]["title"] == "HackMUJ 24h")
    _, rej = call("POST", f"/admin/events/{pend['items'][0]['id']}/reject", token=ad_tok, body={"reason": "Needs a clearer description."}, expect=200)
    check("reject with a reason", rej["status"] == "rejected" and rej["rejection_reason"])
    _, canc = call("POST", f"/events/{eid}/cancel", token=ac_tok, body={"reason": "Smoke test cleanup"}, expect=200)
    check("cancel with a reason", canc["status"] == "cancelled" and canc["cancel_reason"] == "Smoke test cleanup")
    check("cancelled event leaves the catalogue but stays readable", all(e["id"] != eid for e in all_catalogue()) and call("GET", f"/events/{eid}", expect=200)[1]["status"] == "cancelled")
    _, d2 = call("POST", "/events", token=ac_tok, body={**new_event, "title": "Throwaway draft " + uniq}, expect=201)
    check("delete a draft", call("DELETE", f"/events/{d2['id']}", token=ac_tok)[0] == 204 and call("GET", f"/events/{d2['id']}", token=ac_tok)[0] == 404)
    _, club_req = call("POST", "/clubs", token=st_tok, body={"name": f"Smoke Club {uniq}", "description": "x", "category": "other"}, expect=201)
    check("request a new club (unverified)", club_req["verified"] is False)
    _, pending_clubs = call("GET", "/admin/clubs", token=ad_tok, query={"status": "pending"}, expect=200)
    check("admin sees pending clubs", any(c["id"] == club_req["id"] for c in pending_clubs["items"]))
    call("POST", f"/admin/clubs/{club_req['id']}/verify", token=ad_tok, expect=200)
    check("verify a club", any(c["id"] == club_req["id"] for c in call("GET", "/clubs", query={"page_size": 50}, expect=200)[1]["items"]))

    print("community: post, comment (2 levels), reactions, delete")
    _, post = call("POST", "/posts", token=st_tok, body={"scope": {"type": "event", "ref_id": ev["id"]}, "title": f"Smoke post {uniq}", "body": "Anyone going?"}, expect=201)
    check("post with scope + ref_label", post["scope"]["ref_label"] == ev["title"] and post["author"]["name"] == "Demo Student" and post["reaction_counts"] == {"like": 0, "insightful": 0})
    _, c1 = call("POST", f"/posts/{post['id']}/comments", token=ac_tok, body={"body": "Yes!", "parent_id": None}, expect=201)
    _, c2 = call("POST", f"/posts/{post['id']}/comments", token=st_tok, body={"body": "Great", "parent_id": c1["id"]}, expect=201)
    _, c3 = call("POST", f"/posts/{post['id']}/comments", token=ac_tok, body={"body": "reply to reply", "parent_id": c2["id"]}, expect=201)
    check("a reply to a reply attaches to the top-level parent (two levels)", c3["parent_id"] == c1["id"])
    _, thread = call("GET", f"/posts/{post['id']}/comments", token=st_tok, query={"page_size": 50}, expect=200)
    top_c = thread["items"][0]
    check("comments come back as a tree with replies", thread["total"] == 1 and [r["body"] for r in top_c["replies"]] == ["Great", "reply to reply"] and top_c["author"]["name"].endswith("Admin"))
    _, r1 = call("PUT", "/reactions", token=st_tok, body={"target_type": "post", "target_id": post["id"], "kind": "like"}, expect=200)
    _, r2 = call("PUT", "/reactions", token=st_tok, body={"target_type": "post", "target_id": post["id"], "kind": "insightful"}, expect=200)
    _, r3 = call("PUT", "/reactions", token=st_tok, body={"target_type": "post", "target_id": post["id"], "kind": "insightful"}, expect=200)
    check("reaction toggles: like -> switch to insightful -> toggle off", (r1["my_reaction"], r2["my_reaction"], r3["my_reaction"]) == ("like", "insightful", None) and r2["reaction_counts"] == {"like": 0, "insightful": 1} and r3["reaction_counts"] == {"like": 0, "insightful": 0})
    call("PUT", "/reactions", token=st_tok, body={"target_type": "comment", "target_id": c1["id"], "kind": "like"}, expect=200)
    _, feed = call("GET", "/posts", token=st_tok, query={"scope": "event", "ref_id": ev["id"]}, expect=200)
    fp = next(p for p in feed["items"] if p["id"] == post["id"])
    check("feed post: comment_count, recent_comments with authors, my_reaction", fp["comment_count"] == 3 and len(fp["recent_comments"]) == 3 and fp["recent_comments"][0]["author"]["name"] and fp["my_reaction"] is None)
    check("only the author or an admin can delete", call("DELETE", f"/comments/{c1['id']}", token=st_tok)[0] == 403)
    call("DELETE", f"/comments/{c2['id']}", token=st_tok, expect=204)
    _, t2 = call("GET", f"/posts/{post['id']}/comments", token=st_tok, expect=200)
    gone = next(r for r in t2["items"][0]["replies"] if r["id"] == c2["id"])
    check("a removed comment keeps a placeholder", gone["status"] == "removed" and gone["body"] == "[removed]")
    call("DELETE", f"/posts/{post['id']}", token=ad_tok, expect=204)
    check("a platform admin can delete any post", call("GET", f"/posts/{post['id']}")[0] == 404)

    print("profile")
    _, patched = call("PATCH", "/users/me", token=reg["access_token"], body={"interests": ["Robotics"], "preferred_categories": ["technical"]}, expect=200)
    check("PATCH /users/me", patched["interests"] == ["robotics"] and patched["preferred_categories"] == ["technical"])
    call("POST", f"/users/me/follow/{acm_id}", token=reg["access_token"], expect=200)
    _, after = call("GET", "/auth/me", token=reg["access_token"], expect=200)
    check("follow a club", after["followed_club_ids"] == [acm_id])
    call("DELETE", f"/users/me/follow/{acm_id}", token=reg["access_token"], expect=200)
    check("unfollow a club", call("GET", "/auth/me", token=reg["access_token"], expect=200)[1]["followed_club_ids"] == [])

    print(f"\nAll {len(PASSED)} checks passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
