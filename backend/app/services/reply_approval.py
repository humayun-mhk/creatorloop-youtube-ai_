from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import ReplySuggestion
from app.services.n8n_publisher import N8NReplyPublisher


class ReplyNotFoundError(LookupError):
    pass


class InvalidReplyTransitionError(RuntimeError):
    pass


class ReplyApprovalService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        publisher: N8NReplyPublisher | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.publisher = publisher

    def approve(self, reply_id: int, edited_reply: str | None = None) -> ReplySuggestion:
        with self.session.begin():
            reply = self._locked_reply(reply_id)
            if reply.status == "published":
                return reply
            if reply.status == "publishing":
                raise InvalidReplyTransitionError("Reply publishing is already in progress")
            if reply.status == "ignored":
                raise InvalidReplyTransitionError("Ignored reply cannot be approved")
            final_text = (edited_reply if edited_reply is not None else reply.suggested_reply).strip()
            if not final_text:
                raise InvalidReplyTransitionError("Approved reply cannot be empty")
            reply.edited_reply = final_text
            reply.approved_at = reply.approved_at or datetime.now(timezone.utc)
            reply.status = "publishing"
            youtube_comment_id = reply.comment.youtube_comment_id

        publisher = self.publisher or N8NReplyPublisher(self.settings)
        try:
            youtube_reply_id = publisher.publish(youtube_comment_id, final_text)
        except Exception:
            with self.session.begin():
                failed = self._locked_reply(reply_id)
                if failed.status == "publishing":
                    failed.status = "failed"
            raise

        with self.session.begin():
            published = self._locked_reply(reply_id)
            if published.status == "published":
                return published
            published.youtube_reply_id = youtube_reply_id
            published.published_at = datetime.now(timezone.utc)
            published.status = "published"
            return published

    def ignore(self, reply_id: int) -> ReplySuggestion:
        with self.session.begin():
            reply = self._locked_reply(reply_id)
            if reply.status == "ignored":
                return reply
            if reply.status in {"publishing", "published"}:
                raise InvalidReplyTransitionError(
                    f"Cannot ignore a reply with status {reply.status}"
                )
            reply.status = "ignored"
            return reply

    def _locked_reply(self, reply_id: int) -> ReplySuggestion:
        reply = self.session.execute(
            select(ReplySuggestion)
            .options(selectinload(ReplySuggestion.comment))
            .where(ReplySuggestion.id == reply_id)
            .with_for_update()
        ).scalar_one_or_none()
        if reply is None:
            raise ReplyNotFoundError
        return reply
