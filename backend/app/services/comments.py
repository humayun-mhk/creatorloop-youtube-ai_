from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import Comment, SemanticMatch, VideoChunk


class CommentsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, offset: int, limit: int) -> list[Comment]:
        return list(self.session.scalars(
            select(Comment)
                .options(
                    selectinload(Comment.analysis),
                    selectinload(Comment.video),
                    selectinload(Comment.reply_suggestion),
                    selectinload(Comment.semantic_match)
                    .selectinload(SemanticMatch.video_chunk)
                    .selectinload(VideoChunk.video),
                )
            .where(Comment.creator_channel_id.is_not(None))
            .order_by(Comment.created_at.desc(), Comment.id.desc())
            .offset(offset)
            .limit(limit)
        ).all())

    def get(self, comment_id: int) -> Comment | None:
        return self.session.scalar(
            select(Comment)
            .options(
                selectinload(Comment.analysis),
                selectinload(Comment.video),
                selectinload(Comment.reply_suggestion),
                selectinload(Comment.semantic_match)
                .selectinload(SemanticMatch.video_chunk)
                .selectinload(VideoChunk.video),
            )
            .where(Comment.id == comment_id)
        )
