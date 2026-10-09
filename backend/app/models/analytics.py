from pydantic import BaseModel


class CountBy(BaseModel):
    key: str
    count: int


class ClubSaves(BaseModel):
    club_id: str
    name: str
    slug: str
    events: int
    saves: int
    views: int
    registration_clicks: int


class Totals(BaseModel):
    users: int
    clubs: int
    verified_clubs: int
    events: int
    saved_events: int
    posts: int


class OverviewOut(BaseModel):
    totals: Totals
    events_by_category: list[CountBy]  # published events only
    events_by_status: list[CountBy]  # every status
    top_clubs_by_saves: list[ClubSaves]


class FunnelRow(BaseModel):
    event_id: str
    title: str
    club_name: str
    views: int
    saves: int
    registration_clicks: int
    view_to_save: float
    save_to_click: float
    view_to_click: float


class FunnelTotals(BaseModel):
    views: int
    saves: int
    registration_clicks: int
    view_to_save: float
    save_to_click: float
    view_to_click: float


class EngagementOut(BaseModel):
    days: int
    totals: FunnelTotals
    items: list[FunnelRow]


class WeekdayCount(BaseModel):
    weekday: int  # ISO: 1 = Monday ... 7 = Sunday (IST)
    name: str
    count: int


class HourCount(BaseModel):
    hour: int  # 0-23 (IST)
    count: int


class HeatCell(BaseModel):
    weekday: int
    hour: int
    count: int


class BusiestOut(BaseModel):
    timezone: str
    total_events: int
    by_weekday: list[WeekdayCount]
    by_hour: list[HourCount]
    heatmap: list[HeatCell]


class TopEvent(BaseModel):
    event_id: str
    title: str
    status: str
    saves: int
    views: int
    registration_clicks: int


class ClubAnalyticsOut(BaseModel):
    club_id: str
    name: str
    followers: int
    posts: int
    events_by_status: list[CountBy]
    upcoming_published: int
    past_published: int
    views: int
    saves: int
    registration_clicks: int
    view_to_save: float
    save_to_click: float
    top_events: list[TopEvent]
