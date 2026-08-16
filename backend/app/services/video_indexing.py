from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import Channel, SemanticMatch, Video, VideoChunk
from app.schemas.video import TranscriptSegment
from app.services.embeddings import EmbeddingService
from app.services.text_processing import TextChunker, TextPiece, normalize_text


class VideoNotFoundError(LookupError):
    pass


class EmptyVideoContentError(ValueError):
    pass


@dataclass(frozen=True)
class VideoIndexResult:
    video_id: int
    chunk_count: int


class VideoIndexingService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.embedder = embedder
        self.chunker = TextChunker(settings.chunk_size, settings.chunk_overlap)

    def index(
        self, video_id: int, transcript: list[TranscriptSegment] | None = None
    ) -> VideoIndexResult:
        with self.session.begin():
            video = self.session.get(Video, video_id)
            if video is None:
                raise VideoNotFoundError
            title = normalize_text(video.title)
            description = normalize_text(video.description)

        pieces: list[TextPiece] = []
        if title:
            pieces.append(TextPiece(f"Title: {title}"))
        if description:
            pieces.append(TextPiece(f"Description: {description}"))
        for segment in transcript or []:
            pieces.append(TextPiece(segment.text, segment.start_time, segment.end_time))

        chunks = self.chunker.chunk(pieces)
        if not chunks:
            raise EmptyVideoContentError("Video has no indexable content")
        embedder = self.embedder or EmbeddingService(self.settings)
        embeddings = embedder.embed_documents([chunk.text for chunk in chunks])

        with self.session.begin():
            locked_video = self.session.execute(
                select(Video.id).where(Video.id == video_id).with_for_update()
            ).scalar_one_or_none()
            if locked_video is None:
                raise VideoNotFoundError
            # Any indexed-content change can alter global nearest-neighbor rankings.
            self.session.execute(delete(SemanticMatch))
            self.session.execute(delete(VideoChunk).where(VideoChunk.video_id == video_id))
            self.session.add_all([
                VideoChunk(
                    video_id=video_id,
                    text=chunk.text,
                    chunk_index=index,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    embedding=embedding,
                )
                for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
            ])
        return VideoIndexResult(video_id=video_id, chunk_count=len(chunks))


class VideosService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_with_index_status(self, video_id: int) -> tuple[Video, int] | None:
        row = self.session.execute(
            select(Video, func.count(VideoChunk.id))
            .outerjoin(VideoChunk, VideoChunk.video_id == Video.id)
            .where(Video.id == video_id)
            .group_by(Video.id)
        ).one_or_none()
        return (row[0], row[1]) if row else None

    def list_creator_videos(self, offset: int, limit: int) -> list[tuple[Video, int]]:
        rows = self.session.execute(
            select(Video, func.count(VideoChunk.id))
            .join(Channel, Channel.id == Video.creator_channel_id)
            .outerjoin(VideoChunk, VideoChunk.video_id == Video.id)
            .group_by(Video.id)
            .order_by(Video.published_at.desc().nullslast(), Video.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [(video, chunk_count) for video, chunk_count in rows]
