from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-production-use-32+-bytes"
_DEFAULT_ADMIN_PASSWORD = "demo1234"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    db_name: str = "happenmuj"
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_expire_minutes: int = 60 * 24
    # Comma-separated. Empty means "allow any email" (development).
    allowed_email_domains: str = ""
    platform_admin_email: str = "admin@muj-demo.edu"
    platform_admin_password: str = _DEFAULT_ADMIN_PASSWORD
    app_timezone: str = "Asia/Kolkata"
    cors_origins: str = "http://localhost:5173"
    # OAuth 2.0 "Web application" client id from Google Cloud Console. Empty = Google sign-in disabled.
    google_client_id: str = ""
    # "production" makes startup refuse placeholder secrets (see production_problems).
    app_env: str = "development"
    # Max sign-in / sign-up / Google attempts per client per minute. 0 = no limit.
    rate_limit_auth: int = 20
    # Behind a reverse proxy (Render, Railway...) the client address is in X-Forwarded-For.
    trust_proxy_headers: bool = False

    @field_validator("allowed_email_domains", "cors_origins", mode="before")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @property
    def email_domains(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.allowed_email_domains.split(",") if d.strip()]

    def production_problems(self) -> list[str]:
        """Unsafe settings; startup fails on any of them when APP_ENV=production."""
        problems = []
        if self.jwt_secret == _DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is the placeholder or shorter than 32 characters")
        if self.platform_admin_password == _DEFAULT_ADMIN_PASSWORD or len(self.platform_admin_password) < 12:
            problems.append("PLATFORM_ADMIN_PASSWORD is the demo default or shorter than 12 characters")
        if self.platform_admin_email.lower().endswith("@muj-demo.edu"):
            problems.append("PLATFORM_ADMIN_EMAIL is the demo address")
        if any("localhost" in o for o in self.cors_origin_list):
            problems.append("CORS_ORIGINS still lists localhost")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def is_local_uri(uri: str) -> bool:
    """True when every host in a MongoDB URI is this machine (and it is not an Atlas ``+srv`` URI)."""
    if uri.startswith("mongodb+srv://"):
        return False
    hosts = uri.split("://", 1)[-1].split("@")[-1].split("/")[0].split("?")[0]
    return all(h.rsplit(":", 1)[0] in ("localhost", "127.0.0.1", "[::1]") for h in hosts.split(",") if h)


@lru_cache
def get_settings() -> Settings:
    return Settings()
