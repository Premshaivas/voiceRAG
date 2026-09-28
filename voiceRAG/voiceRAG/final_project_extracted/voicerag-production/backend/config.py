from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./data/voicerag.db"
    assemblyai_api_key: str | None = None
    assemblyai_speech_model: str = "universal-3-5-pro"
    llm_gateway_model: str = "claude-sonnet-4-5-20250929"
    llm_gateway_url: str = "https://llm-gateway.assemblyai.com/v1/chat/completions"
    vector_backend: str = "chroma"
    chroma_dir: str = "./data/chroma"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "voice_transcripts"
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 500
    max_audio_duration_seconds: int = 14_400
    cors_origins: str = "http://localhost:5173"
    auth_required: bool = False
    admin_email: str | None = None
    jwt_expire_minutes: int = 15
    refresh_cookie_name: str = "__Host-voicerag-refresh"
    refresh_days: int = 30
    csrf_header_name: str = "X-CSRF-Token"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "voicerag"
    s3_access_key: str | None = "minio"
    s3_secret_key: str | None = "miniosecret"
    s3_presign_seconds: int = 900
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    rate_limit_per_minute: int = 60
    answer_cache_ttl_seconds: int = 60
    answer_cache_max_entries: int = 512
    query_embedding_cache_max_entries: int = 1024
    evaluation_concurrency: int = 4
    retrieval_max_distance: float = 0.72
    min_citation_coverage: float = 0.75

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def ensure_directories(self) -> None:
        Path(self.chroma_dir).mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite"):
            Path(self.database_url.rsplit("/", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
