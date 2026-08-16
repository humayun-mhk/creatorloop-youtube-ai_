from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import ClusterMembership, Comment, ContentBrief, Opportunity
from app.services.brief_generator import GeminiBriefGenerator


class OpportunityNotFoundError(LookupError):
    pass


class BriefThresholdError(RuntimeError):
    pass


@dataclass(frozen=True)
class BriefOutcome:
    brief: ContentBrief
    created: bool


class ContentBriefService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        generator: GeminiBriefGenerator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.generator = generator

    def generate(self, opportunity_id: int) -> BriefOutcome:
        with self.session.begin():
            opportunity = self.session.execute(
                select(Opportunity)
                .options(selectinload(Opportunity.content_brief))
                .where(Opportunity.id == opportunity_id)
            ).scalar_one_or_none()
            if opportunity is None:
                raise OpportunityNotFoundError
            if opportunity.content_brief is not None:
                return BriefOutcome(opportunity.content_brief, created=False)
            if opportunity.demand_score < self.settings.content_brief_threshold:
                raise BriefThresholdError(
                    f"Demand score must be at least {self.settings.content_brief_threshold:g}"
                )
            comments = list(self.session.scalars(
                select(Comment)
                .join(ClusterMembership, ClusterMembership.comment_id == Comment.id)
                .where(ClusterMembership.cluster_id == opportunity.cluster_id)
                .order_by((Comment.like_count + Comment.reply_count).desc(), Comment.id.asc())
                .limit(self.settings.representative_comment_limit)
            ).all())
            representative_comments = [comment.text for comment in comments]
            if not representative_comments:
                raise BriefThresholdError("Opportunity has no stored cluster-member comments")
            topic = opportunity.topic
            demand_score = opportunity.demand_score

        generator = self.generator or GeminiBriefGenerator(self.settings)
        generated = generator.generate(topic, demand_score, representative_comments)
        values = generated.model_dump()
        values.update(
            opportunity_id=opportunity_id,
            representative_comments=representative_comments,
            model=generator.model,
        )
        with self.session.begin():
            inserted_id = self.session.execute(
                insert(ContentBrief)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[ContentBrief.opportunity_id])
                .returning(ContentBrief.id)
            ).scalar_one_or_none()
            brief = self.session.execute(
                select(ContentBrief).where(ContentBrief.opportunity_id == opportunity_id)
            ).scalar_one()
            return BriefOutcome(brief, created=inserted_id is not None)
