from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import Comment, CommentAnalysis, ProcessingStatus
from app.schemas.analysis import ClassificationResult
from app.services.classifier import GeminiClassifier


class CommentNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class AnalysisOutcome:
    analysis: CommentAnalysis
    created: bool


class CommentAnalysisService:
    def __init__(self, session: Session, settings: Settings, classifier: GeminiClassifier | None = None) -> None:
        self.session = session
        self.settings = settings
        self.classifier = classifier

    def analyze(self, comment_id: int) -> AnalysisOutcome:
        with self.session.begin():
            comment = self.session.execute(
                select(Comment)
                .options(selectinload(Comment.video), selectinload(Comment.analysis))
                .where(Comment.id == comment_id)
            ).scalar_one_or_none()
            if comment is None:
                raise CommentNotFoundError
            if comment.analysis is not None:
                return AnalysisOutcome(comment.analysis, created=False)
            comment.processing_status = ProcessingStatus.processing
            comment_text = comment.text
            video_title = comment.video.title
            engagement = comment.like_count + comment.reply_count

        try:
            classifier = self.classifier or GeminiClassifier(self.settings)
            result = classifier.classify(comment_text, video_title)
        except Exception:
            with self.session.begin():
                failed_comment = self.session.get(Comment, comment_id)
                if failed_comment is not None:
                    failed_comment.processing_status = ProcessingStatus.failed
            raise

        return self._persist(comment_id, result, classifier.model, engagement)

    def _persist(self, comment_id: int, result: ClassificationResult, model: str, engagement: int) -> AnalysisOutcome:
        values = result.model_dump()
        intent_weight = {
            "content_request": 1.0, "question": 0.95, "complaint": 0.7,
            "feedback": 0.55, "praise": 0.3, "other": 0.25, "spam": 0.0,
        }[result.intent]
        relevance = round(result.confidence * intent_weight * 100, 2)
        engagement_component = min(max(engagement, 0), 20) / 20 * 20
        values.update(
            relevance_score=relevance,
            priority_score=round(min(100, relevance * 0.8 + engagement_component), 2),
        )
        values.update(comment_id=comment_id, model=model)
        with self.session.begin():
            analysis_id = self.session.execute(
                insert(CommentAnalysis)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[CommentAnalysis.comment_id])
                .returning(CommentAnalysis.id)
            ).scalar_one_or_none()
            comment = self.session.get(Comment, comment_id)
            if comment is not None:
                comment.processing_status = ProcessingStatus.completed
            analysis = self.session.execute(
                select(CommentAnalysis).where(CommentAnalysis.comment_id == comment_id)
            ).scalar_one()
            return AnalysisOutcome(analysis, created=analysis_id is not None)
