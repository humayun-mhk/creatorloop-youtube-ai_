from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommentPayload(StrictSchema):
    youtube_comment_id: str = Field(min_length=1, max_length=128)
    youtube_thread_id: str = Field(min_length=1, max_length=128)
    video_id: str = Field(min_length=1, max_length=64)
    author_name: str = Field(min_length=1, max_length=255)
    author_channel_id: str | None = Field(default=None, max_length=128)
    author_profile_image_url: str | None = None
    author_channel_url: str | None = None
    text: str = Field(min_length=1)
    like_count: int = Field(ge=0)
    reply_count: int = Field(ge=0)
    can_reply: bool
    is_public: bool
    published_at: datetime
    updated_at: datetime


class VideoPayload(StrictSchema):
    found: Literal[True]
    video_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    youtube_url: str | None = None
    thumbnail_url: str | None = None
    description: str
    tags: list[str]
    channel_id: str = Field(min_length=1, max_length=128)
    channel_title: str = Field(min_length=1, max_length=255)
    category_id: str | None = Field(default=None, max_length=32)
    default_language: str | None = Field(default=None, max_length=32)
    default_audio_language: str | None = Field(default=None, max_length=32)
    live_broadcast_content: str | None = Field(default=None, max_length=32)
    published_at: datetime | None
    duration: str | None = Field(default=None, max_length=32)
    definition: str | None = Field(default=None, max_length=16)
    caption_available: bool
    view_count: int = Field(ge=0)
    like_count: int = Field(ge=0)
    comment_count: int = Field(ge=0)


class MissingVideoPayload(StrictSchema):
    found: Literal[False]
    video_id: str = Field(min_length=1, max_length=64)


IngestVideoPayload = Annotated[VideoPayload | MissingVideoPayload, Field(discriminator="found")]


class IngestionMetadata(StrictSchema):
    fetched_at: datetime
    pipeline: str = Field(min_length=1, max_length=128)


class YouTubeCommentIngestRequest(StrictSchema):
    event_type: Literal["youtube.comment.received"]
    source: Literal["youtube"]
    monitored_channel_id: str = Field(min_length=1, max_length=128)
    comment: CommentPayload
    video: IngestVideoPayload
    ingestion: IngestionMetadata

    @model_validator(mode="after")
    def video_ids_must_match(self) -> "YouTubeCommentIngestRequest":
        if self.comment.video_id != self.video.video_id:
            raise ValueError("comment.video_id must match video.video_id")
        return self


class IngestionResponse(StrictSchema):
    status: Literal["accepted", "already_exists", "video_sync_required"]
    new_comment: bool
    comment_id: int | None = None
    processing_status: Literal["pending", "processing", "completed", "failed"] | None = None
    outcome: str | None = None
    analysis_id: int | None = None
    match_found: bool | None = None
    reply_id: int | None = None
    opportunities_rebuilt: int | None = None
    cached: bool = False
    youtube_video_id: str | None = None
