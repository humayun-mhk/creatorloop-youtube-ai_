import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import VECTOR


class Base(DeclarativeBase):
    pass


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    ignored = "ignored"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"
    __table_args__ = (
        CheckConstraint(
            "sync_status IN ('not_connected','connecting','connected','syncing','fetching_videos','saving_videos','indexing_videos','fetching_comments','processing_comments','ready','failed')",
            name="ck_channels_sync_status",
        ),
        CheckConstraint(
            "video_sync_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_video_sync_status",
        ),
        CheckConstraint(
            "comment_sync_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_comment_sync_status",
        ),
        CheckConstraint(
            "index_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_index_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    youtube_channel_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_url: Mapped[str | None] = mapped_column(Text)
    custom_url: Mapped[str | None] = mapped_column(String(255))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    country: Mapped[str | None] = mapped_column(String(16))
    default_language: Mapped[str | None] = mapped_column(String(32))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploads_playlist_id: Mapped[str | None] = mapped_column(String(128))
    subscriber_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    hidden_subscriber_count: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    channel_view_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    public_video_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    keywords: Mapped[str | None] = mapped_column(Text)
    topic_categories: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    privacy_status: Mapped[str | None] = mapped_column(String(32))
    made_for_kids: Mapped[bool | None] = mapped_column(Boolean)
    sync_status: Mapped[str] = mapped_column(String(32), default="not_connected", server_default="not_connected", nullable=False)
    video_sync_status: Mapped[str] = mapped_column(String(32), default="not_connected", server_default="not_connected", nullable=False)
    comment_sync_status: Mapped[str] = mapped_column(String(32), default="not_connected", server_default="not_connected", nullable=False)
    index_status: Mapped[str] = mapped_column(String(32), default="not_connected", server_default="not_connected", nullable=False)
    last_video_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_comment_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    videos_discovered: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    videos_indexed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    comments_imported: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    videos: Mapped[list["Video"]] = relationship(back_populates="creator_channel")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="creator_channel", foreign_keys="Comment.creator_channel_id"
    )


class Video(TimestampMixin, Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    creator_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    channel_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    youtube_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration: Mapped[str | None] = mapped_column(String(32))
    definition: Mapped[str | None] = mapped_column(String(16))
    category_id: Mapped[str | None] = mapped_column(String(32))
    default_language: Mapped[str | None] = mapped_column(String(32))
    default_audio_language: Mapped[str | None] = mapped_column(String(32))
    live_broadcast_content: Mapped[str | None] = mapped_column(String(32))
    caption_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    comments: Mapped[list["Comment"]] = relationship(back_populates="video")
    creator_channel: Mapped[Channel | None] = relationship(back_populates="videos")
    chunks: Mapped[list["VideoChunk"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_processing_status", "processing_status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    youtube_comment_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    youtube_thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    creator_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    knowledge_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), index=True
    )
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_channel_id: Mapped[str | None] = mapped_column(String(128))
    author_profile_image_url: Mapped[str | None] = mapped_column(Text)
    author_channel_url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.pending,
        server_default=ProcessingStatus.pending.value,
        nullable=False,
    )
    pipeline_status: Mapped[str] = mapped_column(
        String(24), default="not_started", server_default="not_started", nullable=False
    )
    pipeline_outcome: Mapped[str | None] = mapped_column(String(32))
    pipeline_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pipeline_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped[Video] = relationship(back_populates="comments")
    creator_channel: Mapped[Channel | None] = relationship(
        back_populates="comments", foreign_keys=[creator_channel_id]
    )
    knowledge_channel: Mapped[Channel | None] = relationship(foreign_keys=[knowledge_channel_id])
    quick_analyze_memberships: Mapped[list["QuickAnalyzeComment"]] = relationship(
        back_populates="comment", cascade="all, delete-orphan"
    )
    analysis: Mapped["CommentAnalysis | None"] = relationship(
        back_populates="comment", uselist=False, cascade="all, delete-orphan"
    )
    semantic_match: Mapped["SemanticMatch | None"] = relationship(
        back_populates="comment", uselist=False, cascade="all, delete-orphan"
    )
    reply_suggestion: Mapped["ReplySuggestion | None"] = relationship(
        back_populates="comment", uselist=False, cascade="all, delete-orphan"
    )


class CommentAnalysis(TimestampMixin, Base):
    __tablename__ = "comment_analyses"
    __table_args__ = (
        CheckConstraint(
            "intent IN ('question','content_request','complaint','feedback','praise','spam','other')",
            name="ck_comment_analyses_intent",
        ),
        CheckConstraint(
            "sentiment IN ('positive','neutral','negative')",
            name="ck_comment_analyses_sentiment",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_comment_analyses_confidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    is_question: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_content_request: Mapped[bool] = mapped_column(Boolean, nullable=False)
    should_reply: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    reply_reason: Mapped[str] = mapped_column(String(500), default="Not evaluated", server_default="Not evaluated", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    comment: Mapped[Comment] = relationship(back_populates="analysis")


class VideoChunk(Base):
    __tablename__ = "video_chunks"
    __table_args__ = (
        Index("uq_video_chunks_video_chunk_index", "video_id", "chunk_index", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float | None] = mapped_column(Float)
    end_time: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped[Video] = relationship(back_populates="chunks")


class SemanticMatch(TimestampMixin, Base):
    __tablename__ = "semantic_matches"
    __table_args__ = (
        CheckConstraint("similarity IS NULL OR (similarity >= -1 AND similarity <= 1)", name="ck_semantic_matches_similarity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    video_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_chunks.id", ondelete="SET NULL")
    )
    match_found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    similarity: Mapped[float | None] = mapped_column(Float)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    candidates: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)

    comment: Mapped[Comment] = relationship(back_populates="semantic_match")
    video_chunk: Mapped[VideoChunk | None] = relationship()


class ReplySuggestion(TimestampMixin, Base):
    __tablename__ = "reply_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval','approved','ignored','publishing','published','failed')",
            name="ck_reply_suggestions_status",
        ),
        CheckConstraint("similarity >= -1 AND similarity <= 1", name="ck_reply_suggestions_similarity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    suggested_reply: Mapped[str] = mapped_column(Text, nullable=False)
    edited_reply: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), default="pending_approval", server_default="pending_approval", nullable=False
    )
    matched_video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    youtube_reply_id: Mapped[str | None] = mapped_column(String(128))

    comment: Mapped[Comment] = relationship(back_populates="reply_suggestion")
    matched_video: Mapped[Video] = relationship()


class DemandCluster(Base):
    __tablename__ = "demand_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["ClusterMembership"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )
    opportunity: Mapped["Opportunity"] = relationship(
        back_populates="cluster", uselist=False, cascade="all, delete-orphan"
    )


class ClusterMembership(Base):
    __tablename__ = "cluster_memberships"
    __table_args__ = (
        Index("uq_cluster_memberships_comment_id", "comment_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("demand_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cluster: Mapped[DemandCluster] = relationship(back_populates="memberships")
    comment: Mapped[Comment] = relationship()


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("demand_score >= 0 AND demand_score <= 100", name="ck_opportunities_demand_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("demand_clusters.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unique_users: Mapped[int] = mapped_column(Integer, nullable=False)
    total_engagement: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_request_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    frequency_score: Mapped[float] = mapped_column(Float, nullable=False)
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False)
    unique_users_score: Mapped[float] = mapped_column(Float, nullable=False)
    content_gap_score: Mapped[float] = mapped_column(Float, nullable=False)
    demand_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    cluster: Mapped[DemandCluster] = relationship(back_populates="opportunity")
    content_brief: Mapped["ContentBrief | None"] = relationship(
        back_populates="opportunity", uselist=False, cascade="all, delete-orphan"
    )


class ContentBrief(TimestampMixin, Base):
    __tablename__ = "content_briefs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    suggested_title: Mapped[str] = mapped_column(String(500), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    audience_pain: Mapped[str] = mapped_column(Text, nullable=False)
    why_users_want: Mapped[str] = mapped_column(Text, nullable=False)
    video_outline: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    faqs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    representative_comments: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="content_brief")


class QuickAnalyzeJob(TimestampMixin, Base):
    __tablename__ = "quick_analyze_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','complete','failed')",
            name="ck_quick_analyze_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    youtube_video_url: Mapped[str] = mapped_column(Text, nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    knowledge_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued", nullable=False)
    comments_analyzed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    content_requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    existing_answer_matches: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    unanswered_requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    top_topics: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    top_opportunities: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    top_question_topics: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    top_request_topics: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    sentiment_summary: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)
    top_matches: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    video: Mapped[Video | None] = relationship()
    knowledge_channel: Mapped[Channel | None] = relationship()
    comments: Mapped[list["QuickAnalyzeComment"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class QuickAnalyzeComment(Base):
    __tablename__ = "quick_analyze_comments"
    __table_args__ = (
        Index("uq_quick_analyze_comments_job_comment", "job_id", "comment_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("quick_analyze_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[QuickAnalyzeJob] = relationship(back_populates="comments")
    comment: Mapped[Comment] = relationship(back_populates="quick_analyze_memberships")
