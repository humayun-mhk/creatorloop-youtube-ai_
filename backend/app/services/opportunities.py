from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.database.models import (
    ClusterMembership,
    Comment,
    CommentAnalysis,
    DemandCluster,
    Opportunity,
    SemanticMatch,
)
from app.services.clustering import cluster_embeddings
from app.services.demand_score import OpportunityDraft, score_opportunities
from app.services.embeddings import EmbeddingService
from app.services.text_processing import normalize_text


class OpportunityNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class EligibleRequest:
    comment_id: int
    text: str
    topic: str
    user_key: str
    engagement: int
    published_at: datetime
    similarity: float | None


@dataclass(frozen=True)
class RebuildResult:
    eligible_comments: int
    opportunities_created: int


class OpportunitiesService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.embedder = embedder

    def rebuild(self, now: datetime | None = None) -> RebuildResult:
        rebuild_time = now or datetime.now(timezone.utc)
        with self.session.begin():
            rows = self.session.execute(
                select(Comment, CommentAnalysis, SemanticMatch)
                .join(CommentAnalysis, CommentAnalysis.comment_id == Comment.id)
                .join(SemanticMatch, SemanticMatch.comment_id == Comment.id)
                .where(
                    Comment.creator_channel_id.is_not(None),
                    CommentAnalysis.intent.in_(["question", "content_request"]),
                    CommentAnalysis.intent != "spam",
                    SemanticMatch.match_found.is_(False),
                )
                .order_by(Comment.id)
            ).all()
            requests = [
                EligibleRequest(
                    comment_id=comment.id,
                    text=comment.text,
                    topic=analysis.topic,
                    user_key=comment.author_channel_id or f"author:{comment.author_name.casefold()}",
                    engagement=comment.like_count + comment.reply_count,
                    published_at=comment.published_at,
                    similarity=match.similarity,
                )
                for comment, analysis, match in rows
            ]

        embeddings: list[list[float]] = []
        if requests:
            embedder = self.embedder or EmbeddingService(self.settings)
            embeddings = embedder.embed_for_similarity([
                f"Topic: {request.topic}\nRequest: {request.text}" for request in requests
            ])
        labels = cluster_embeddings(
            embeddings,
            self.settings.clustering_similarity_threshold,
            self.settings.clustering_min_samples,
        )
        groups: dict[int, list[EligibleRequest]] = defaultdict(list)
        for request, label in zip(requests, labels, strict=True):
            groups[label].append(request)
        drafts = [self._draft(group) for _, group in sorted(groups.items())]
        scored = score_opportunities(
            drafts, rebuild_time, self.settings.demand_recency_window_days
        )

        with self.session.begin():
            self.session.execute(delete(DemandCluster))
            for index, item in enumerate(scored, start=1):
                cluster = DemandCluster(label=f"cluster-{index:04d}")
                self.session.add(cluster)
                self.session.flush()
                self.session.add_all([
                    ClusterMembership(cluster_id=cluster.id, comment_id=comment_id)
                    for comment_id in item.draft.member_comment_ids
                ])
                self.session.add(Opportunity(
                    cluster_id=cluster.id,
                    topic=item.draft.topic,
                    request_count=item.draft.request_count,
                    unique_users=item.draft.unique_users,
                    total_engagement=item.draft.total_engagement,
                    latest_request_at=item.draft.latest_request_at,
                    frequency_score=item.frequency_score,
                    engagement_score=item.engagement_score,
                    recency_score=item.recency_score,
                    unique_users_score=item.unique_users_score,
                    content_gap_score=item.content_gap_score,
                    demand_score=item.demand_score,
                ))
        return RebuildResult(len(requests), len(scored))

    def list_opportunities(self, offset: int, limit: int) -> list[Opportunity]:
        opportunities = list(self.session.scalars(
            select(Opportunity)
            .options(
                selectinload(Opportunity.content_brief),
                selectinload(Opportunity.cluster)
                .selectinload(DemandCluster.memberships)
                .selectinload(ClusterMembership.comment),
            )
            .order_by(Opportunity.demand_score.desc(), Opportunity.id.asc())
            .offset(offset)
            .limit(limit)
        ).all())
        for opportunity in opportunities:
            self._attach_representative_comments(opportunity)
        return opportunities

    def get(self, opportunity_id: int) -> Opportunity | None:
        opportunity = self.session.scalar(
            select(Opportunity)
            .options(
                selectinload(Opportunity.content_brief),
                selectinload(Opportunity.cluster)
                .selectinload(DemandCluster.memberships)
                .selectinload(ClusterMembership.comment),
            )
            .where(Opportunity.id == opportunity_id)
        )
        if opportunity is not None:
            self._attach_representative_comments(opportunity)
        return opportunity

    def _attach_representative_comments(self, opportunity: Opportunity) -> None:
        comments = [membership.comment for membership in opportunity.cluster.memberships]
        comments.sort(key=lambda item: (-(item.like_count + item.reply_count), item.id))
        setattr(
            opportunity,
            "representative_comments",
            [comment.text for comment in comments[: self.settings.representative_comment_limit]],
        )

    @staticmethod
    def _draft(group: list[EligibleRequest]) -> OpportunityDraft:
        normalized_topics = [normalize_text(item.topic) or "Uncategorized request" for item in group]
        counts = Counter(topic.casefold() for topic in normalized_topics)
        winning_key = sorted(counts, key=lambda key: (-counts[key], key))[0]
        topic = sorted(topic for topic in normalized_topics if topic.casefold() == winning_key)[0]
        gaps = [100.0 if item.similarity is None else (1.0 - item.similarity) * 100.0 for item in group]
        return OpportunityDraft(
            topic=topic,
            member_comment_ids=[item.comment_id for item in group],
            request_count=len(group),
            unique_users=len({item.user_key for item in group}),
            total_engagement=sum(item.engagement for item in group),
            latest_request_at=max(item.published_at for item in group),
            content_gap_score=sum(gaps) / len(gaps),
        )
