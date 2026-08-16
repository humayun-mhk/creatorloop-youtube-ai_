from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import Comment
from app.services.comment_analysis import CommentAnalysisService, CommentNotFoundError
from app.services.opportunities import OpportunitiesService
from app.services.replies import ReplySuggestionService
from app.services.semantic_search import SemanticSearchService


@dataclass(frozen=True)
class ProcessingOutcome:
    comment_id: int
    status: str
    outcome: str | None
    analysis_id: int | None = None
    match_found: bool | None = None
    reply_id: int | None = None
    opportunities_rebuilt: int | None = None
    cached: bool = False


class CommentProcessingService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def process(
        self,
        comment_id: int,
        *,
        rebuild_opportunities: bool = False,
    ) -> ProcessingOutcome:
        with self.session.begin():
            comment = self.session.execute(
                select(Comment)
                .options(
                    selectinload(Comment.analysis),
                    selectinload(Comment.semantic_match),
                    selectinload(Comment.reply_suggestion),
                )
                .where(Comment.id == comment_id)
                .with_for_update()
            ).scalar_one_or_none()
            if comment is None:
                raise CommentNotFoundError
            if comment.pipeline_status == "completed":
                return self._cached(comment)
            if comment.pipeline_status == "processing":
                return ProcessingOutcome(
                    comment_id=comment.id,
                    status="processing",
                    outcome=comment.pipeline_outcome,
                    cached=True,
                )
            comment.pipeline_status = "processing"
            comment.pipeline_started_at = datetime.now(timezone.utc)
            comment.pipeline_completed_at = None

        try:
            analysis = CommentAnalysisService(
                self.session, self.settings
            ).analyze(comment_id).analysis
            with self.session.begin():
                comment = self.session.get(Comment, comment_id)
                if comment is None:
                    raise CommentNotFoundError
                is_public = comment.is_public
                can_reply = comment.can_reply
                knowledge_channel_id = comment.knowledge_channel_id

            # Gemini makes the first-stage decision about whether this comment
            # deserves a creator response. Semantic search remains the safety gate:
            # we only generate an answer when creator-owned content supports it.
            eligible = analysis.should_reply and analysis.intent != "spam"
            if not is_public or not eligible:
                outcome = "no_reply_needed" if is_public else "not_public"
                return self._complete(comment_id, outcome, analysis_id=analysis.id)

            match = SemanticSearchService(
                self.session, self.settings
            ).match_comment(comment_id, knowledge_channel_id=knowledge_channel_id)
            if match.match_found:
                if not can_reply:
                    return self._complete(
                        comment_id,
                        "match_no_reply",
                        analysis_id=analysis.id,
                        match_found=True,
                    )
                reply = ReplySuggestionService(
                    self.session, self.settings
                ).generate(comment_id).reply
                return self._complete(
                    comment_id,
                    "reply_suggested",
                    analysis_id=analysis.id,
                    match_found=True,
                    reply_id=reply.id,
                )

            rebuilt = None
            if rebuild_opportunities and knowledge_channel_id is not None:
                rebuilt = OpportunitiesService(
                    self.session, self.settings
                ).rebuild().opportunities_created
            return self._complete(
                comment_id,
                "unmet_demand",
                analysis_id=analysis.id,
                match_found=False,
                opportunities_rebuilt=rebuilt,
            )
        except Exception:
            with self.session.begin():
                failed = self.session.get(Comment, comment_id)
                if failed is not None:
                    failed.pipeline_status = "failed"
            raise

    def _complete(
        self,
        comment_id: int,
        outcome: str,
        *,
        analysis_id: int | None = None,
        match_found: bool | None = None,
        reply_id: int | None = None,
        opportunities_rebuilt: int | None = None,
    ) -> ProcessingOutcome:
        with self.session.begin():
            comment = self.session.execute(
                select(Comment).where(Comment.id == comment_id).with_for_update()
            ).scalar_one()
            comment.pipeline_status = "completed"
            comment.pipeline_outcome = outcome
            comment.pipeline_completed_at = datetime.now(timezone.utc)
        return ProcessingOutcome(
            comment_id=comment_id,
            status="completed",
            outcome=outcome,
            analysis_id=analysis_id,
            match_found=match_found,
            reply_id=reply_id,
            opportunities_rebuilt=opportunities_rebuilt,
        )

    @staticmethod
    def _cached(comment: Comment) -> ProcessingOutcome:
        return ProcessingOutcome(
            comment_id=comment.id,
            status="completed",
            outcome=comment.pipeline_outcome,
            analysis_id=comment.analysis.id if comment.analysis else None,
            match_found=comment.semantic_match.match_found if comment.semantic_match else None,
            reply_id=comment.reply_suggestion.id if comment.reply_suggestion else None,
            cached=True,
        )
