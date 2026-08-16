from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.database.models import ProcessingStatus
from app.schemas.analysis import AnalysisRead
from app.schemas.reply import ReplyRead


class CommentVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    youtube_video_id: str
    title: str
    description: str


class MatchedVideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    youtube_video_id: str
    title: str


class MatchedChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    text: str
    start_time: float | None
    video: MatchedVideoRead


class CommentSemanticMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    match_found: bool
    similarity: float | None
    video_chunk: MatchedChunkRead | None


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    youtube_comment_id: str
    youtube_thread_id: str
    video_id: int
    author_name: str
    author_channel_id: str | None
    author_profile_image_url: str | None
    author_channel_url: str | None
    text: str
    like_count: int
    reply_count: int
    can_reply: bool
    is_public: bool
    published_at: datetime
    updated_at: datetime
    processing_status: ProcessingStatus
    pipeline_status: str = "not_started"
    pipeline_outcome: str | None = None
    pipeline_started_at: datetime | None = None
    pipeline_completed_at: datetime | None = None
    created_at: datetime
    analysis: AnalysisRead | None
    video: CommentVideoRead
    semantic_match: CommentSemanticMatchRead | None
    reply_suggestion: ReplyRead | None
