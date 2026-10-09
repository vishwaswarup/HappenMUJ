"""``$jsonSchema`` collection validators.

Only the *common* fields are validated (types, required, enums). ``events.details`` is
deliberately left open: its shape depends on ``event_type`` and is checked by Pydantic.
Schema validation where we want it, flexibility where we need it.
"""

from pymongo.asynchronous.database import AsyncDatabase

CATEGORIES = [
    "technical",
    "cultural",
    "debating",
    "sports",
    "academic",
    "career",
    "hackathon",
    "workshop",
    "competition",
    "seminar",
    "social",
    "gaming",
    "other",
]
EVENT_TYPES = [
    "workshop",
    "competition",
    "hackathon",
    "sports_match",
    "cultural_show",
    "seminar",
    "social",
    "other",
]
EVENT_STATUSES = ["draft", "pending_review", "published", "rejected", "cancelled"]
ROLES = ["student", "club_admin", "platform_admin"]


def _nullable(*types: str) -> dict:
    return {"bsonType": [*types, "null"]}


VALIDATORS: dict[str, dict] = {
    "users": {
        "bsonType": "object",
        "required": ["name", "email", "password_hash", "role", "created_at"],
        "properties": {
            "name": {"bsonType": "string", "minLength": 1},
            "email": {"bsonType": "string"},
            "password_hash": {"bsonType": "string"},
            "role": {"enum": ROLES},
            "interests": {"bsonType": "array", "items": {"bsonType": "string"}},
            "preferred_categories": {"bsonType": "array", "items": {"enum": CATEGORIES}},
            "followed_club_ids": {"bsonType": "array", "items": {"bsonType": "objectId"}},
            "created_at": {"bsonType": "date"},
        },
    },
    "clubs": {
        "bsonType": "object",
        "required": ["name", "slug", "category", "verified", "admin_ids", "created_at"],
        "properties": {
            "name": {"bsonType": "string", "minLength": 1},
            "slug": {"bsonType": "string"},
            "category": {"enum": CATEGORIES},
            "verified": {"bsonType": "bool"},
            "verified_at": _nullable("date"),
            "verified_by": _nullable("objectId"),
            "requested_by": _nullable("objectId"),
            "admin_ids": {"bsonType": "array", "items": {"bsonType": "objectId"}},
            "created_at": {"bsonType": "date"},
        },
    },
    "events": {
        "bsonType": "object",
        "required": [
            "title",
            "club_id",
            "creator_id",
            "category",
            "event_type",
            "schedule",
            "status",
            "created_at",
        ],
        "properties": {
            "title": {"bsonType": "string", "minLength": 1},
            "one_liner": {"bsonType": "string", "maxLength": 160},
            "club_id": {"bsonType": "objectId"},
            "creator_id": {"bsonType": "objectId"},
            "category": {"enum": CATEGORIES},
            "event_type": {"enum": EVENT_TYPES},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "status": {"enum": EVENT_STATUSES},
            "schedule": {
                "bsonType": "object",
                "required": ["start", "end"],
                "properties": {"start": {"bsonType": "date"}, "end": {"bsonType": "date"}},
            },
            "fee": {
                "bsonType": "object",
                "properties": {"type": {"enum": ["free", "fixed", "per_participant", "per_team", "not_specified"]}},
            },
            "team": {
                "bsonType": "object",
                "properties": {"type": {"enum": ["individual", "range", "fixed", "not_applicable", "not_specified"]}},
            },
            "stats": {
                "bsonType": "object",
                "properties": {
                    "views": {"bsonType": ["int", "long"]},
                    "saves": {"bsonType": ["int", "long"]},
                    "registration_clicks": {"bsonType": ["int", "long"]},
                },
            },
            "created_at": {"bsonType": "date"},
            # "details" intentionally has no schema: it varies by event_type.
        },
    },
}


async def apply_validators(db: AsyncDatabase) -> None:
    existing = set(await db.list_collection_names())
    for name, schema in VALIDATORS.items():
        opts = {"validator": {"$jsonSchema": schema}, "validationLevel": "moderate", "validationAction": "error"}
        if name in existing:
            await db.command({"collMod": name, **opts})
        else:
            await db.create_collection(name, **opts)
