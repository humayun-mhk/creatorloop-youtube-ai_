from typing import Literal

from pydantic import BaseModel


class CommentProcessResponse(BaseModel):
    comment_id: int
    status: Literal["processing", "completed"]
    outcome: str | None
    analysis_id: int | None = None
    match_found: bool | None = None
    reply_id: int | None = None
    opportunities_rebuilt: int | None = None
    cached: bool = False
