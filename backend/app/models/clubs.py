from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.validators import CATEGORIES


class ClubCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    category: str = "other"

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown category; allowed: {CATEGORIES}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{"name": "ACM SIGAI", "description": "AI/ML community at MUJ", "category": "technical"}]
        }
    }


class ClubOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    category: str
    verified: bool
    verified_at: datetime | None
    verified_by: str | None
    requested_by: str | None
    admin_ids: list[str]
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "66f0c0ffee0000000000b001",
                    "name": "ACM SIGAI",
                    "slug": "acm-sigai",
                    "description": "AI/ML community at MUJ",
                    "category": "technical",
                    "verified": True,
                    "verified_at": "2026-10-09T05:30:00Z",
                    "verified_by": "66f0c0ffee0000000000a000",
                    "requested_by": "66f0c0ffee0000000000a001",
                    "admin_ids": ["66f0c0ffee0000000000a002"],
                    "created_at": "2026-10-01T05:30:00Z",
                }
            ]
        }
    }


class AddAdminIn(BaseModel):
    user_id: str
