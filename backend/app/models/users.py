from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.validators import CATEGORIES

Role = Literal["student", "club_admin", "platform_admin"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr  # any email the student owns, e.g. a personal Gmail
    password: str = Field(min_length=8, max_length=128)
    interests: list[str] = Field(default=[], max_length=50)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Aarav Sharma",
                    "email": "aarav.sharma@gmail.com",
                    "password": "s3cretpass",
                }
            ]
        }
    }


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=10, description="The Google ID token from Google Identity Services")


class AuthConfigOut(BaseModel):
    google_client_id: str | None  # null when Google sign-in is not configured


class LoginIn(BaseModel):
    email: str
    password: str

    model_config = {
        "json_schema_extra": {"examples": [{"email": "aarav@jaipur.manipal.edu", "password": "s3cretpass"}]}
    }


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: Role
    interests: list[str]
    preferred_categories: list[str]
    followed_club_ids: list[str]
    managed_club_ids: list[str] = []  # clubs whose admin_ids contain this user
    email_verified: bool = False  # true when Google vouched for the address
    auth_providers: list[str] = []  # "password" and/or "google"
    created_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "66f0c0ffee0000000000a001",
                    "name": "Aarav Sharma",
                    "email": "aarav@jaipur.manipal.edu",
                    "role": "student",
                    "interests": ["ai", "machine learning"],
                    "preferred_categories": ["technical", "hackathon"],
                    "followed_club_ids": [],
                    "created_at": "2026-10-09T05:30:00Z",
                }
            ]
        }
    }


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    interests: list[str] | None = Field(default=None, max_length=50)
    preferred_categories: list[str] | None = None

    @field_validator("preferred_categories")
    @classmethod
    def _cats(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        bad = [c for c in v if c not in CATEGORIES]
        if bad:
            raise ValueError(f"unknown categories: {bad}; allowed: {CATEGORIES}")
        return list(dict.fromkeys(v))

    model_config = {
        "json_schema_extra": {
            "examples": [{"interests": ["AI", "Robotics"], "preferred_categories": ["technical", "hackathon"]}]
        }
    }


class RoleChange(BaseModel):
    role: Role
