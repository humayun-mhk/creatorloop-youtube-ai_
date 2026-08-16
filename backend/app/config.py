from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CreatorLoop API"
    app_env: str = "development"
    debug: bool = Field(default=False, validation_alias="CREATORLOOP_DEBUG")

    database_url: str = Field(min_length=1)
    internal_api_key: SecretStr = Field(min_length=16)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    gemini_max_retries: int = Field(default=2, ge=0, le=8)
    gemini_retry_max_delay_seconds: float = Field(default=120.0, gt=0, le=300)

    embedding_model: str = "gemini-embedding-2"
    embedding_dimension: int = Field(default=768, ge=128, le=3072)
    embedding_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    embedding_batch_size: int = Field(default=16, ge=1, le=100)
    embedding_max_retries: int = Field(default=4, ge=0, le=8)

    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=100, ge=0, le=1000)

    semantic_match_threshold: float = Field(default=0.78, ge=0, le=1)
    semantic_search_top_k: int = Field(default=5, ge=1, le=50)

    creator_reply_style: str = (
        "Friendly, concise, helpful, and conversational"
    )
    comment_reply_policy: str = (
        "Reply when the viewer asks a useful question, requests content, "
        "reports a meaningful problem, or gives feedback that benefits from "
        "a response. Do not reply to spam, promotion, abusive noise, "
        "emoji-only comments, or generic praise that needs no answer."
    )
    reply_max_characters: int = Field(default=500, ge=50, le=2000)

    clustering_similarity_threshold: float = Field(default=0.78, ge=0, le=1)
    clustering_min_samples: int = Field(default=2, ge=1, le=100)
    demand_recency_window_days: int = Field(default=30, ge=1, le=3650)
    content_brief_threshold: float = Field(default=70.0, ge=0, le=100)
    representative_comment_limit: int = Field(default=5, ge=1, le=20)

    n8n_reply_webhook_url: str | None = None
    n8n_reply_webhook_secret: SecretStr | None = None
    n8n_reply_webhook_secret_header: str = "X-Internal-API-Key"
    n8n_reply_timeout_seconds: float = Field(default=20.0, gt=0, le=120)

    n8n_channel_sync_webhook_url: str | None = None
    n8n_channel_sync_webhook_secret: SecretStr | None = None
    n8n_channel_sync_webhook_secret_header: str = "X-Internal-API-Key"
    n8n_channel_sync_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    # n8n checks the newest 50 videos each run. The backend/database decides
    # whether each video is new, changed, already indexed, or metadata-only.
    initial_sync_video_limit: int = Field(default=50, ge=1, le=500)

    n8n_quick_analyze_webhook_url: str | None = None
    n8n_comment_monitor_secret: SecretStr | None = None
    n8n_quick_analyze_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    comment_monitor_interval_minutes: int = Field(default=15, ge=5, le=1440)

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    database_connect_timeout: int = Field(default=10, ge=1, le=60)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_must_be_smaller_than_chunk(
        cls,
        value: int,
        info: object,
    ) -> int:
        chunk_size = getattr(info, "data", {}).get("chunk_size", 800)
        if value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()