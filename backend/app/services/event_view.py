"""Pure functions turning event documents into API shapes (event card / detail)."""

from datetime import datetime

from app.models.events import (
    ChangeLogEntry,
    ClubRef,
    Contact,
    EventCard,
    EventDetail,
    FeeOut,
    RegistrationCard,
    RegistrationDetail,
    ScheduleOut,
    StatsCard,
    StatsDetail,
    TeamOut,
    VenueCard,
    VenueDetail,
)


def _money(amount: float) -> str:
    return f"Rs {int(amount)}" if float(amount).is_integer() else f"Rs {amount:.2f}"


def fee_display(fee: dict) -> str:
    t, amount = fee.get("type", "not_specified"), fee.get("amount")
    if t == "free":
        return "Free"
    if t == "fixed":
        return _money(amount)
    if t == "per_participant":
        return f"{_money(amount)} per participant"
    if t == "per_team":
        return f"{_money(amount)} per team"
    return "Fee not specified"  # never "Free": unknown is not free


def team_display(team: dict) -> str:
    t, lo, hi = team.get("type", "not_specified"), team.get("min"), team.get("max")
    if t == "individual":
        return "Individual"
    if t == "range":
        return f"{lo}-{hi} members"
    if t == "fixed":
        return f"Exactly {lo} members"
    if t == "not_applicable":
        return "Not applicable"
    return "Team size not specified"


def registration_open(doc: dict, now: datetime) -> bool:
    """required AND (deadline is null OR deadline > now) AND start > now."""
    reg = doc.get("registration", {})
    deadline = reg.get("deadline")
    return bool(reg.get("required") and (deadline is None or deadline > now) and doc["schedule"]["start"] > now)


def poster_url(doc: dict) -> str | None:
    fid = doc.get("poster_file_id")
    return f"/api/v1/files/{fid}" if fid else None


def to_card(doc: dict, now: datetime, is_saved: bool | None = None) -> EventCard:
    snap = doc.get("club_snapshot", {})
    reg, stats = doc.get("registration", {}), doc.get("stats", {})
    venue, fee, team = doc.get("venue", {}), doc.get("fee", {}), doc.get("team", {})
    open_ = doc["registration_open"] if "registration_open" in doc else registration_open(doc, now)
    return EventCard(
        id=str(doc["_id"]),
        title=doc["title"],
        one_liner=doc.get("one_liner", ""),
        club=ClubRef(id=str(doc["club_id"]), name=snap.get("name", ""), slug=snap.get("slug", "")),
        category=doc["category"],
        event_type=doc["event_type"],
        tags=doc.get("tags", []),
        poster_url=poster_url(doc),
        schedule=ScheduleOut(**doc["schedule"]),
        venue=VenueCard(name=venue.get("name", ""), building=venue.get("building")),
        fee=FeeOut(
            type=fee.get("type", "not_specified"), amount=fee.get("amount"),
            currency=fee.get("currency", "INR"), display=fee_display(fee),
        ),
        team=TeamOut(
            type=team.get("type", "not_specified"), min=team.get("min"), max=team.get("max"),
            display=team_display(team),
        ),
        registration=RegistrationCard(
            required=reg.get("required", False), platform=reg.get("platform"), deadline=reg.get("deadline")
        ),
        registration_open=open_,
        featured=bool(doc.get("featured", {}).get("is_featured")),
        stats=StatsCard(saves=stats.get("saves", 0), views=stats.get("views", 0)),
        is_saved=is_saved,
    )  # fmt: skip


def to_detail(doc: dict, now: datetime, is_saved: bool | None = None) -> EventDetail:
    card = to_card(doc, now, is_saved)
    reg, stats, venue = doc.get("registration", {}), doc.get("stats", {}), doc.get("venue", {})
    return EventDetail(
        **card.model_dump(exclude={"venue", "registration", "stats"}),
        venue=VenueDetail(name=venue.get("name", ""), building=venue.get("building"), room=venue.get("room")),
        registration=RegistrationDetail(**card.registration.model_dump(), url=reg.get("url")),
        stats=StatsDetail(**card.stats.model_dump(), registration_clicks=stats.get("registration_clicks", 0)),
        description=doc.get("description", ""),
        details=doc.get("details", {}),
        contact=Contact(**doc["contact"]) if doc.get("contact") else None,
        status=doc["status"],
        cancelled=doc["status"] == "cancelled",
        completed=doc["schedule"]["end"] < now,
        rejection_reason=doc.get("rejection_reason"),
        cancel_reason=doc.get("cancel_reason"),
        cancelled_at=doc.get("cancelled_at"),
        creator_id=str(doc["creator_id"]),
        published_at=doc.get("published_at"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at", doc["created_at"]),
        change_log=[ChangeLogEntry(at=c["at"], by=str(c["by"]), fields=c["fields"]) for c in doc.get("change_log", [])],
    )
