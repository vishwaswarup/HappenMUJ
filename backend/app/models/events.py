"""Event schemas. ``details`` is a Pydantic discriminated union keyed on ``event_type``:
each event type carries different fields, yet all live in the same ``events`` collection."""

from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.common import UTCDateTime, normalize_terms
from app.validators import CATEGORIES

EventType = Literal[
    "workshop", "competition", "hackathon", "sports_match", "cultural_show", "seminar", "social", "other"
]
EventStatus = Literal["draft", "pending_review", "published", "rejected", "cancelled"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- details (per event_type)
class Speaker(Strict):
    name: str = Field(max_length=120)
    bio: str | None = Field(default=None, max_length=1000)
    affiliation: str | None = Field(default=None, max_length=200)


class Prize(Strict):
    rank: str | int
    reward: str


class Round(Strict):
    name: str
    description: str = ""


class TeamName(Strict):
    name: str


class Performance(Strict):
    title: str
    performer: str | None = None


class WorkshopDetails(Strict):
    event_type: Literal["workshop"] = "workshop"
    speaker: Speaker | None = None
    topics: list[str] = []
    duration_minutes: int | None = Field(default=None, gt=0)
    prerequisites: list[str] = []
    bring_own_laptop: bool = False


class CompetitionDetails(Strict):
    event_type: Literal["competition"] = "competition"
    prizes: list[Prize] = []
    eligibility: str | None = None
    rounds: list[Round] = []
    judging_criteria: list[str] = []


class HackathonDetails(Strict):
    event_type: Literal["hackathon"] = "hackathon"
    themes: list[str] = []
    tracks: list[str] = []
    duration_hours: int | None = Field(default=None, gt=0)
    prizes: list[Prize] = []
    max_teams: int | None = Field(default=None, gt=0)


class SportsMatchDetails(Strict):
    event_type: Literal["sports_match"] = "sports_match"
    sport: str | None = None
    match_type: str | None = None
    teams: list[TeamName] = []
    format: str | None = None


class CulturalShowDetails(Strict):
    event_type: Literal["cultural_show"] = "cultural_show"
    performances: list[Performance] = []
    artists: list[str] = []
    auditions_required: bool = False
    audition_date: UTCDateTime | None = None


class SeminarDetails(Strict):
    event_type: Literal["seminar"] = "seminar"
    speaker: Speaker | None = None
    topic: str | None = None
    q_and_a_enabled: bool = False


class SocialDetails(Strict):
    event_type: Literal["social"] = "social"
    extra: dict[str, Any] = {}


class OtherDetails(Strict):
    event_type: Literal["other"] = "other"
    extra: dict[str, Any] = {}


Details = Annotated[
    WorkshopDetails
    | CompetitionDetails
    | HackathonDetails
    | SportsMatchDetails
    | CulturalShowDetails
    | SeminarDetails
    | SocialDetails
    | OtherDetails,
    Field(discriminator="event_type"),
]


# ---------------------------------------------------------------- common embedded groups
class Schedule(Strict):
    start: UTCDateTime
    end: UTCDateTime

    @model_validator(mode="after")
    def _order(self) -> "Schedule":
        if self.end <= self.start:
            raise ValueError("schedule.end must be after schedule.start")
        return self


class Venue(Strict):
    name: str = Field(min_length=1, max_length=150)
    building: str | None = Field(default=None, max_length=50)
    room: str | None = Field(default=None, max_length=50)


class Fee(Strict):
    type: Literal["free", "fixed", "per_participant", "per_team", "not_specified"] = "not_specified"
    amount: float | None = Field(default=None, ge=0)
    currency: Literal["INR"] = "INR"

    @model_validator(mode="after")
    def _rules(self) -> "Fee":
        needs_amount = self.type in ("fixed", "per_participant", "per_team")
        if needs_amount and self.amount is None:
            raise ValueError(f"fee.amount is required when fee.type is '{self.type}'")
        if not needs_amount and self.amount is not None:
            raise ValueError(f"fee.amount must be omitted when fee.type is '{self.type}'")
        return self


class Team(Strict):
    type: Literal["individual", "range", "fixed", "not_applicable", "not_specified"] = "not_specified"
    min: int | None = Field(default=None, ge=1)
    max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _rules(self) -> "Team":
        if self.type == "range":
            if self.min is None or self.max is None:
                raise ValueError("team.min and team.max are required when team.type is 'range'")
            if self.min > self.max:
                raise ValueError("team.min cannot exceed team.max")
        elif self.type == "fixed":
            size = self.min if self.min is not None else self.max
            if size is None or (self.min is not None and self.max is not None and self.min != self.max):
                raise ValueError("team.type 'fixed' needs min == max (give one value or two equal values)")
            self.min = self.max = size
        elif self.min is not None or self.max is not None:
            raise ValueError(f"team.min/max must be omitted when team.type is '{self.type}'")
        return self


class Registration(Strict):
    required: bool = False
    platform: Literal["google_forms", "unstop", "devfolio", "website", "other"] | None = None
    url: str | None = Field(default=None, max_length=2000)
    deadline: UTCDateTime | None = None

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str | None) -> str | None:
        if v is None:
            return v
        u = urlparse(v.strip())
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError("registration.url must be an http(s) URL")
        return v.strip()

    @model_validator(mode="after")
    def _rules(self) -> "Registration":
        if self.required:
            if not self.url:
                raise ValueError("registration.url is required when registration.required is true")
            if self.platform is None:
                self.platform = "other"
        return self


class Contact(Strict):
    name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None


# ---------------------------------------------------------------- input models
EVENT_FIELDS = (
    "title", "one_liner", "description", "category", "event_type", "tags",
    "schedule", "venue", "fee", "team", "registration", "contact", "details",
)  # fmt: skip


class EventInput(Strict):
    title: str = Field(min_length=1, max_length=150)
    one_liner: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    category: str
    event_type: EventType
    tags: list[str] = Field(default=[], max_length=30)
    schedule: Schedule
    venue: Venue
    fee: Fee = Fee()
    team: Team = Team()
    registration: Registration = Registration()
    contact: Contact | None = None
    details: Details | None = None

    @model_validator(mode="before")
    @classmethod
    def _inject_discriminator(cls, data: Any) -> Any:
        """Callers send ``details`` without a type tag; it is derived from ``event_type``."""
        if isinstance(data, dict) and data.get("event_type") is not None:
            et = data["event_type"]
            det = data.get("details") or {}
            if isinstance(det, dict):
                if det.get("event_type", et) != et:
                    raise ValueError("details.event_type must match event_type")
                data = {**data, "details": {**det, "event_type": et}}
        return data

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown category; allowed: {CATEGORIES}")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return normalize_terms(v, 30)

    @model_validator(mode="after")
    def _cross(self) -> "EventInput":
        d = self.registration.deadline
        if d is not None and d > self.schedule.end:
            raise ValueError("registration.deadline cannot be after the event ends")
        return self


_EXAMPLE_WORKSHOP = {
    "club_id": "66f0c0ffee0000000000b001",
    "title": "Intro to Generative AI",
    "one_liner": "Hands-on workshop on building with LLMs.",
    "description": "Bring your laptop; we build a small RAG app in two hours.",
    "category": "technical",
    "event_type": "workshop",
    "tags": ["AI", "GenAI"],
    "schedule": {"start": "2026-10-20T14:00:00+05:30", "end": "2026-10-20T16:30:00+05:30"},
    "venue": {"name": "AB3 Seminar Hall", "building": "AB3"},
    "fee": {"type": "fixed", "amount": 199},
    "team": {"type": "individual"},
    "registration": {"required": True, "platform": "google_forms", "url": "https://forms.gle/abc",
                     "deadline": "2026-10-19T23:59:00+05:30"},
    "contact": {"name": "Riya", "email": "riya@example.com"},
    "details": {"speaker": {"name": "Dr. A. Rao", "bio": "ML researcher"}, "topics": ["LLMs", "RAG"],
                "duration_minutes": 150, "bring_own_laptop": True},
}  # fmt: skip


class EventCreate(EventInput):
    club_id: str
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_EXAMPLE_WORKSHOP]})


class EventPatch(Strict):
    """Partial update. Embedded groups (schedule, venue, fee, team, registration, contact, details)
    are replaced as a whole when present; the merged result is re-validated."""

    title: str | None = None
    one_liner: str | None = None
    description: str | None = None
    category: str | None = None
    event_type: EventType | None = None
    tags: list[str] | None = None
    schedule: Schedule | None = None
    venue: Venue | None = None
    fee: Fee | None = None
    team: Team | None = None
    registration: Registration | None = None
    contact: Contact | None = None
    details: dict[str, Any] | None = None

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"venue": {"name": "AB1 Auditorium", "building": "AB1"}}]},
    )


class CancelIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class RejectIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- output models (event card, section 6)
class ClubRef(BaseModel):
    id: str
    name: str
    slug: str


class VenueCard(BaseModel):
    name: str
    building: str | None = None


class VenueDetail(VenueCard):
    room: str | None = None


class FeeOut(BaseModel):
    type: str
    amount: float | None
    currency: str
    display: str


class TeamOut(BaseModel):
    type: str
    min: int | None
    max: int | None
    display: str


class ScheduleOut(BaseModel):
    start: datetime
    end: datetime


class RegistrationCard(BaseModel):
    required: bool
    platform: str | None
    deadline: datetime | None


class RegistrationDetail(RegistrationCard):
    url: str | None


class StatsCard(BaseModel):
    saves: int
    views: int


class StatsDetail(StatsCard):
    registration_clicks: int


class EventCard(BaseModel):
    id: str
    title: str
    one_liner: str
    club: ClubRef
    category: str
    event_type: str
    tags: list[str]
    poster_url: str | None
    schedule: ScheduleOut
    venue: VenueCard
    fee: FeeOut
    team: TeamOut
    registration: RegistrationCard
    registration_open: bool
    featured: bool
    stats: StatsCard
    is_saved: bool | None = None  # only present when the caller is authenticated


class ChangeLogEntry(BaseModel):
    at: datetime
    by: str
    fields: list[str]


class EventDetail(EventCard):
    description: str
    details: dict[str, Any]
    contact: Contact | None
    venue: VenueDetail
    registration: RegistrationDetail
    stats: StatsDetail
    status: str
    cancelled: bool
    completed: bool  # derived: end < now (never stored)
    rejection_reason: str | None
    cancel_reason: str | None
    cancelled_at: datetime | None
    creator_id: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    change_log: list[ChangeLogEntry]
