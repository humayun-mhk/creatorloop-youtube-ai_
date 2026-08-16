from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)

    @model_validator(mode="after")
    def end_after_start(self) -> "TranscriptSegment":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self


class VideoIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: list[TranscriptSegment] | None = None


class VideoIndexResponse(BaseModel):
    video_id: int
    indexed: bool
    chunk_count: int
    embedding_model: str
    embedding_dimension: int


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_video_id: str
    channel_id: str
    channel_title: str
    title: str
    youtube_url: str | None = None
    thumbnail_url: str | None = None
    description: str
    tags: list[str]
    published_at: datetime | None
    duration: str | None
    definition: str | None
    caption_available: bool
    view_count: int
    like_count: int
    comment_count: int
    created_at: datetime
    updated_at: datetime
    index_status: str
    indexed_chunk_count: int
