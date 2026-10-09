from typing import Annotated, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Query
from pydantic import BaseModel

from app.core.errors import AppError
from app.validators import CATEGORIES

T = TypeVar("T")

SCHEMA_VERSION = 1  # stored as `schema_v` on every document (schema versioning pattern)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    ):
        self.page, self.page_size = page, page_size

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size


def to_oid(value: str, what: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise AppError(422, "invalid_id", f"Invalid {what}: {value!r}") from None


def normalize_terms(values: list[str], limit: int = 20) -> list[str]:
    """Lowercase, trim and de-duplicate tags/interests (case-insensitive matching)."""
    seen: dict[str, None] = {}
    for v in values:
        t = v.strip().lower()
        if t:
            seen.setdefault(t, None)
    return list(seen)[:limit]


__all__ = ["CATEGORIES", "Page", "PageParams", "SCHEMA_VERSION", "normalize_terms", "to_oid"]
