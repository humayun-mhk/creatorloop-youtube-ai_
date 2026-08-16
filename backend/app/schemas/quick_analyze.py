from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ingestion import VideoPayload, YouTubeCommentIngestRequest
from app.schemas.processing import CommentProcessResponse


class QuickAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    youtube_video_url: str = Field(min_length=1, max_length=500)


class QuickAnalyzeStarted(BaseModel):
    id: str
    status: Literal["queued", "running"]
    youtube_video_id: str


class QuickAnalyzeVideo(BaseModel):
    id: int
    youtube_video_id: str
    youtube_url: str | None
    title: str
    channel_title: str
    thumbnail_url: str | None


class QuickAnalyzeSummary(BaseModel):
    comments_analyzed: int
    questions: int
    content_requests: int
    existing_answer_matches: int
    unanswered_requests: int


class QuickAnalyzeResult(BaseModel):
    id: str
    status: Literal["queued", "running", "complete", "failed"]
    youtube_video_url: str
    youtube_video_id: str
    video: QuickAnalyzeVideo | None
    summary: QuickAnalyzeSummary
    top_topics: list[dict]
    top_opportunities: list[dict]
    top_question_topics: list[dict]
    top_request_topics: list[dict]
    sentiment_summary: dict[str, int]
    top_matches: list[dict]
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class QuickAnalyzeCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ingestion: YouTubeCommentIngestRequest


class QuickAnalyzeVideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video: VideoPayload


class QuickAnalyzeCommentResponse(BaseModel):
    new_comment: bool
    comment_id: int
    processing: CommentProcessResponse


class QuickAnalyzeCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comments_disabled: bool = False


class QuickAnalyzeFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
