import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import ReplySuggestion
from app.services.n8n_publisher import N8NReplyPublisher

logger = logging.getLogger(__name__)


class ReplyNotFoundError(LookupError):
    pass


class InvalidReplyTransitionError(RuntimeError):
    pass


class ReplyApprovalService:
    """
    Owns reply state transitions around external publishing.

    Valid publish flow:

        pending_approval -> publishing -> published
        failed           -> publishing -> published

    External publishing failures are persisted as `failed`, which means the
    same reply can be retried from the frontend without creating a new
    ReplySuggestion row.
    """

    def __init__(
        self,
        session: Session,
        settings: Settings,
        publisher: N8NReplyPublisher | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.publisher = publisher

    def approve(
        self,
        reply_id: int,
        edited_reply: str | None = None,
    ) -> ReplySuggestion:
        # Persist the publishing state before making an external network call.
        with self.session.begin():
            reply = self._locked_reply(reply_id)

            if reply.status == "published":
                # Idempotent API behavior: approving an already-published
                # reply simply returns the existing published row.
                return reply

            if reply.status == "publishing":
                raise InvalidReplyTransitionError(
                    "Reply publishing is already in progress"
                )

            if reply.status == "ignored":
                raise InvalidReplyTransitionError(
                    "Ignored reply cannot be approved"
                )

            final_text = self._resolve_final_text(
                reply,
                edited_reply,
            )

            reply.edited_reply = final_text
            reply.approved_at = (
                reply.approved_at
                or datetime.now(timezone.utc)
            )

            # Clear any stale publication data before retrying a failed row.
            reply.youtube_reply_id = None
            reply.published_at = None
            reply.status = "publishing"

            youtube_comment_id = (
                reply.comment.youtube_comment_id
            )

        publisher = (
            self.publisher
            or N8NReplyPublisher(self.settings)
        )

        try:
            youtube_reply_id = publisher.publish(
                youtube_comment_id,
                final_text,
            )
        except Exception as exc:
            # A failed remote call must never leave the DB stuck in
            # `publishing`. Preserve the edited text and mark it retryable.
            self._mark_failed(reply_id)

            logger.warning(
                "Reply %s publishing failed: %s",
                reply_id,
                exc,
                exc_info=True,
            )
            raise

        with self.session.begin():
            published = self._locked_reply(reply_id)

            # Defensive idempotency in case another request completed the row
            # while the external call was in flight.
            if published.status == "published":
                return published

            if published.status != "publishing":
                raise InvalidReplyTransitionError(
                    "Reply state changed while publishing"
                )

            published.youtube_reply_id = (
                youtube_reply_id
            )
            published.published_at = (
                datetime.now(timezone.utc)
            )
            published.status = "published"

            return published

    def ignore(
        self,
        reply_id: int,
    ) -> ReplySuggestion:
        with self.session.begin():
            reply = self._locked_reply(reply_id)

            if reply.status == "ignored":
                return reply

            if reply.status == "publishing":
                raise InvalidReplyTransitionError(
                    "Cannot ignore a reply while publishing"
                )

            if reply.status == "published":
                raise InvalidReplyTransitionError(
                    "Published reply cannot be ignored"
                )

            # pending_approval, approved, and failed may all be ignored.
            reply.status = "ignored"
            return reply

    @staticmethod
    def _resolve_final_text(
        reply: ReplySuggestion,
        edited_reply: str | None,
    ) -> str:
        """
        Keep a previously edited reply when retrying.

        Priority:
        1. New text explicitly supplied by the frontend.
        2. Previously saved edited text.
        3. Original AI suggestion.
        """

        candidate = (
            edited_reply
            if edited_reply is not None
            else (
                reply.edited_reply
                or reply.suggested_reply
            )
        )

        final_text = candidate.strip()

        if not final_text:
            raise InvalidReplyTransitionError(
                "Approved reply cannot be empty"
            )

        if len(final_text) > 2000:
            raise InvalidReplyTransitionError(
                "Approved reply cannot exceed 2000 characters"
            )

        return final_text

    def _mark_failed(
        self,
        reply_id: int,
    ) -> None:
        # Network exceptions do not normally leave a SQLAlchemy transaction
        # open, but rollback defensively if the session has one.
        if self.session.in_transaction():
            self.session.rollback()

        with self.session.begin():
            failed = self._locked_reply(reply_id)

            # Do not overwrite a state that another request already completed.
            if failed.status == "publishing":
                failed.status = "failed"

    def _locked_reply(
        self,
        reply_id: int,
    ) -> ReplySuggestion:
        reply = self.session.execute(
            select(ReplySuggestion)
            .options(
                selectinload(
                    ReplySuggestion.comment
                )
            )
            .where(
                ReplySuggestion.id == reply_id
            )
            .with_for_update()
        ).scalar_one_or_none()

        if reply is None:
            raise ReplyNotFoundError

        return reply