from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database.models import Channel, Comment, ProcessingStatus, Video
from app.schemas.ingestion import MissingVideoPayload, YouTubeCommentIngestRequest


@dataclass(frozen=True)
class IngestionResult:
    comment_id: int | None
    new_comment: bool
    video_sync_required: bool = False
    youtube_video_id: str | None = None


class IngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest(self, payload: YouTubeCommentIngestRequest) -> IngestionResult:
        if isinstance(payload.video, MissingVideoPayload):
            existing_video = self.session.execute(
                select(Video).where(Video.youtube_video_id == payload.video.video_id)
            ).scalar_one_or_none()
            if existing_video is None:
                return IngestionResult(
                    comment_id=None,
                    new_comment=False,
                    video_sync_required=True,
                    youtube_video_id=payload.video.video_id,
                )
            video_id = existing_video.id
            creator_channel_id = existing_video.creator_channel_id
        else:
            creator_channel_id = self.session.execute(
                select(Channel.id).where(
                    Channel.youtube_channel_id == payload.video.channel_id
                )
            ).scalar_one_or_none()
            video_data = payload.video.model_dump(exclude={"found", "video_id"})
            video_data.update(
                youtube_video_id=payload.video.video_id,
                creator_channel_id=creator_channel_id,
            )
            video_update = {
                key: value for key, value in video_data.items() if key != "youtube_video_id"
            }
            video_update["updated_at"] = func.now()
            video_id = self.session.execute(
                insert(Video)
                .values(**video_data)
                .on_conflict_do_update(
                    index_elements=[Video.youtube_video_id],
                    set_=video_update,
                )
                .returning(Video.id)
            ).scalar_one()

        comment_data = payload.comment.model_dump(exclude={"video_id"})
        comment_data.update(
            video_id=video_id,
            creator_channel_id=creator_channel_id,
            knowledge_channel_id=creator_channel_id,
            processing_status=ProcessingStatus.pending,
        )
        inserted_id = self.session.execute(
            insert(Comment)
            .values(**comment_data)
            .on_conflict_do_nothing(index_elements=[Comment.youtube_comment_id])
            .returning(Comment.id)
        ).scalar_one_or_none()

        if inserted_id is not None:
            if creator_channel_id is not None:
                self.session.execute(
                    update(Channel)
                    .where(Channel.id == creator_channel_id)
                    .values(
                        comments_imported=Channel.comments_imported + 1,
                        last_comment_sync_at=func.now(),
                        updated_at=func.now(),
                    )
                )
            return IngestionResult(comment_id=inserted_id, new_comment=True)

        existing_id = self.session.execute(
            select(Comment.id).where(
                Comment.youtube_comment_id == payload.comment.youtube_comment_id
            )
        ).scalar_one()
        return IngestionResult(comment_id=existing_id, new_comment=False)
