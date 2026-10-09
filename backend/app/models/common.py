from datetime import datetime
from typing import Annotated, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Query
from pydantic import AfterValidator, BaseModel

from app.core.errors import AppError
from app.core.timeutil import ensure_utc
from app.validators import CATEGORIES

T = TypeVar("T")


def _to_utc(v: datetime) -> datetime:
    """Reject naive datetimes, convert offsets to UTC, truncate to ms (BSON Date precision)."""
    v = ensure_utc(v)
    return v.replace(microsecond=(v.microsecond // 1000) * 1000)


UTCDateTime = Annotated[datetime, AfterValidator(_to_utc)]

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


class BigPageParams(PageParams):
    """For lists the UI needs in full (e.g. all saved events for the calendar): default 200, max 200."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=200)] = 200,
    ):
        super().__init__(page=page, page_size=page_size)


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


__all__ = ["UTCDateTime", "CATEGORIES", "Page", "PageParams", "SCHEMA_VERSION", "normalize_terms", "to_oid"]
