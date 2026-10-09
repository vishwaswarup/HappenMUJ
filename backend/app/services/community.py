"""Community: one mechanism, three scopes (global feed, event discussion, club space).

Patterns on show: extended reference (author_snapshot), subset (recent_comments, last 3), computed
(comment_count, reaction_counts). Multi-document writes run in transactions.
"""

from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app import db as db_module
from app.core import timeutil
from app.core.errors import AppError, forbidden, not_found
from app.models.common import SCHEMA_VERSION, to_oid
from app.models.community import (
    Author,
    CommentCreate,
    CommentOut,
    CommentSnapshot,
    PostCreate,
    PostOut,
    PostScope,
    PostScopeOut,
    ReactionOut,
    ReplyOut,
)
from app.services.visibility import public_filter

REMOVED_TEXT = "[removed]"
RECENT = 3
SNAPSHOT_BODY_CHARS = 200
KINDS = ("like", "insightful")


def _zero_counts() -> dict[str, int]:
    return {k: 0 for k in KINDS}


# ------------------------------------------------------------------ posts
async def _check_scope(db: AsyncDatabase, scope: PostScope) -> ObjectId | None:
    if scope.type == "global":
        return None
    ref = to_oid(scope.ref_id or "", "scope.ref_id")
    if scope.type == "event":
        ok = await db.events.count_documents(public_filter(_id=ref), limit=1)
    else:
        ok = await db.clubs.count_documents({"_id": ref, "verified": True}, limit=1)
    if not ok:
        raise not_found("Event" if scope.type == "event" else "Club")
    return ref


async def create_post(db: AsyncDatabase, user: dict, data: PostCreate) -> dict:
    ref = await _check_scope(db, data.scope)
    now = timeutil.now()
    doc = {
        "scope": {"type": data.scope.type, "ref_id": ref},
        "author_id": user["_id"],
        "author_snapshot": {"name": user["name"]},  # extended reference: no $lookup to render a feed
        "title": data.title.strip(),
        "body": data.body.strip(),
        "tags": data.tags,
        "comment_count": 0,
        "reaction_counts": _zero_counts(),
        "recent_comments": [],
        "pinned": False,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "schema_v": SCHEMA_VERSION,
    }
    doc["_id"] = (await db.posts.insert_one(doc)).inserted_id
    return doc


async def get_post(db: AsyncDatabase, post_id: ObjectId, user: dict | None) -> dict:
    post = await db.posts.find_one({"_id": post_id})
    if not post or (post["status"] != "active" and not (user and user["role"] == "platform_admin")):
        raise not_found("Post")
    return post


async def list_posts(
    db: AsyncDatabase, *, scope: str | None, ref_id: str | None, q: str | None, skip: int, limit: int
) -> tuple[list[dict], int]:
    flt: dict[str, Any] = {"status": "active"}
    if scope:
        flt["scope.type"] = scope
    if ref_id:
        flt["scope.ref_id"] = to_oid(ref_id, "ref_id")
    if q:
        flt["$text"] = {"$search": q}
    total = await db.posts.count_documents(flt)
    if q:
        cursor = db.posts.find(flt, {"_score": {"$meta": "textScore"}}).sort(
            [("_score", {"$meta": "textScore"}), ("created_at", -1), ("_id", -1)]
        )
    else:
        cursor = db.posts.find(flt).sort([("pinned", -1), ("created_at", -1), ("_id", -1)])
    return await cursor.skip(skip).limit(limit).to_list(limit), total


# ------------------------------------------------------------------ comments
def _snapshot(c: dict) -> dict:
    return {
        "id": c["_id"],
        "author_id": c["author_id"],
        "author_name": c["author_snapshot"]["name"],
        "body": c["body"][:SNAPSHOT_BODY_CHARS],
        "parent_id": c["parent_id"],
        "created_at": c["created_at"],
    }


# Transaction steps: module-level so tests can force a failure part-way through.
async def insert_comment(db: AsyncDatabase, session, comment: dict) -> None:
    await db.comments.insert_one(comment, session=session)


async def bump_post_for_comment(db: AsyncDatabase, session, post_id: ObjectId, snapshot: dict) -> None:
    await db.posts.update_one(
        {"_id": post_id},
        {
            "$inc": {"comment_count": 1},
            # Subset pattern: keep only the latest 3 comment snapshots on the post.
            "$push": {"recent_comments": {"$each": [snapshot], "$slice": -RECENT}},
        },
        session=session,
    )


async def create_comment(db: AsyncDatabase, user: dict, post_id: ObjectId, data: CommentCreate) -> dict:
    post = await db.posts.find_one({"_id": post_id, "status": "active"}, {"_id": 1})
    if not post:
        raise not_found("Post")
    parent_id = None
    if data.parent_id:
        parent = await db.comments.find_one(
            {"_id": to_oid(data.parent_id, "parent_id"), "post_id": post_id, "status": "active"}
        )
        if not parent:
            raise not_found("Parent comment")
        # Threading is capped at 2 levels: a reply to a reply attaches to the top-level parent.
        parent_id = parent["parent_id"] or parent["_id"]
    comment = {
        "_id": ObjectId(),
        "post_id": post_id,
        "parent_id": parent_id,
        "author_id": user["_id"],
        "author_snapshot": {"name": user["name"]},
        "body": data.body.strip(),
        "reaction_counts": _zero_counts(),
        "status": "active",
        "created_at": timeutil.now(),
        "schema_v": SCHEMA_VERSION,
    }

    async def write(session):
        await insert_comment(db, session, comment)
        await bump_post_for_comment(db, session, post_id, _snapshot(comment))

    await db_module.run_txn(write)
    return comment


async def list_comments(
    db: AsyncDatabase, post_id: ObjectId, *, skip: int, limit: int, replies: int
) -> tuple[list[dict], int]:
    total = await db.comments.count_documents({"post_id": post_id, "parent_id": None})
    return await (await db.comments.aggregate(comments_pipeline(post_id, skip, limit, replies))).to_list(limit), total


def comments_pipeline(post_id: ObjectId, skip: int, limit: int, replies: int) -> list[dict]:
    """Top-level comments of a post, each with up to `replies` replies and the true reply count."""
    return [
        {"$match": {"post_id": post_id, "parent_id": None}},
        {"$sort": {"created_at": 1, "_id": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "comments",
                "localField": "_id",
                "foreignField": "parent_id",
                # $limit must be positive, so replies=0 means "no reply preview" -> match nothing
                "pipeline": [{"$sort": {"created_at": 1, "_id": 1}}, {"$limit": replies}]
                if replies
                else [{"$match": {"_id": None}}],
                "as": "replies",
            }
        },
        {
            "$lookup": {
                "from": "comments",
                "localField": "_id",
                "foreignField": "parent_id",
                "pipeline": [{"$match": {"status": "active"}}, {"$count": "n"}],
                "as": "reply_total",
            }
        },
    ]


async def refresh_recent_comments(db: AsyncDatabase, session, post_id: ObjectId) -> None:
    """Rebuild the embedded subset after a removal (the maintenance cost of the subset pattern)."""
    last = await (
        db.comments.find({"post_id": post_id, "status": "active"}, session=session)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(RECENT)
        .to_list(RECENT)
    )
    await db.posts.update_one(
        {"_id": post_id}, {"$set": {"recent_comments": [_snapshot(c) for c in reversed(last)]}}, session=session
    )


# ------------------------------------------------------------------ removal (soft delete)
async def remove_post(db: AsyncDatabase, actor: dict, post_id: ObjectId, *, admin_override: bool = False) -> None:
    post = await db.posts.find_one({"_id": post_id})
    if not post:
        raise not_found("Post")
    _authorize_removal(actor, post, admin_override)
    await db.posts.update_one(
        {"_id": post_id, "status": "active"},
        {"$set": {"status": "removed", "removed_by": actor["_id"], "removed_at": timeutil.now()}},
    )


async def remove_comment(db: AsyncDatabase, actor: dict, comment_id: ObjectId, *, admin_override: bool = False) -> None:
    comment = await db.comments.find_one({"_id": comment_id})
    if not comment:
        raise not_found("Comment")
    _authorize_removal(actor, comment, admin_override)

    async def write(session):
        res = await db.comments.update_one(
            {"_id": comment_id, "status": "active"},
            {"$set": {"status": "removed", "removed_by": actor["_id"], "removed_at": timeutil.now()}},
            session=session,
        )
        if res.modified_count:  # idempotent: removing twice changes nothing
            await db.posts.update_one(
                {"_id": comment["post_id"], "comment_count": {"$gt": 0}},
                {"$inc": {"comment_count": -1}},
                session=session,
            )
            await refresh_recent_comments(db, session, comment["post_id"])

    await db_module.run_txn(write)


def _authorize_removal(actor: dict, doc: dict, admin_override: bool) -> None:
    is_admin = actor["role"] == "platform_admin"
    if admin_override and not is_admin:
        raise forbidden()
    if not (is_admin or doc["author_id"] == actor["_id"]):
        raise forbidden("Only the author or a platform admin can remove this")


# ------------------------------------------------------------------ reactions
async def bump_reaction_counter(
    db: AsyncDatabase, session, target_type: str, target_id: ObjectId, kind: str, delta: int
) -> None:
    coll = db.posts if target_type == "post" else db.comments
    flt: dict[str, Any] = {"_id": target_id}
    if delta < 0:
        flt[f"reaction_counts.{kind}"] = {"$gt": 0}  # counters never go negative
    await coll.update_one(flt, {"$inc": {f"reaction_counts.{kind}": delta}}, session=session)


async def toggle_reaction(
    db: AsyncDatabase, user: dict, target_type: str, target_id: ObjectId, kind: str
) -> ReactionOut:
    """Same kind again = remove; different kind = switch; none = add. One reaction per user per target."""
    coll = db.posts if target_type == "post" else db.comments
    if not await coll.find_one({"_id": target_id, "status": "active"}, {"_id": 1}):
        raise not_found("Post" if target_type == "post" else "Comment")
    key = {"user_id": user["_id"], "target_type": target_type, "target_id": target_id}

    async def write(session):
        existing = await db.reactions.find_one(key, session=session)
        if existing is None:
            await db.reactions.insert_one(
                {**key, "kind": kind, "created_at": timeutil.now(), "schema_v": SCHEMA_VERSION}, session=session
            )
            await bump_reaction_counter(db, session, target_type, target_id, kind, +1)
            mine: str | None = kind
        elif existing["kind"] == kind:
            await db.reactions.delete_one({"_id": existing["_id"]}, session=session)
            await bump_reaction_counter(db, session, target_type, target_id, kind, -1)
            mine = None
        else:
            await db.reactions.update_one({"_id": existing["_id"]}, {"$set": {"kind": kind}}, session=session)
            await bump_reaction_counter(db, session, target_type, target_id, existing["kind"], -1)
            await bump_reaction_counter(db, session, target_type, target_id, kind, +1)
            mine = kind
        target = await coll.find_one({"_id": target_id}, {"reaction_counts": 1}, session=session)
        return mine, target["reaction_counts"]

    try:
        mine, counts = await db_module.run_txn(write)
    except DuplicateKeyError:  # concurrent first-time reaction by the same user: the unique index decided
        raise AppError(409, "conflict", "Reaction was changed concurrently; retry") from None
    return ReactionOut(target_type=target_type, target_id=str(target_id), my_reaction=mine, reaction_counts=counts)


async def my_reactions(
    db: AsyncDatabase, user: dict | None, target_type: str, ids: list[ObjectId]
) -> dict[ObjectId, str]:
    if user is None or not ids:
        return {}
    rows = await db.reactions.find(
        {"user_id": user["_id"], "target_type": target_type, "target_id": {"$in": ids}}, {"target_id": 1, "kind": 1}
    ).to_list(None)
    return {r["target_id"]: r["kind"] for r in rows}


# ------------------------------------------------------------------ serialisation
def post_out(p: dict, mine: str | None, labels: dict[ObjectId, str] | None = None) -> PostOut:
    ref = p["scope"]["ref_id"]
    return PostOut(
        id=str(p["_id"]),
        scope=PostScopeOut(
            type=p["scope"]["type"],
            ref_id=str(ref) if ref else None,
            ref_label=(labels or {}).get(ref) if ref else None,
        ),
        author=Author(id=str(p["author_id"]), name=p["author_snapshot"]["name"]),
        author_id=str(p["author_id"]),
        author_name=p["author_snapshot"]["name"],
        title=p["title"], body=p["body"], tags=p.get("tags", []),
        comment_count=p["comment_count"], reaction_counts=p["reaction_counts"],
        recent_comments=[
            CommentSnapshot(
                id=str(c["id"]),
                author=Author(id=str(c.get("author_id", "")), name=c["author_name"]),
                author_name=c["author_name"], body=c["body"],
                parent_id=str(c["parent_id"]) if c["parent_id"] else None, created_at=c["created_at"],
            )
            for c in p.get("recent_comments", [])
        ],
        pinned=p["pinned"], status=p["status"], my_reaction=mine,
        created_at=p["created_at"], updated_at=p["updated_at"],
    )  # fmt: skip


def reply_out(c: dict, mine: str | None) -> ReplyOut:
    removed = c["status"] == "removed"
    return ReplyOut(
        id=str(c["_id"]), post_id=str(c["post_id"]),
        parent_id=str(c["parent_id"]) if c["parent_id"] else None,
        author=(
            Author(id="", name="Removed")
            if removed
            else Author(id=str(c["author_id"]), name=c["author_snapshot"]["name"])
        ),
        author_id=None if removed else str(c["author_id"]),
        author_name=None if removed else c["author_snapshot"]["name"],
        body=REMOVED_TEXT if removed else c["body"], status=c["status"],
        reaction_counts=c["reaction_counts"], my_reaction=mine, created_at=c["created_at"],
    )  # fmt: skip


def comment_out(c: dict, reaction_map: dict[ObjectId, str]) -> CommentOut:
    replies = c.get("replies", [])
    base = reply_out(c, reaction_map.get(c["_id"]))
    total = c["reply_total"][0]["n"] if c.get("reply_total") else 0
    return CommentOut(
        **base.model_dump(), reply_count=total, replies=[reply_out(r, reaction_map.get(r["_id"])) for r in replies]
    )


async def comments_out(db: AsyncDatabase, user: dict | None, rows: list[dict]) -> list[CommentOut]:
    ids = [r["_id"] for r in rows] + [rep["_id"] for r in rows for rep in r.get("replies", [])]
    rmap = await my_reactions(db, user, "comment", ids)
    return [comment_out(r, rmap) for r in rows]


async def scope_labels(db: AsyncDatabase, posts: list[dict]) -> dict[ObjectId, str]:
    """Event titles / club names for the posts' scopes, two queries total (not one per post)."""
    events = {p["scope"]["ref_id"] for p in posts if p["scope"]["type"] == "event" and p["scope"]["ref_id"]}
    clubs = {p["scope"]["ref_id"] for p in posts if p["scope"]["type"] == "club" and p["scope"]["ref_id"]}
    labels: dict[ObjectId, str] = {}
    if events:
        async for e in db.events.find({"_id": {"$in": list(events)}}, {"title": 1}):
            labels[e["_id"]] = e["title"]
    if clubs:
        async for c in db.clubs.find({"_id": {"$in": list(clubs)}}, {"name": 1}):
            labels[c["_id"]] = c["name"]
    return labels


async def posts_out(db: AsyncDatabase, user: dict | None, posts: list[dict]) -> list[PostOut]:
    rmap = await my_reactions(db, user, "post", [p["_id"] for p in posts])
    labels = await scope_labels(db, posts)
    return [post_out(p, rmap.get(p["_id"]), labels) for p in posts]
