from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.events import EventCard

SavedStatus = Literal["saved", "registration_initiated"]


class SaveIn(BaseModel):
    event_id: str

    model_config = ConfigDict(json_schema_extra={"examples": [{"event_id": "66f0c0ffee0000000000c001"}]})


class SavedRecord(BaseModel):
    id: str
    event_id: str
    status: SavedStatus
    event_start: datetime
    created_at: datetime


class SavedEventOut(BaseModel):
    id: str
    status: SavedStatus
    saved_at: datetime
    cancelled: bool  # a saved event that was later cancelled stays in the list, flagged
    event: EventCard


class CalendarDay(BaseModel):
    date: str  # YYYY-MM-DD in the app timezone (IST)
    items: list[SavedEventOut]


class CalendarOut(BaseModel):
    year: int
    month: int
    timezone: str
    days: list[CalendarDay]


class ViewOut(BaseModel):
    recorded: bool  # false when deduplicated (same user, same event, within 30 minutes)


class RegistrationClickOut(BaseModel):
    url: str
    platform: str | None = None
