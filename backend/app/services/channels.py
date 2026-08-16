import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import Channel, Video, VideoChunk
from app.schemas.channel import (
    ChannelIdentity,
    ChannelSyncProgress,
    VideoBatchImportRequest,
)
from app.services.embeddings import EmbeddingProviderError
from app.services.video_indexing import VideoIndexingService

logger = logging.getLogger(__name__)


class ChannelNotFoundError(LookupError):
    pass


class ChannelMismatchError(ValueError):
    pass


class ChannelsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def current(self) -> Channel | None:
        return self.session.scalar(
            select(Channel)
            .order_by(Channel.updated_at.desc(), Channel.id.desc())
            .limit(1)
        )

    def get(self, channel_id: int) -> Channel | None:
        return self.session.get(Channel, channel_id)

    def upsert(self, identity: ChannelIdentity, status: str = "connected") -> Channel:
        values = identity.model_dump()
        values.update(sync_status=status)

        update_values = dict(values)
        update_values["updated_at"] = func.now()

        try:
            # CreatorLoop is a single analyzed-channel workspace.
            self.session.execute(
                delete(Channel).where(
                    Channel.youtube_channel_id != identity.youtube_channel_id
                )
            )

            self.session.execute(
                insert(Channel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[Channel.youtube_channel_id],
                    set_=update_values,
                )
            )

            channel = self.session.execute(
                select(Channel).where(
                    Channel.youtube_channel_id == identity.youtube_channel_id
                )
            ).scalar_one()

            self.session.commit()
            return channel
        except Exception:
            self.session.rollback()
            raise

    def start_sync(self, channel_id: int) -> Channel:
        try:
            channel = self._locked(channel_id)
            channel.sync_status = "syncing"
            channel.video_sync_status = "pending"
            channel.comment_sync_status = "pending"
            channel.index_status = "pending"
            self.session.commit()
            return channel
        except Exception:
            self.session.rollback()
            raise

    def fail_sync(self, channel_id: int) -> None:
        try:
            channel = self._locked(channel_id)
            channel.sync_status = "failed"
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def apply_progress(
        self,
        channel_id: int,
        progress: ChannelSyncProgress,
    ) -> Channel:
        now = datetime.now(timezone.utc)

        try:
            channel = self._locked(channel_id)
            channel.sync_status = progress.status

            for name in (
                "video_sync_status",
                "comment_sync_status",
                "index_status",
                "videos_discovered",
                "videos_indexed",
                "comments_imported",
            ):
                value = getattr(progress, name)
                if value is not None:
                    setattr(channel, name, value)

            if progress.video_sync_status == "ready":
                channel.last_video_sync_at = now
            if progress.comment_sync_status == "ready":
                channel.last_comment_sync_at = now
            if progress.status == "ready":
                channel.last_full_sync_at = now

            self.session.commit()
            return channel
        except Exception:
            self.session.rollback()
            raise

    def import_videos(
        self,
        channel_id: int,
        request: VideoBatchImportRequest,
    ) -> tuple[list[int], int, int]:
        """
        Upsert metadata for the videos n8n checked and index only videos that
        actually need an embedding refresh.

        A video is indexed when:
        - it is new to CreatorLoop, or
        - its title/description changed, or
        - it exists but has no vector chunks yet.

        View/like/comment-count changes update PostgreSQL metadata without
        regenerating embeddings.
        """
        video_ids: list[int] = []
        index_ids: list[int] = []
        seen_youtube_ids: set[str] = set()

        new_count = 0
        changed_count = 0
        already_indexed_count = 0

        try:
            channel = self._locked(channel_id)
            channel.sync_status = "saving_videos"
            channel.video_sync_status = "syncing"

            for payload in request.videos:
                # Defensive dedupe in case an upstream batch contains the same ID
                # more than once.
                if payload.video_id in seen_youtube_ids:
                    continue
                seen_youtube_ids.add(payload.video_id)

                if payload.channel_id != channel.youtube_channel_id:
                    raise ChannelMismatchError(
                        "Video channel_id does not match the connected channel"
                    )

                existing = self.session.execute(
                    select(Video.id, Video.title, Video.description).where(
                        Video.youtube_video_id == payload.video_id
                    )
                ).one_or_none()

                existing_chunk_count = 0
                if existing is not None:
                    existing_chunk_count = (
                        self.session.scalar(
                            select(func.count(VideoChunk.id)).where(
                                VideoChunk.video_id == existing.id
                            )
                        )
                        or 0
                    )

                is_new = existing is None
                content_changed = (
                    is_new
                    or existing.title != payload.title
                    or existing.description != payload.description
                )
                missing_index = existing is not None and existing_chunk_count == 0

                values = payload.model_dump(exclude={"found", "video_id"})
                values.update(
                    youtube_video_id=payload.video_id,
                    creator_channel_id=channel.id,
                    youtube_url=(
                        payload.youtube_url
                        or f"https://www.youtube.com/watch?v={payload.video_id}"
                    ),
                )

                # Always refresh cheap metadata/statistics for videos in the
                # latest-100 window, even when their embeddings are reused.
                update_values = {
                    key: value
                    for key, value in values.items()
                    if key != "youtube_video_id"
                }
                update_values["updated_at"] = func.now()

                video_id = self.session.execute(
                    insert(Video)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=[Video.youtube_video_id],
                        set_=update_values,
                    )
                    .returning(Video.id)
                ).scalar_one()

                video_ids.append(video_id)

                should_index = request.index_videos and (
                    is_new or content_changed or missing_index
                )

                if should_index and video_id not in index_ids:
                    index_ids.append(video_id)

                if is_new:
                    new_count += 1
                elif content_changed or missing_index:
                    changed_count += 1
                else:
                    already_indexed_count += 1

            channel.videos_discovered = (
                self.session.scalar(
                    select(func.count(Video.id)).where(
                        Video.creator_channel_id == channel.id
                    )
                )
                or 0
            )
            discovered = channel.videos_discovered

            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        logger.info(
            "Video sync batch checked=%s new=%s changed_or_missing_index=%s "
            "already_indexed=%s to_index=%s",
            len(video_ids),
            new_count,
            changed_count,
            already_indexed_count,
            len(index_ids),
        )

        if index_ids:
            self.apply_progress(
                channel_id,
                ChannelSyncProgress(
                    status="indexing_videos",
                    index_status="syncing",
                ),
            )

            indexer = VideoIndexingService(self.session, self.settings)

            try:
                for video_id in index_ids:
                    indexer.index(video_id)
            except Exception:
                # Clear any transaction left open by the failed indexing call
                # before recording the failure status.
                self.session.rollback()
                try:
                    self.apply_progress(
                        channel_id,
                        ChannelSyncProgress(
                            status="failed",
                            index_status="failed",
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Unable to mark channel index as failed",
                        extra={"channel_id": channel_id},
                    )
                raise

        try:
            channel = self._locked(channel_id)

            indexed = (
                self.session.scalar(
                    select(func.count(func.distinct(VideoChunk.video_id)))
                    .join(Video, Video.id == VideoChunk.video_id)
                    .where(Video.creator_channel_id == channel.id)
                )
                or 0
            )

            channel.videos_indexed = indexed
            channel.video_sync_status = "ready"
            channel.index_status = "ready" if indexed >= discovered else "pending"
            channel.last_video_sync_at = datetime.now(timezone.utc)

            self.session.commit()
            return video_ids, discovered, indexed
        except Exception:
            self.session.rollback()
            raise

    def _locked(self, channel_id: int) -> Channel:
        channel = self.session.execute(
            select(Channel)
            .where(Channel.id == channel_id)
            .with_for_update()
        ).scalar_one_or_none()

        if channel is None:
            raise ChannelNotFoundError

        return channel