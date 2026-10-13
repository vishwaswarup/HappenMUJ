"""Tiny in-memory sliding-window limiter for the sign-in endpoints.

Per process: fine for one API instance (our deployment). With several instances, move the counters to MongoDB
or a proxy-level limiter.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.core.errors import AppError

WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    if get_settings().trust_proxy_headers and (fwd := request.headers.get("x-forwarded-for")):
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def reset() -> None:
    _hits.clear()


async def limit_auth(request: Request) -> None:
    """FastAPI dependency: at most ``rate_limit_auth`` calls per minute per client per path."""
    limit = get_settings().rate_limit_auth
    if limit <= 0:
        return
    now = time.monotonic()
    q = _hits[f"{_client_key(request)}|{request.url.path.rstrip('/').rsplit('/', 1)[-1]}"]
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    if len(q) >= limit:
        raise AppError(429, "rate_limited", "Too many attempts. Wait a minute and try again.")
    q.append(now)
