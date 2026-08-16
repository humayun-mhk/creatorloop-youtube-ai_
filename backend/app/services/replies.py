from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import Comment, ReplySuggestion, SemanticMatch, VideoChunk
from app.services.reply_generator import GeminiReplyGenerator, ReplyContext


class CommentNotFoundError(LookupError):
    pass


class ReplyNotEligibleError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReplyGenerationOutcome:
    reply: ReplySuggestion
    created: bool


class ReplySuggestionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        generator: GeminiReplyGenerator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.generator = generator

    def generate(self, comment_id: int) -> ReplyGenerationOutcome:
        with self.session.begin():
            comment = self.session.execute(
                select(Comment)
                .options(
                    selectinload(Comment.video),
                    selectinload(Comment.analysis),
                    selectinload(Comment.reply_suggestion),
                    selectinload(Comment.semantic_match)
                    .selectinload(SemanticMatch.video_chunk)
                    .selectinload(VideoChunk.video),
                )
                .where(Comment.id == comment_id)
            ).scalar_one_or_none()
            if comment is None:
                raise CommentNotFoundError
            if comment.reply_suggestion is not None:
                return ReplyGenerationOutcome(comment.reply_suggestion, created=False)
            if comment.analysis is None:
                raise ReplyNotEligibleError("Comment must be classified before reply generation")
            match = comment.semantic_match
            if match is None or not match.match_found or match.video_chunk is None:
                raise ReplyNotEligibleError("Comment has no satisfactory creator-content match")
            chunk = match.video_chunk
            context = ReplyContext(
                viewer_comment=comment.text,
                commented_video_title=comment.video.title,
                commented_video_description=comment.video.description,
                classification_intent=comment.analysis.intent,
                classification_topic=comment.analysis.topic,
                classification_sentiment=comment.analysis.sentiment,
                matched_video_title=chunk.video.title,
                matched_video_url=chunk.video.youtube_url
                or f"https://www.youtube.com/watch?v={chunk.video.youtube_video_id}",
                matched_chunk=chunk.text,
                similarity=match.similarity or 0.0,
                start_time=chunk.start_time,
                creator_reply_style=self.settings.creator_reply_style,
            )
            matched_video_id = chunk.video_id
            similarity = match.similarity or 0.0

        generator = self.generator or GeminiReplyGenerator(self.settings)
        suggested_reply = generator.generate(context)

        with self.session.begin():
            inserted_id = self.session.execute(
                insert(ReplySuggestion)
                .values(
                    comment_id=comment_id,
                    suggested_reply=suggested_reply,
                    status="pending_approval",
                    matched_video_id=matched_video_id,
                    similarity=similarity,
                )
                .on_conflict_do_nothing(index_elements=[ReplySuggestion.comment_id])
                .returning(ReplySuggestion.id)
            ).scalar_one_or_none()
            reply = self.session.execute(
                select(ReplySuggestion).where(ReplySuggestion.comment_id == comment_id)
            ).scalar_one()
            return ReplyGenerationOutcome(reply, created=inserted_id is not None)


class RepliesService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, offset: int, limit: int) -> list[ReplySuggestion]:
        return list(self.session.scalars(
            select(ReplySuggestion)
            .order_by(ReplySuggestion.created_at.desc(), ReplySuggestion.id.desc())
            .offset(offset)
            .limit(limit)
        ).all())

    def get(self, reply_id: int) -> ReplySuggestion | None:
        return self.session.get(ReplySuggestion, reply_id)
