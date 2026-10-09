"""Index definitions. ``create_indexes`` is idempotent and runs at startup."""

from pymongo import ASCENDING as ASC
from pymongo import DESCENDING as DESC
from pymongo import TEXT, IndexModel
from pymongo.asynchronous.database import AsyncDatabase

EVENT_INTERACTION_TTL_SECONDS = 90 * 24 * 3600

INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("email", ASC)], unique=True, name="email_unique"),
        IndexModel([("followed_club_ids", ASC)], name="followed_clubs_multikey"),  # multikey: club follower counts
    ],
    "clubs": [
        IndexModel([("slug", ASC)], unique=True, name="slug_unique"),
        IndexModel([("admin_ids", ASC)], name="admin_ids_multikey"),  # multikey
        IndexModel([("verified", ASC)], name="verified"),
    ],
    "events": [
        IndexModel([("status", ASC), ("schedule.start", ASC)], name="status_start"),
        IndexModel([("club_id", ASC), ("schedule.start", ASC)], name="club_start"),
        IndexModel([("category", ASC), ("schedule.start", ASC)], name="category_start"),
        IndexModel([("tags", ASC)], name="tags_multikey"),  # multikey
        # Partial: only featured events are indexed, so the index stays tiny.
        IndexModel(
            [("featured.featured_at", DESC)],
            name="featured_partial",
            partialFilterExpression={"featured.is_featured": True},
        ),
        # Weighted text index: a title hit outranks a description hit.
        IndexModel(
            [
                ("title", TEXT),
                ("tags", TEXT),
                ("club_snapshot.name", TEXT),
                ("one_liner", TEXT),
                ("description", TEXT),
                ("venue.name", TEXT),
            ],
            name="events_text",
            weights={
                "title": 10,
                "tags": 6,
                "club_snapshot.name": 5,
                "one_liner": 3,
                "description": 1,
                "venue.name": 2,
            },
            default_language="english",
        ),
    ],
    "saved_events": [
        IndexModel([("user_id", ASC), ("event_id", ASC)], unique=True, name="user_event_unique"),
        IndexModel([("user_id", ASC), ("event_start", ASC)], name="user_event_start"),
    ],
    "event_interactions": [
        IndexModel([("event_id", ASC), ("type", ASC), ("ts", ASC)], name="event_type_ts"),
        # TTL: MongoDB deletes interactions older than 90 days by itself.
        IndexModel([("ts", ASC)], name="ts_ttl", expireAfterSeconds=EVENT_INTERACTION_TTL_SECONDS),
    ],
    "posts": [
        IndexModel([("scope.type", ASC), ("scope.ref_id", ASC), ("created_at", DESC)], name="scope_created"),
        IndexModel([("title", TEXT), ("body", TEXT)], name="posts_text"),
    ],
    "comments": [
        IndexModel([("post_id", ASC), ("created_at", ASC)], name="post_created"),
        IndexModel([("parent_id", ASC)], name="parent"),
    ],
    "reactions": [
        IndexModel(
            [("user_id", ASC), ("target_type", ASC), ("target_id", ASC)],
            unique=True,
            name="user_target_unique",
        ),
    ],
}


async def create_indexes(db: AsyncDatabase) -> None:
    for coll, models in INDEXES.items():
        await db[coll].create_indexes(models)
