from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FEEDSTUDIO_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./data/feedstudio.db"
    storage_dir: Path = Path("./data/storage")
    job_backend: str = Field(default="thread", description="'thread' (in-process) or 'rq' (Redis workers)")
    redis_url: str = "redis://localhost:6379/0"
    public_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:5173"]
    api_token: str | None = Field(default=None, description="If set, /api requires 'Authorization: Bearer <token>'")

    max_feed_mb: int = 200
    max_upload_mb: int = 200
    max_items: int = 1_000_000
    fetch_timeout_seconds: float = 60.0
    allow_http_sources: bool = False
    allow_private_networks: bool = False
    snapshot_retention: int = 5
    preview_max_scan: int = 200_000
    publish_drop_threshold: float = Field(default=0.5, description="Block publication if items drop more than this ratio")


@lru_cache
def get_settings() -> Settings:
    return Settings()
