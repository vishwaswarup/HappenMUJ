from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, CurrentUser, OptionalUser
from app.core.errors import ErrorResponse
from app.models.common import Page, PageParams, to_oid
from app.models.community import (
    CommentCreate,
    CommentOut,
    PostCreate,
    PostOut,
    ReactionIn,
    ReactionOut,
    ReplyOut,
)
from app.services import community as svc

router = APIRouter(tags=["community"])
_errors = {401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.post(
    "/posts",
    response_model=PostOut,
    status_code=201,
    responses=_errors,
    summary="Create a post (global, event or club scope)",
)
async def create_post(data: PostCreate, db: DB, user: CurrentUser) -> PostOut:
    return (await svc.posts_out(db, user, [await svc.create_post(db, user, data)]))[0]


@router.get("/posts", response_model=Page[PostOut], summary="Feed. Public; includes my_reaction when authenticated")
async def list_posts(
    db: DB, user: OptionalUser, pp: Annotated[PageParams, Depends()],
    scope: Literal["global", "event", "club"] | None = None,
    ref_id: Annotated[str | None, Query(description="Event or club id when scope is event/club")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> Page[PostOut]:  # fmt: skip
    posts, total = await svc.list_posts(db, scope=scope, ref_id=ref_id, q=q, skip=pp.skip, limit=pp.page_size)
    return Page(items=await svc.posts_out(db, user, posts), total=total, page=pp.page, page_size=pp.page_size)


@router.get(
    "/posts/{post_id}",
    response_model=PostOut,
    responses={404: {"model": ErrorResponse}},
    summary="One post with its last 3 comments (removed posts: platform admins only)",
)
async def get_post(post_id: str, db: DB, user: OptionalUser) -> PostOut:
    post = await svc.get_post(db, to_oid(post_id, "post id"), user)
    return (await svc.posts_out(db, user, [post]))[0]


@router.delete("/posts/{post_id}", status_code=204, responses=_errors, summary="Remove my post (soft delete)")
async def delete_post(post_id: str, db: DB, user: CurrentUser) -> None:
    await svc.remove_post(db, user, to_oid(post_id, "post id"))


@router.post(
    "/posts/{post_id}/comments",
    response_model=ReplyOut,
    status_code=201,
    responses=_errors,
    summary="Comment or reply (transaction: insert + comment_count + recent_comments). Depth capped at 2",
)
async def create_comment(post_id: str, data: CommentCreate, db: DB, user: CurrentUser) -> ReplyOut:
    c = await svc.create_comment(db, user, to_oid(post_id, "post id"), data)
    return svc.reply_out(c, None)


@router.get(
    "/posts/{post_id}/comments",
    response_model=Page[CommentOut],
    responses={404: {"model": ErrorResponse}},
    summary="Top-level comments, each with up to N replies (2-level threading)",
)
async def list_comments(
    post_id: str, db: DB, user: OptionalUser, pp: Annotated[PageParams, Depends()],
    replies: Annotated[int, Query(ge=0, le=20, description="Max replies returned per top-level comment")] = 3,
) -> Page[CommentOut]:  # fmt: skip
    pid = to_oid(post_id, "post id")
    await svc.get_post(db, pid, user)
    rows, total = await svc.list_comments(db, pid, skip=pp.skip, limit=pp.page_size, replies=replies)
    return Page(items=await svc.comments_out(db, user, rows), total=total, page=pp.page, page_size=pp.page_size)


@router.delete("/comments/{comment_id}", status_code=204, responses=_errors, summary="Remove my comment (soft delete)")
async def delete_comment(comment_id: str, db: DB, user: CurrentUser) -> None:
    await svc.remove_comment(db, user, to_oid(comment_id, "comment id"))


@router.put(
    "/reactions",
    response_model=ReactionOut,
    responses=_errors,
    summary="Toggle a reaction: same kind removes it, a different kind switches it (counters updated in a transaction)",
)
async def react(data: ReactionIn, db: DB, user: CurrentUser) -> ReactionOut:
    return await svc.toggle_reaction(db, user, data.target_type, to_oid(data.target_id, "target id"), data.kind)
