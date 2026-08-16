from datetime import datetime

from pydantic import BaseModel, ConfigDict
from app.schemas.brief import ContentBriefRead


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: int
    topic: str
    request_count: int
    unique_users: int
    total_engagement: int
    latest_request_at: datetime
    frequency_score: float
    engagement_score: float
    recency_score: float
    unique_users_score: float
    content_gap_score: float
    demand_score: float
    created_at: datetime
    updated_at: datetime
    content_brief: ContentBriefRead | None
    representative_comments: list[str]


class OpportunityRebuildResponse(BaseModel):
    status: str
    eligible_comments: int
    opportunities_created: int
