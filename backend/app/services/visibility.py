"""The ONE definition of 'publicly visible'. Every public endpoint must build on this filter."""

from typing import Any


def public_filter(**extra: Any) -> dict[str, Any]:
    """Published and not cancelled. Draft, pending_review, rejected and cancelled never show publicly."""
    return {"status": "published", "cancelled_at": None, **extra}
