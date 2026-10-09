from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    db_name: str = "happenmuj"
    jwt_secret: str = "change-me-in-production-use-32+-bytes"
    jwt_expire_minutes: int = 60 * 24
    # Comma-separated. Empty means "allow any email" (development).
    allowed_email_domains: str = ""
    platform_admin_email: str = "admin@muj-demo.edu"
    platform_admin_password: str = "demo1234"
    app_timezone: str = "Asia/Kolkata"
    cors_origins: str = "http://localhost:5173"

    @field_validator("allowed_email_domains", "cors_origins", mode="before")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @property
    def email_domains(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.allowed_email_domains.split(",") if d.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
