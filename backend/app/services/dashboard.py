from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Comment, CommentAnalysis, ReplySuggestion, SemanticMatch
from app.schemas.dashboard import DashboardMetrics


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def metrics(self) -> DashboardMetrics:
        comments_processed = self.session.scalar(select(func.count(CommentAnalysis.id)).join(Comment).where(Comment.creator_channel_id.is_not(None))) or 0
        questions_detected = self.session.scalar(
            select(func.count(CommentAnalysis.id)).join(Comment).where(Comment.creator_channel_id.is_not(None), CommentAnalysis.is_question.is_(True))
        ) or 0
        existing_answers_found = self.session.scalar(
            select(func.count(SemanticMatch.id)).join(Comment).where(Comment.creator_channel_id.is_not(None), SemanticMatch.match_found.is_(True))
        ) or 0
        content_requests = self.session.scalar(
            select(func.count(CommentAnalysis.id)).join(Comment).where(
                Comment.creator_channel_id.is_not(None),
                CommentAnalysis.is_content_request.is_(True)
            )
        ) or 0
        pending_replies = self.session.scalar(
            select(func.count(ReplySuggestion.id)).join(Comment).where(
                Comment.creator_channel_id.is_not(None),
                ReplySuggestion.status == "pending_approval"
            )
        ) or 0
        published_replies = self.session.scalar(
            select(func.count(ReplySuggestion.id)).join(Comment).where(Comment.creator_channel_id.is_not(None), ReplySuggestion.status == "published")
        ) or 0
        return DashboardMetrics(
            comments_processed=comments_processed,
            questions_detected=questions_detected,
            existing_answers_found=existing_answers_found,
            content_requests=content_requests,
            pending_replies=pending_replies,
            published_replies=published_replies,
        )
