from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import Comment, SemanticMatch, Video, VideoChunk
from app.services.embeddings import EmbeddingService


class CommentNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SemanticCandidate:
    chunk_id: int
    video_id: int
    youtube_video_id: str
    video_title: str
    text: str
    start_time: float | None
    similarity: float


@dataclass(frozen=True)
class SemanticSearchResult:
    match_found: bool
    candidates: list[SemanticCandidate]
    cached: bool = False

    @property
    def best(self) -> SemanticCandidate | None:
        return self.candidates[0] if self.candidates else None


def evaluate_candidates(
    candidates: list[SemanticCandidate], threshold: float, cached: bool = False
) -> SemanticSearchResult:
    match_found = bool(candidates and candidates[0].similarity >= threshold)
    return SemanticSearchResult(match_found=match_found, candidates=candidates, cached=cached)


class SemanticSearchService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.embedder = embedder

    def match_comment(
        self, comment_id: int, knowledge_channel_id: int | None = None
    ) -> SemanticSearchResult:
        with self.session.begin():
            comment = self.session.execute(
                select(Comment)
                .options(selectinload(Comment.analysis), selectinload(Comment.semantic_match))
                .where(Comment.id == comment_id)
            ).scalar_one_or_none()
            if comment is None:
                raise CommentNotFoundError
            if comment.semantic_match is not None:
                candidates = [SemanticCandidate(**item) for item in comment.semantic_match.candidates]
                return evaluate_candidates(candidates, comment.semantic_match.threshold, cached=True)
            query_text = self._query_text(comment)
            scope_channel_id = knowledge_channel_id or comment.knowledge_channel_id

        embedder = self.embedder or EmbeddingService(self.settings)
        query_embedding = embedder.embed_query(query_text)

        with self.session.begin():
            similarity = (1 - VideoChunk.embedding.cosine_distance(query_embedding)).label("similarity")
            query = (
                select(VideoChunk, Video, similarity)
                .join(Video, Video.id == VideoChunk.video_id)
                .order_by(similarity.desc())
                .limit(self.settings.semantic_search_top_k)
            )
            if scope_channel_id is not None:
                query = query.where(Video.creator_channel_id == scope_channel_id)
            rows = self.session.execute(query).all()
            candidates = [
                SemanticCandidate(
                    chunk_id=chunk.id,
                    video_id=video.id,
                    youtube_video_id=video.youtube_video_id,
                    video_title=video.title,
                    text=chunk.text,
                    start_time=chunk.start_time,
                    similarity=max(-1.0, min(1.0, float(score))),
                )
                for chunk, video, score in rows
            ]
            result = evaluate_candidates(candidates, self.settings.semantic_match_threshold)
            best = result.best
            self.session.execute(
                insert(SemanticMatch)
                .values(
                    comment_id=comment_id,
                    video_chunk_id=best.chunk_id if best else None,
                    match_found=result.match_found,
                    similarity=best.similarity if best else None,
                    query_text=query_text,
                    embedding_model=self.settings.embedding_model,
                    threshold=self.settings.semantic_match_threshold,
                    candidates=[asdict(candidate) for candidate in candidates],
                )
                .on_conflict_do_nothing(index_elements=[SemanticMatch.comment_id])
            )
            persisted = self.session.execute(
                select(SemanticMatch).where(SemanticMatch.comment_id == comment_id)
            ).scalar_one()
            persisted_candidates = [SemanticCandidate(**item) for item in persisted.candidates]
            return evaluate_candidates(persisted_candidates, persisted.threshold)

    @staticmethod
    def _query_text(comment: Comment) -> str:
        if comment.analysis is not None and comment.analysis.topic.strip():
            return f"Topic: {comment.analysis.topic.strip()}\nComment: {comment.text.strip()}"
        return comment.text.strip()
