"""MongoDB connection (PyMongo async API) and GridFS access.

The client is created once per process (``init_db``) and shared. Datetimes are
returned timezone-aware (UTC) via ``tz_aware=True``.
"""

from gridfs.asynchronous import AsyncGridFSBucket
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import get_settings

_client: AsyncMongoClient | None = None
_db: AsyncDatabase | None = None

COLLECTIONS = [
    "users",
    "clubs",
    "events",
    "saved_events",
    "event_interactions",
    "posts",
    "comments",
    "reactions",
    "settings",
]


async def init_db(uri: str | None = None, db_name: str | None = None) -> AsyncDatabase:
    global _client, _db
    s = get_settings()
    if _client is not None:
        await close_db()
    _client = AsyncMongoClient(uri or s.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    _db = _client[db_name or s.db_name]
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        await _client.close()
    _client, _db = None, None


def get_db() -> AsyncDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised; call init_db() first")
    return _db


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("Database not initialised; call init_db() first")
    return _client


def get_bucket() -> AsyncGridFSBucket:
    """GridFS bucket (``fs.files`` / ``fs.chunks``) used for event posters."""
    return AsyncGridFSBucket(get_db())
