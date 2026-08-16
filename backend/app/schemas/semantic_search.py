from pydantic import BaseModel


class MatchedVideo(BaseModel):
    id: int
    youtube_video_id: str
    title: str


class MatchedChunk(BaseModel):
    text: str
    start_time: float | None


class SemanticMatchResponse(BaseModel):
    match_found: bool
    similarity: float | None
    video: MatchedVideo | None
    chunk: MatchedChunk | None
