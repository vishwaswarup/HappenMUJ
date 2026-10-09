from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.common import normalize_terms

ScopeType = Literal["global", "event", "club"]
ReactionKind = Literal["like", "insightful"]
TargetType = Literal["post", "comment"]
Status = Literal["active", "removed"]


class PostScope(BaseModel):
    type: ScopeType = "global"
    ref_id: str | None = None

    @model_validator(mode="after")
    def _ref(self) -> "PostScope":
        if self.type == "global" and self.ref_id is not None:
            raise ValueError("ref_id must be omitted for global posts")
        if self.type != "global" and not self.ref_id:
            raise ValueError(f"ref_id is required for {self.type} posts")
        return self


class PostCreate(BaseModel):
    scope: PostScope = PostScope()
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    tags: list[str] = Field(default=[], max_length=20)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return normalize_terms(v, 20)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "scope": {"type": "event", "ref_id": "66f0c0ffee0000000000c001"},
                    "title": "Anyone going to the hackathon?",
                    "body": "Looking for a teammate who knows React.",
                    "tags": ["hackathon", "teamup"],
                }
            ]
        }
    )


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: str | None = None

    model_config = ConfigDict(json_schema_extra={"examples": [{"body": "Count me in!", "parent_id": None}]})


class ReactionIn(BaseModel):
    target_type: TargetType
    target_id: str
    kind: ReactionKind = "like"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"target_type": "post", "target_id": "66f0c0ffee0000000000d001", "kind": "like"}]
        }
    )


class ReactionOut(BaseModel):
    target_type: TargetType
    target_id: str
    my_reaction: ReactionKind | None  # null after toggling off
    reaction_counts: dict[str, int]


class Author(BaseModel):
    id: str
    name: str


class PostScopeOut(BaseModel):
    type: ScopeType
    ref_id: str | None
    ref_label: str | None = None  # the event title or club name, so a feed card can say where the post lives


class CommentSnapshot(BaseModel):
    """Subset pattern: the last 3 comments embedded in the post so the feed needs no second query."""

    id: str
    author: Author
    author_name: str
    body: str
    parent_id: str | None
    created_at: datetime


class PostOut(BaseModel):
    id: str
    scope: PostScopeOut
    author: Author
    author_id: str
    author_name: str
    title: str
    body: str
    tags: list[str]
    comment_count: int
    reaction_counts: dict[str, int]
    recent_comments: list[CommentSnapshot]
    pinned: bool
    status: Status
    my_reaction: ReactionKind | None = None  # only when authenticated
    created_at: datetime
    updated_at: datetime


class ReplyOut(BaseModel):
    id: str
    post_id: str
    parent_id: str | None
    author: Author  # a placeholder author for removed comments
    author_id: str | None  # null for removed comments
    author_name: str | None
    body: str  # "[removed]" for removed comments, so threads keep their shape
    status: Status
    reaction_counts: dict[str, int]
    my_reaction: ReactionKind | None = None
    created_at: datetime


class CommentOut(ReplyOut):
    reply_count: int
    replies: list[ReplyOut]
