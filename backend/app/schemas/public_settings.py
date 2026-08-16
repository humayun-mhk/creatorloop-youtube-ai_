from pydantic import BaseModel


class PublicSettings(BaseModel):
    semantic_match_threshold: float
    content_brief_threshold: float
