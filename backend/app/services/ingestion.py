from sqlalchemy.orm import Session

from app.repositories.ingestion import IngestionRepository, IngestionResult
from app.schemas.ingestion import YouTubeCommentIngestRequest


class IngestionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IngestionRepository(session)

    def ingest(self, payload: YouTubeCommentIngestRequest) -> IngestionResult:
        with self.session.begin():
            return self.repository.ingest(payload)
