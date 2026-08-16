from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReplyStatus = Literal[
    "pending_approval", "approved", "ignored", "publishing", "published", "failed"
]


class GeneratedReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggested_reply: str = Field(min_length=1, max_length=2000)


class ReplyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    comment_id: int
    suggested_reply: str
    edited_reply: str | None
    status: ReplyStatus
    matched_video_id: int
    similarity: float
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    published_at: datetime | None
    youtube_reply_id: str | None


class ReplyApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str | None = Field(default=None, min_length=1, max_length=2000)
