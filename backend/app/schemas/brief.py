from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GeneratedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_title: str = Field(min_length=1, max_length=500)
    hook: str = Field(min_length=1)
    audience_pain: str = Field(min_length=1)
    why_users_want: str = Field(min_length=1)
    video_outline: list[str] = Field(min_length=1, max_length=20)
    faqs: list[str] = Field(min_length=1, max_length=20)
    keywords: list[str] = Field(min_length=1, max_length=30)


class ContentBriefRead(GeneratedBrief):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: int
    representative_comments: list[str]
    model: str
    created_at: datetime
    updated_at: datetime
