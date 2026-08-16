import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.ingestion import (
    IngestionResponse,
    YouTubeCommentIngestRequest,
)
from app.services.ingestion import IngestionService

router = APIRouter(
    prefix="/api/youtube/comments",
    tags=["youtube-ingestion"],
)


def authenticate_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().internal_api_key.get_secret_value()

    if (
        x_internal_api_key is None
        or not secrets.compare_digest(
            x_internal_api_key,
            expected,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_api_key",
                "message": "Invalid internal API key",
            },
        )


def get_ingestion_service(
    db: Annotated[Session, Depends(get_db)],
) -> IngestionService:
    return IngestionService(db)


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    response_model_exclude_none=True,
)
def ingest_comment(
    payload: YouTubeCommentIngestRequest,
    service: Annotated[
        IngestionService,
        Depends(get_ingestion_service),
    ],
    _: Annotated[
        None,
        Depends(authenticate_internal_api_key),
    ],
) -> IngestionResponse:
    """Persist/deduplicate a YouTube comment only.

    AI processing is intentionally separated into
    POST /api/comments/{comment_id}/process.

    This keeps YouTube ingestion healthy even when Gemini is rate-limited
    or temporarily unavailable. n8n can safely call the process endpoint
    after ingestion; duplicate completed comments are returned from cache
    by the processing service, while failed comments can be retried.
    """

    try:
        result = service.ingest(payload)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to persist ingestion event",
            },
        ) from exc

    if result.video_sync_required:
        return IngestionResponse(
            status="video_sync_required",
            new_comment=False,
            youtube_video_id=result.youtube_video_id,
        )

    if result.comment_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "ingestion_error",
                "message": "Comment ingestion returned no id",
            },
        )

    return IngestionResponse(
        status=(
            "accepted"
            if result.new_comment
            else "already_exists"
        ),
        new_comment=result.new_comment,
        comment_id=result.comment_id,
        processing_status=(
            "pending"
            if result.new_comment
            else None
        ),
    )
