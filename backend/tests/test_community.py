import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

NOW = datetime(2026, 10, 9, 6, 30, tzinfo=UTC)


async def post(client, actor, title="Hello", body="World", scope=None, **kw):
    payload = {"title": title, "body": body, **kw}
    if scope:
        payload["scope"] = scope
    r = await client.post("/posts", headers=actor.headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def comment(client, actor, post_id, body="hi", parent_id=None, expect=201):
    r = await client.post(
        f"/posts/{post_id}/comments", headers=actor.headers, json={"body": body, "parent_id": parent_id}
    )
    assert r.status_code == expect, r.text
    return r.json()


async def react(client, actor, ttype, tid, kind="like"):
    r = await client.put(
        "/reactions", headers=actor.headers, json={"target_type": ttype, "target_id": tid, "kind": kind}
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def u(make_user):
    return await make_user("Asha"), await make_user("Ben")


# ---------------------------------------------------------------- posts and scopes
async def test_create_global_post(client, u):
    a, _ = u
    p = await post(client, a, tags=["Hello", "hello", "AI"])
    assert p["scope"] == {"type": "global", "ref_id": None, "ref_label": None}
    assert p["author_name"] == "Asha" and p["author_id"] == a.id
    assert p["author"] == {"id": a.id, "name": "Asha"}  # the shape the frontend reads
    assert p["tags"] == ["hello", "ai"] and p["status"] == "active"
    assert (
        p["comment_count"] == 0 and p["recent_comments"] == [] and p["reaction_counts"] == {"like": 0, "insightful": 0}
    )
    assert p["my_reaction"] is None and p["pinned"] is False


async def test_only_authenticated_users_can_post_reads_are_public(client, u):
    a, _ = u
    assert (await client.post("/posts", json={"title": "x", "body": "y"})).status_code == 401
    p = await post(client, a)
    assert (await client.get("/posts")).status_code == 200
    got = await client.get(f"/posts/{p['id']}")
    assert got.status_code == 200 and got.json()["my_reaction"] is None
    assert (await client.get(f"/posts/{p['id']}/comments")).status_code == 200


async def test_post_validation(client, u):
    a, _ = u
    bad = [
        {"title": "", "body": "x"},
        {"title": "x", "body": ""},
        {"title": "x" * 201, "body": "x"},
        {"title": "x", "body": "x", "scope": {"type": "event"}},  # event needs ref_id
        {"title": "x", "body": "x", "scope": {"type": "global", "ref_id": "abc"}},
        {"title": "x", "body": "x", "scope": {"type": "planet", "ref_id": None}},
    ]
    for body in bad:
        assert (await client.post("/posts", headers=a.headers, json=body)).status_code == 422, body


async def test_event_and_club_scopes(client, make_club, make_doc, freeze, u):
    freeze()
    a, b = u
    club, _ = await make_club("ACM")
    unverified, _ = await make_club("Hidden Club", verified=False)
    ev = await make_doc(club, NOW + timedelta(days=3))
    draft = await make_doc(club, NOW + timedelta(days=3), status="draft")

    ep = await post(client, a, "On event", scope={"type": "event", "ref_id": str(ev["_id"])})
    cp = await post(client, a, "On club", scope={"type": "club", "ref_id": club["id"]})
    gp = await post(client, b, "Global")
    assert ep["scope"]["ref_id"] == str(ev["_id"])
    assert ep["scope"]["ref_label"] == ev["title"] and cp["scope"]["ref_label"] == "ACM"  # shown on feed cards

    # cannot post under a non-public event, an unverified club, or something that doesn't exist
    for scope in (
        {"type": "event", "ref_id": str(draft["_id"])},
        {"type": "club", "ref_id": unverified["id"]},
        {"type": "event", "ref_id": str(ObjectId())},
    ):
        r = await client.post("/posts", headers=a.headers, json={"title": "x", "body": "y", "scope": scope})
        assert r.status_code == 404, scope

    def ids(body):
        return [p["id"] for p in body["items"]]

    assert ids((await client.get("/posts")).json()) == [gp["id"], cp["id"], ep["id"]]  # newest first
    assert ids((await client.get("/posts?scope=global")).json()) == [gp["id"]]
    assert ids((await client.get(f"/posts?scope=event&ref_id={ev['_id']}")).json()) == [ep["id"]]
    assert ids((await client.get(f"/posts?scope=club&ref_id={club['id']}")).json()) == [cp["id"]]
    assert ids((await client.get("/posts?scope=club")).json()) == [cp["id"]]
    assert (await client.get("/posts?scope=nope")).status_code == 422


async def test_post_pagination_and_search(client, u):
    a, _ = u
    for i in range(5):
        await post(client, a, f"Post {i}", "plain text")
    await post(client, a, "Robotics meetup", "bring your bots")
    page = (await client.get("/posts?page_size=4&page=2")).json()
    assert page["total"] == 6 and len(page["items"]) == 2 and page["page"] == 2
    found = (await client.get("/posts?q=robotics")).json()
    assert [p["title"] for p in found["items"]] == ["Robotics meetup"] and found["total"] == 1
    body_hit = (await client.get("/posts?q=bots")).json()
    assert body_hit["total"] == 1
    assert (await client.get("/posts?page_size=51")).status_code == 422


# ---------------------------------------------------------------- comments, threading, subset
async def test_comment_updates_counters_and_recent_subset(client, u, db):
    a, b = u
    p = await post(client, a)
    for i in range(5):
        await comment(client, b, p["id"], f"comment {i}")
    got = (await client.get(f"/posts/{p['id']}")).json()
    assert got["comment_count"] == 5
    assert [c["body"] for c in got["recent_comments"]] == [
        "comment 2",
        "comment 3",
        "comment 4",
    ]  # last 3, oldest first
    assert got["recent_comments"][0]["author_name"] == "Ben"
    stored = await db.posts.find_one({"_id": ObjectId(p["id"])})
    assert len(stored["recent_comments"]) == 3 and stored["comment_count"] == 5
    assert await db.comments.count_documents({"post_id": ObjectId(p["id"])}) == 5


async def test_reply_depth_capped_at_two_levels(client, u):
    a, b = u
    p = await post(client, a)
    top = await comment(client, a, p["id"], "top")
    reply = await comment(client, b, p["id"], "reply", parent_id=top["id"])
    assert reply["parent_id"] == top["id"]
    # reply to a reply attaches to the TOP-LEVEL parent (no third level)
    deep = await comment(client, a, p["id"], "reply to reply", parent_id=reply["id"])
    assert deep["parent_id"] == top["id"]
    deeper = await comment(client, b, p["id"], "and again", parent_id=deep["id"])
    assert deeper["parent_id"] == top["id"]

    page = (await client.get(f"/posts/{p['id']}/comments")).json()
    assert page["total"] == 1  # only top-level comments are paged
    c = page["items"][0]
    assert c["id"] == top["id"] and c["reply_count"] == 3
    assert [r["body"] for r in c["replies"]] == ["reply", "reply to reply", "and again"]
    assert all(r["parent_id"] == top["id"] for r in c["replies"])
    assert (await client.get(f"/posts/{p['id']}")).json()["comment_count"] == 4


async def test_reply_limit_param_and_pagination(client, u):
    a, b = u
    p = await post(client, a)
    tops = [await comment(client, a, p["id"], f"top {i}") for i in range(3)]
    for i in range(4):
        await comment(client, b, p["id"], f"r{i}", parent_id=tops[0]["id"])
    page = (await client.get(f"/posts/{p['id']}/comments?replies=2&page_size=2")).json()
    assert page["total"] == 3 and [c["body"] for c in page["items"]] == ["top 0", "top 1"]
    first = page["items"][0]
    assert len(first["replies"]) == 2 and first["reply_count"] == 4  # limited view, true total
    none = (await client.get(f"/posts/{p['id']}/comments?replies=0")).json()["items"][0]
    assert none["replies"] == [] and none["reply_count"] == 4
    assert (await client.get(f"/posts/{p['id']}/comments?page=2&page_size=2")).json()["items"][0]["body"] == "top 2"
    assert (await client.get(f"/posts/{p['id']}/comments?replies=201")).status_code == 422


async def test_comment_errors(client, u, db):
    a, b = u
    p1, p2 = await post(client, a, "one"), await post(client, a, "two")
    c1 = await comment(client, a, p1["id"])
    # parent from another post
    assert (
        await client.post(f"/posts/{p2['id']}/comments", headers=b.headers, json={"body": "x", "parent_id": c1["id"]})
    ).status_code == 404
    assert (await client.post(f"/posts/{p1['id']}/comments", headers=b.headers, json={"body": ""})).status_code == 422
    assert (await client.post(f"/posts/{p1['id']}/comments", json={"body": "x"})).status_code == 401
    assert (
        await client.post(f"/posts/{ObjectId()}/comments", headers=b.headers, json={"body": "x"})
    ).status_code == 404
    assert (
        await client.post(f"/posts/{p1['id']}/comments", headers=b.headers, json={"body": "x", "parent_id": "nope"})
    ).status_code == 422


async def test_comment_rolls_back_on_midway_failure(client, u, db, monkeypatch):
    a, b = u
    p = await post(client, a)
    from app.services import community

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after inserting the comment")

    monkeypatch.setattr(community, "bump_post_for_comment", boom)
    with pytest.raises(RuntimeError):
        await comment(client, b, p["id"], "doomed")
    stored = await db.posts.find_one({"_id": ObjectId(p["id"])})
    assert await db.comments.count_documents({}) == 0  # the insert was rolled back
    assert stored["comment_count"] == 0 and stored["recent_comments"] == []
    monkeypatch.undo()
    await comment(client, b, p["id"], "fine")
    assert (await db.posts.find_one({"_id": ObjectId(p["id"])}))["comment_count"] == 1


async def test_concurrent_comments_keep_counter_exact(client, u, db):
    a, b = u
    p = await post(client, a)
    await asyncio.gather(*[comment(client, b, p["id"], f"c{i}") for i in range(8)])
    stored = await db.posts.find_one({"_id": ObjectId(p["id"])})
    assert stored["comment_count"] == 8 == await db.comments.count_documents({})
    assert len(stored["recent_comments"]) == 3


# ---------------------------------------------------------------- reactions
async def test_reaction_toggle_cycle_and_counters(client, u, db):
    a, b = u
    p = await post(client, a)
    r = await react(client, b, "post", p["id"], "like")
    assert r["my_reaction"] == "like" and r["reaction_counts"] == {"like": 1, "insightful": 0}
    # same kind again toggles off
    r = await react(client, b, "post", p["id"], "like")
    assert r["my_reaction"] is None and r["reaction_counts"] == {"like": 0, "insightful": 0}
    assert await db.reactions.count_documents({}) == 0
    # on, then switch kind: counters move, still exactly one reaction doc
    await react(client, b, "post", p["id"], "like")
    r = await react(client, b, "post", p["id"], "insightful")
    assert r["my_reaction"] == "insightful" and r["reaction_counts"] == {"like": 0, "insightful": 1}
    assert await db.reactions.count_documents({}) == 1
    # a second user adds to the counts
    r = await react(client, a, "post", p["id"], "like")
    assert r["reaction_counts"] == {"like": 1, "insightful": 1}


async def test_reaction_on_comment_and_my_reaction_in_reads(client, u):
    a, b = u
    p = await post(client, a)
    c = await comment(client, a, p["id"])
    rep = await comment(client, a, p["id"], "r", parent_id=c["id"])
    await react(client, b, "post", p["id"])
    await react(client, b, "comment", c["id"], "insightful")
    await react(client, b, "comment", rep["id"], "like")

    mine = (await client.get("/posts", headers=b.headers)).json()["items"][0]
    assert mine["my_reaction"] == "like" and mine["reaction_counts"]["like"] == 1
    assert (await client.get(f"/posts/{p['id']}", headers=b.headers)).json()["my_reaction"] == "like"
    assert (await client.get("/posts", headers=a.headers)).json()["items"][0]["my_reaction"] is None
    assert (await client.get("/posts")).json()["items"][0]["my_reaction"] is None  # anonymous

    top = (await client.get(f"/posts/{p['id']}/comments", headers=b.headers)).json()["items"][0]
    assert top["my_reaction"] == "insightful" and top["reaction_counts"]["insightful"] == 1
    assert top["replies"][0]["my_reaction"] == "like"
    anon = (await client.get(f"/posts/{p['id']}/comments")).json()["items"][0]
    assert anon["my_reaction"] is None and anon["reaction_counts"]["insightful"] == 1


async def test_reaction_validation_and_auth(client, u):
    a, _ = u
    p = await post(client, a)
    ok = {"target_type": "post", "target_id": p["id"], "kind": "like"}
    assert (await client.put("/reactions", json=ok)).status_code == 401
    assert (await client.put("/reactions", headers=a.headers, json={**ok, "kind": "angry"})).status_code == 422
    assert (await client.put("/reactions", headers=a.headers, json={**ok, "target_type": "event"})).status_code == 422
    assert (
        await client.put("/reactions", headers=a.headers, json={**ok, "target_id": str(ObjectId())})
    ).status_code == 404
    assert (await client.put("/reactions", headers=a.headers, json={**ok, "target_type": "comment"})).status_code == 404


async def test_reaction_rolls_back_on_failure(client, u, db, monkeypatch):
    a, b = u
    p = await post(client, a)
    from app.services import community

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after inserting the reaction")

    monkeypatch.setattr(community, "bump_reaction_counter", boom)
    with pytest.raises(RuntimeError):
        await react(client, b, "post", p["id"])
    assert await db.reactions.count_documents({}) == 0
    assert (await db.posts.find_one({"_id": ObjectId(p["id"])}))["reaction_counts"] == {"like": 0, "insightful": 0}


async def test_concurrent_toggles_by_many_users_are_consistent(client, u, make_user, db):
    a, _ = u
    p = await post(client, a)
    voters = [await make_user(f"v{i}") for i in range(6)]
    await asyncio.gather(*[react(client, v, "post", p["id"]) for v in voters])
    assert (await db.posts.find_one({"_id": ObjectId(p["id"])}))["reaction_counts"]["like"] == 6
    assert await db.reactions.count_documents({}) == 6
    await asyncio.gather(*[react(client, v, "post", p["id"]) for v in voters])  # everyone toggles off
    assert (await db.posts.find_one({"_id": ObjectId(p["id"])}))["reaction_counts"]["like"] == 0


# ---------------------------------------------------------------- removal and moderation
async def test_author_can_delete_own_only(client, u):
    a, b = u
    p = await post(client, a)
    assert (await client.delete(f"/posts/{p['id']}", headers=b.headers)).status_code == 403
    assert (await client.delete(f"/posts/{p['id']}")).status_code == 401
    assert (await client.delete(f"/posts/{p['id']}", headers=a.headers)).status_code == 204
    assert (await client.delete(f"/posts/{p['id']}", headers=a.headers)).status_code == 204  # idempotent
    assert (await client.get(f"/posts/{p['id']}")).status_code == 404
    assert (await client.get("/posts")).json()["total"] == 0
    assert (await client.get(f"/posts/{p['id']}/comments")).status_code == 404
    assert (await client.post(f"/posts/{p['id']}/comments", headers=b.headers, json={"body": "x"})).status_code == 404
    assert (await client.delete(f"/posts/{ObjectId()}", headers=a.headers)).status_code == 404


async def test_delete_comment_updates_counter_subset_and_leaves_tombstone(client, u, db):
    a, b = u
    p = await post(client, a)
    cs = [await comment(client, b, p["id"], f"c{i}") for i in range(4)]
    reply = await comment(client, a, p["id"], "reply to c3", parent_id=cs[3]["id"])
    assert (await client.get(f"/posts/{p['id']}")).json()["comment_count"] == 5
    # a stranger cannot delete; the author can
    assert (await client.delete(f"/comments/{cs[3]['id']}", headers=a.headers)).status_code == 403
    assert (await client.delete(f"/comments/{cs[3]['id']}", headers=b.headers)).status_code == 204
    assert (await client.delete(f"/comments/{cs[3]['id']}", headers=b.headers)).status_code == 204  # idempotent
    got = (await client.get(f"/posts/{p['id']}")).json()
    assert got["comment_count"] == 4  # decremented once
    # subset rebuilt from the last 3 ACTIVE comments (c3 is gone, the reply is newer)
    assert [c["body"] for c in got["recent_comments"]] == ["c1", "c2", "reply to c3"]
    thread = (await client.get(f"/posts/{p['id']}/comments")).json()["items"]
    tomb = next(c for c in thread if c["id"] == cs[3]["id"])
    assert tomb["body"] == "[removed]" and tomb["status"] == "removed" and tomb["author_name"] is None
    assert tomb["replies"][0]["body"] == "reply to c3" and tomb["reply_count"] == 1  # the thread survives
    assert reply


async def test_admin_moderation(client, u, admin, db):
    a, b = u
    p = await post(client, a)
    c = await comment(client, b, p["id"], "rude")
    # students cannot use admin endpoints
    assert (await client.post(f"/admin/comments/{c['id']}/remove", headers=a.headers)).status_code == 403
    assert (await client.post(f"/admin/posts/{p['id']}/remove", headers=b.headers)).status_code == 403
    assert (await client.post(f"/admin/comments/{c['id']}/remove")).status_code == 401
    # admin removes someone else's comment
    assert (await client.post(f"/admin/comments/{c['id']}/remove", headers=admin.headers)).status_code == 204
    stored = await db.comments.find_one({"_id": ObjectId(c["id"])})
    assert stored["status"] == "removed" and str(stored["removed_by"]) == admin.id and stored["removed_at"]
    assert (await client.get(f"/posts/{p['id']}")).json()["comment_count"] == 0
    # admin removes the post: hidden from public, still visible to admins with status
    assert (await client.post(f"/admin/posts/{p['id']}/remove", headers=admin.headers)).status_code == 204
    assert (await client.get(f"/posts/{p['id']}")).status_code == 404
    seen = await client.get(f"/posts/{p['id']}", headers=admin.headers)
    assert seen.status_code == 200 and seen.json()["status"] == "removed"
    assert (await client.post(f"/admin/posts/{ObjectId()}/remove", headers=admin.headers)).status_code == 404
    # a platform admin may also use the author-style DELETE
    p2 = await post(client, a, "second")
    assert (await client.delete(f"/posts/{p2['id']}", headers=admin.headers)).status_code == 204


async def test_cannot_react_to_removed_content(client, u):
    a, b = u
    p = await post(client, a)
    c = await comment(client, a, p["id"])
    await client.delete(f"/comments/{c['id']}", headers=a.headers)
    await client.delete(f"/posts/{p['id']}", headers=a.headers)
    assert (
        await client.put("/reactions", headers=b.headers, json={"target_type": "comment", "target_id": c["id"]})
    ).status_code == 404
    assert (
        await client.put("/reactions", headers=b.headers, json={"target_type": "post", "target_id": p["id"]})
    ).status_code == 404


async def test_removed_posts_excluded_from_search(client, u):
    a, _ = u
    p = await post(client, a, "Unique zebra topic", "zebra")
    assert (await client.get("/posts?q=zebra")).json()["total"] == 1
    await client.delete(f"/posts/{p['id']}", headers=a.headers)
    assert (await client.get("/posts?q=zebra")).json()["total"] == 0


async def test_frontend_contract_author_labels_and_full_tree(client, make_club, make_doc, freeze, u):
    freeze()
    a, b = u
    club, _ = await make_club("ACM")
    ev = await make_doc(club, NOW + timedelta(days=3), title="HackMUJ")
    p = await post(client, a, "Q", scope={"type": "event", "ref_id": str(ev["_id"])})
    top = await comment(client, a, p["id"], "top")
    for i in range(7):  # more replies than the old default preview of 3
        await comment(client, b, p["id"], f"r{i}", parent_id=top["id"])
    # feed: labels resolved in batch, author objects on posts AND on the embedded recent comments
    feed = (await client.get("/posts")).json()["items"][0]
    assert feed["scope"] == {"type": "event", "ref_id": str(ev["_id"]), "ref_label": "HackMUJ"}
    assert feed["author"] == {"id": a.id, "name": "Asha"}
    assert [c["author"]["name"] for c in feed["recent_comments"]] == ["Ben", "Ben", "Ben"]
    assert all(c["author"]["id"] == b.id for c in feed["recent_comments"])
    # thread: the whole two-level tree comes back with no query params (the adapter sends only page_size)
    thread = (await client.get(f"/posts/{p['id']}/comments?page_size=50")).json()["items"][0]
    assert (
        thread["author"] == {"id": a.id, "name": "Asha"} and len(thread["replies"]) == 7 and thread["reply_count"] == 7
    )
    assert all(r["author"]["name"] == "Ben" for r in thread["replies"])
    # a removed comment keeps its place with a placeholder author
    await client.delete(f"/comments/{top['id']}", headers=a.headers)
    gone = (await client.get(f"/posts/{p['id']}/comments")).json()["items"][0]
    assert gone["status"] == "removed" and gone["body"] == "[removed]" and gone["author"]["name"] == "Removed"
    assert len(gone["replies"]) == 7  # replies survive
