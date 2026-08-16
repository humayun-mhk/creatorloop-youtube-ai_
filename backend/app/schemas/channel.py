from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ingestion import VideoPayload

SyncStatus = Literal[
    "not_connected", "connecting", "connected", "syncing", "fetching_videos",
    "saving_videos", "indexing_videos", "fetching_comments",
    "processing_comments", "ready", "failed",
]
PartStatus = Literal["not_connected", "pending", "syncing", "ready", "failed"]


class ChannelConnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_channel: str = Field(min_length=2, max_length=500)

    @field_validator("target_channel")
    @classmethod
    def validate_public_channel(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Public YouTube channel is required")
        if "://" in normalized:
            from urllib.parse import urlparse
            parsed = urlparse(normalized)
            if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in {
                "youtube.com", "www.youtube.com", "m.youtube.com"
            }:
                raise ValueError("Only public youtube.com channel URLs are supported")
            parts = [part for part in parsed.path.split("/") if part]
            if not parts or (parts[0] == "channel" and len(parts) != 2):
                raise ValueError("Use a YouTube handle or /channel/UC... URL")
        return normalized


class ChannelIdentity(BaseModel):
    """Public channel information returned by the YouTube Data API.

    Owner-only analytics/private fields are intentionally not represented here.
    """

    model_config = ConfigDict(extra="forbid")
    youtube_channel_id: str = Field(min_length=1, max_length=128)
    channel_title: str = Field(min_length=1, max_length=255)
    channel_url: str | None = None
    custom_url: str | None = Field(default=None, max_length=255)
    thumbnail_url: str | None = None
    description: str = ""
    country: str | None = Field(default=None, max_length=16)
    default_language: str | None = Field(default=None, max_length=32)
    published_at: datetime | None = None
    uploads_playlist_id: str | None = Field(default=None, max_length=128)
    subscriber_count: int = Field(default=0, ge=0)
    hidden_subscriber_count: bool = False
    channel_view_count: int = Field(default=0, ge=0)
    public_video_count: int = Field(default=0, ge=0)
    keywords: str | None = None
    topic_categories: list[str] = Field(default_factory=list)
    privacy_status: str | None = Field(default=None, max_length=32)
    made_for_kids: bool | None = None


class ChannelRead(ChannelIdentity):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class ChannelSyncRead(BaseModel):
    status: SyncStatus
    video_sync_status: PartStatus
    comment_sync_status: PartStatus
    index_status: PartStatus
    videos_discovered: int
    videos_indexed: int
    comments_imported: int
    last_video_sync_at: datetime | None
    last_comment_sync_at: datetime | None
    last_full_sync_at: datetime | None


class CurrentChannelResponse(BaseModel):
    connected: bool
    channel: ChannelRead | None
    sync: ChannelSyncRead | None


class ChannelActionResponse(BaseModel):
    status: str
    channel_id: int


class ChannelSyncProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: SyncStatus
    video_sync_status: PartStatus | None = None
    comment_sync_status: PartStatus | None = None
    index_status: PartStatus | None = None
    videos_discovered: int | None = Field(default=None, ge=0)
    videos_indexed: int | None = Field(default=None, ge=0)
    comments_imported: int | None = Field(default=None, ge=0)


class VideoBatchImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    videos: list[VideoPayload] = Field(min_length=1, max_length=50)
    index_videos: bool = True


class VideoBatchImportResponse(BaseModel):
    status: str
    videos_received: int
    videos_discovered: int
    videos_indexed: int
    video_ids: list[int]
