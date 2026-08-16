from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["question", "content_request", "complaint", "feedback", "praise", "spam", "other"]
Sentiment = Literal["positive", "neutral", "negative"]


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    topic: str = Field(min_length=1, max_length=255)
    sentiment: Sentiment
    is_question: bool
    is_content_request: bool
    should_reply: bool
    reply_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)


class AnalysisRead(ClassificationResult):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    model: str
    relevance_score: float = Field(default=0, ge=0, le=100)
    priority_score: float = Field(default=0, ge=0, le=100)
