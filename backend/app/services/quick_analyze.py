from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database.models import (
    Channel, Comment, CommentAnalysis, QuickAnalyzeComment, QuickAnalyzeJob,
    SemanticMatch, Video, VideoChunk,
)
from app.schemas.quick_analyze import QuickAnalyzeResult, QuickAnalyzeSummary, QuickAnalyzeVideo
from app.schemas.ingestion import VideoPayload, YouTubeCommentIngestRequest
from app.schemas.processing import CommentProcessResponse
from app.services.comment_processing import CommentProcessingService
from app.services.ingestion import IngestionService

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class InvalidYouTubeUrlError(ValueError):
    pass


class QuickAnalyzeNotFoundError(LookupError):
    pass


def parse_youtube_video_url(value: str) -> tuple[str, str]:
    try:
        parsed = urlparse(value.strip())
    except ValueError as exc:
        raise InvalidYouTubeUrlError("Invalid YouTube video URL") from exc
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise InvalidYouTubeUrlError("A valid HTTPS YouTube video URL is required")
    host = (parsed.hostname or "").lower()
    video_id: str | None = None
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            values = parse_qs(parsed.query).get("v", [])
            video_id = values[0] if len(values) == 1 else None
        elif parsed.path.startswith("/shorts/"):
            parts = [part for part in parsed.path.split("/") if part]
            video_id = parts[1] if len(parts) == 2 else None
    elif host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[0] if len(parts) == 1 else None
    if video_id is None or not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise InvalidYouTubeUrlError("Unsupported or invalid YouTube video URL")
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


class QuickAnalyzeService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def create(self, youtube_video_url: str) -> QuickAnalyzeJob:
        video_id, canonical_url = parse_youtube_video_url(youtube_video_url)
        with self.session.begin():
            knowledge_channel_id = self.session.scalar(
                select(Channel.id).order_by(Channel.id.asc()).limit(1)
            )
            job = QuickAnalyzeJob(
                public_id=str(uuid.uuid4()),
                youtube_video_url=canonical_url,
                youtube_video_id=video_id,
                knowledge_channel_id=knowledge_channel_id,
                status="queued",
            )
            self.session.add(job)
            self.session.flush()
            return job

    def mark_running(self, public_id: str) -> None:
        with self.session.begin():
            job = self._locked(public_id)
            job.status = "running"
            job.error_message = None

    def fail(self, public_id: str, message: str) -> QuickAnalyzeJob:
        with self.session.begin():
            job = self._locked(public_id)
            job.status = "failed"
            job.error_message = message
            job.completed_at = datetime.now(timezone.utc)
            return job

    def ingest_and_process(
        self, public_id: str, payload: YouTubeCommentIngestRequest
    ) -> tuple[bool, int, CommentProcessResponse]:
        with self.session.begin():
            job = self._locked(public_id)
            if payload.comment.video_id != job.youtube_video_id:
                raise InvalidYouTubeUrlError("Comment video does not match the Quick Analyze job")
            knowledge_channel_id = job.knowledge_channel_id

        result = IngestionService(self.session).ingest(payload)
        if result.video_sync_required or result.comment_id is None:
            raise InvalidYouTubeUrlError("Quick Analyze requires complete video metadata")

        with self.session.begin():
            job = self._locked(public_id)
            comment = self.session.get(Comment, result.comment_id)
            if comment is None:
                raise QuickAnalyzeNotFoundError
            job.video_id = comment.video_id
            job.status = "running"
            comment.knowledge_channel_id = knowledge_channel_id
            self.session.execute(
                insert(QuickAnalyzeComment)
                .values(job_id=job.id, comment_id=comment.id)
                .on_conflict_do_nothing(
                    index_elements=[QuickAnalyzeComment.job_id, QuickAnalyzeComment.comment_id]
                )
            )

        processed = CommentProcessingService(
            self.session, self.settings
        ).process(result.comment_id, rebuild_opportunities=False)
        return result.new_comment, result.comment_id, CommentProcessResponse.model_validate(processed.__dict__)

    def attach_video(self, public_id: str, payload: VideoPayload) -> Video:
        with self.session.begin():
            job = self._locked(public_id)
            if payload.video_id != job.youtube_video_id:
                raise InvalidYouTubeUrlError("Video metadata does not match the Quick Analyze job")
            connected_channel_id = self.session.scalar(
                select(Channel.id).where(Channel.youtube_channel_id == payload.channel_id)
            )
            values = payload.model_dump(exclude={"found", "video_id"})
            values.update(
                youtube_video_id=payload.video_id,
                youtube_url=payload.youtube_url or job.youtube_video_url,
                creator_channel_id=connected_channel_id,
            )
            updates = {key: value for key, value in values.items() if key != "youtube_video_id"}
            updates["updated_at"] = func.now()
            video_id = self.session.execute(
                insert(Video)
                .values(**values)
                .on_conflict_do_update(index_elements=[Video.youtube_video_id], set_=updates)
                .returning(Video.id)
            ).scalar_one()
            job.video_id = video_id
            job.status = "running"
            return self.session.get(Video, video_id)

    def complete(self, public_id: str) -> QuickAnalyzeJob:
        with self.session.begin():
            job = self._locked(public_id)
            rows = self.session.execute(
                select(Comment, CommentAnalysis, SemanticMatch)
                .join(QuickAnalyzeComment, QuickAnalyzeComment.comment_id == Comment.id)
                .outerjoin(CommentAnalysis, CommentAnalysis.comment_id == Comment.id)
                .outerjoin(SemanticMatch, SemanticMatch.comment_id == Comment.id)
                .where(QuickAnalyzeComment.job_id == job.id)
            ).all()
            analyzed = [(comment, analysis, match) for comment, analysis, match in rows if analysis]
            eligible = [
                row for row in analyzed
                if row[1].intent in {"question", "content_request"}
                and (row[1].is_question or row[1].is_content_request)
            ]
            unmatched = [row for row in eligible if row[2] is not None and not row[2].match_found]
            topic_counts = Counter(row[1].topic for row in analyzed)
            unmet_counts = Counter(row[1].topic for row in unmatched)
            question_counts = Counter(row[1].topic for row in analyzed if row[1].is_question)
            request_counts = Counter(row[1].topic for row in analyzed if row[1].is_content_request)
            sentiment_counts = Counter(row[1].sentiment for row in analyzed)
            matched_video_counts: Counter[tuple[int, str, str]] = Counter()
            for _, _, match in analyzed:
                if not match or not match.match_found or not match.video_chunk_id:
                    continue
                chunk = self.session.get(VideoChunk, match.video_chunk_id)
                video = self.session.get(Video, chunk.video_id) if chunk else None
                if video:
                    url = video.youtube_url or f"https://www.youtube.com/watch?v={video.youtube_video_id}"
                    matched_video_counts[(video.id, video.title, url)] += 1
            job.comments_analyzed = len(analyzed)
            job.questions = sum(1 for _, analysis, _ in analyzed if analysis.is_question)
            job.content_requests = sum(1 for _, analysis, _ in analyzed if analysis.is_content_request)
            job.existing_answer_matches = sum(1 for _, _, match in analyzed if match and match.match_found)
            job.unanswered_requests = len(unmatched)
            job.top_topics = [
                {"topic": topic, "count": count}
                for topic, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            ]
            job.top_opportunities = [
                {"topic": topic, "request_count": count}
                for topic, count in sorted(unmet_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            ]
            job.top_question_topics = self._rank_counts(question_counts)
            job.top_request_topics = self._rank_counts(request_counts)
            job.sentiment_summary = {name: sentiment_counts.get(name, 0) for name in ("positive", "neutral", "negative")}
            job.top_matches = [
                {"video_id": video_id, "title": title, "youtube_url": url, "match_count": count}
                for (video_id, title, url), count in sorted(matched_video_counts.items(), key=lambda item: (-item[1], item[0][1]))[:10]
            ]
            job.status = "complete"
            job.completed_at = datetime.now(timezone.utc)
            return job

    def get(self, public_id: str) -> QuickAnalyzeJob | None:
        return self.session.scalar(
            select(QuickAnalyzeJob)
            .options(selectinload(QuickAnalyzeJob.video))
            .where(QuickAnalyzeJob.public_id == public_id)
        )

    def response(self, job: QuickAnalyzeJob) -> QuickAnalyzeResult:
        video = None
        if job.video is not None:
            video = QuickAnalyzeVideo(
                id=job.video.id,
                youtube_video_id=job.video.youtube_video_id,
                youtube_url=job.video.youtube_url,
                title=job.video.title,
                channel_title=job.video.channel_title,
                thumbnail_url=job.video.thumbnail_url,
            )
        return QuickAnalyzeResult(
            id=job.public_id,
            status=job.status,
            youtube_video_url=job.youtube_video_url,
            youtube_video_id=job.youtube_video_id,
            video=video,
            summary=QuickAnalyzeSummary(
                comments_analyzed=job.comments_analyzed,
                questions=job.questions,
                content_requests=job.content_requests,
                existing_answer_matches=job.existing_answer_matches,
                unanswered_requests=job.unanswered_requests,
            ),
            top_topics=job.top_topics,
            top_opportunities=job.top_opportunities,
            top_question_topics=job.top_question_topics,
            top_request_topics=job.top_request_topics,
            sentiment_summary=job.sentiment_summary,
            top_matches=job.top_matches,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )

    def _locked(self, public_id: str) -> QuickAnalyzeJob:
        job = self.session.execute(
            select(QuickAnalyzeJob)
            .where(QuickAnalyzeJob.public_id == public_id)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            raise QuickAnalyzeNotFoundError
        return job

    @staticmethod
    def _rank_counts(counts: Counter) -> list[dict]:
        return [
            {"topic": topic, "count": count}
            for topic, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ]
