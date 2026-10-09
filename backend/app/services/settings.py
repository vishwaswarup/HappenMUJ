"""Ranking configuration lives in one document in ``settings`` so weights are editable and transparent."""

from pymongo.asynchronous.database import AsyncDatabase

from app.core import timeutil

RANKING_ID = "ranking"
DEFAULT_RANKING = {
    "weights": {"saves": 0.30, "views": 0.20, "clicks": 0.20, "proximity": 0.20, "urgency": 0.10},
    "window_days": 7,
}


async def ensure_ranking_settings(db: AsyncDatabase) -> None:
    await db.settings.update_one(
        {"_id": RANKING_ID}, {"$setOnInsert": {**DEFAULT_RANKING, "updated_at": timeutil.now()}}, upsert=True
    )


async def get_ranking_settings(db: AsyncDatabase) -> dict:
    doc = await db.settings.find_one({"_id": RANKING_ID})
    if doc is None:  # never fail a request because the settings doc is missing
        return {"_id": RANKING_ID, **DEFAULT_RANKING, "updated_at": None}
    return {**DEFAULT_RANKING, **doc, "weights": {**DEFAULT_RANKING["weights"], **doc.get("weights", {})}}
