from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OpportunityDraft:
    topic: str
    member_comment_ids: list[int]
    request_count: int
    unique_users: int
    total_engagement: int
    latest_request_at: datetime
    content_gap_score: float


@dataclass(frozen=True)
class ScoredOpportunity:
    draft: OpportunityDraft
    frequency_score: float
    engagement_score: float
    recency_score: float
    unique_users_score: float
    content_gap_score: float
    demand_score: float


def _relative(value: int, maximum: int) -> float:
    return 0.0 if maximum <= 0 else min(100.0, value / maximum * 100.0)


def score_opportunities(
    drafts: list[OpportunityDraft], now: datetime, recency_window_days: int
) -> list[ScoredOpportunity]:
    if not drafts:
        return []
    max_frequency = max(draft.request_count for draft in drafts)
    max_engagement = max(draft.total_engagement for draft in drafts)
    max_users = max(draft.unique_users for draft in drafts)
    results: list[ScoredOpportunity] = []
    for draft in drafts:
        frequency = _relative(draft.request_count, max_frequency)
        engagement = _relative(draft.total_engagement, max_engagement)
        unique_users = _relative(draft.unique_users, max_users)
        age_days = max(0.0, (now - draft.latest_request_at).total_seconds() / 86400)
        recency = max(0.0, 100.0 * (1.0 - age_days / recency_window_days))
        content_gap = max(0.0, min(100.0, draft.content_gap_score))
        demand = (
            0.35 * frequency
            + 0.20 * engagement
            + 0.20 * recency
            + 0.15 * unique_users
            + 0.10 * content_gap
        )
        results.append(ScoredOpportunity(
            draft=draft,
            frequency_score=round(frequency, 2),
            engagement_score=round(engagement, 2),
            recency_score=round(recency, 2),
            unique_users_score=round(unique_users, 2),
            content_gap_score=round(content_gap, 2),
            demand_score=round(max(0.0, min(100.0, demand)), 2),
        ))
    return results
