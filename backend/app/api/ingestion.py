import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.ingestion import IngestionResponse, YouTubeCommentIngestRequest
from app.services.classifier import ClassificationProviderError, InvalidClassificationError
from app.services.comment_analysis import CommentNotFoundError
from app.services.comment_processing import CommentProcessingService
from app.services.embeddings import EmbeddingProviderError
from app.services.ingestion import IngestionService
from app.services.reply_generator import InvalidGeneratedReplyError, ReplyProviderError

router = APIRouter(prefix="/api/youtube/comments", tags=["youtube-ingestion"])


def authenticate_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = get_settings().internal_api_key.get_secret_value()
    if x_internal_api_key is None or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_api_key", "message": "Invalid internal API key"},
        )


def get_ingestion_service(db: Annotated[Session, Depends(get_db)]) -> IngestionService:
    return IngestionService(db)


def get_processing_service(db: Annotated[Session, Depends(get_db)]) -> CommentProcessingService:
    return CommentProcessingService(db, get_settings())


@router.post("/ingest", response_model=IngestionResponse, response_model_exclude_none=True)
def ingest_comment(
    payload: YouTubeCommentIngestRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    processor: Annotated[CommentProcessingService, Depends(get_processing_service)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> IngestionResponse:
    """Persist a YouTube comment and let FastAPI run the AI pipeline.

    n8n is intentionally only the YouTube transport layer. Duplicate comments are
    safe: processing returns the cached result, and a previously failed comment can
    be retried on a later poll.
    """
    try:
        result = service.ingest(payload)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to persist ingestion event"},
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
            detail={"code": "ingestion_error", "message": "Comment ingestion returned no id"},
        )

    try:
        processed = processor.process(result.comment_id)
    except CommentNotFoundError as exc:
        raise HTTPException(404, detail={"code": "comment_not_found", "message": "Comment not found"}) from exc
    except InvalidClassificationError as exc:
        raise HTTPException(502, detail={"code": "invalid_model_response", "message": str(exc)}) from exc
    except ClassificationProviderError as exc:
        raise HTTPException(503, detail={"code": "classification_unavailable", "message": str(exc)}) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(503, detail={"code": "embedding_unavailable", "message": str(exc)}) from exc
    except InvalidGeneratedReplyError as exc:
        raise HTTPException(502, detail={"code": "invalid_model_response", "message": str(exc)}) from exc
    except ReplyProviderError as exc:
        raise HTTPException(503, detail={"code": "reply_generation_unavailable", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={"code": "database_error", "message": "Unable to process comment"}) from exc

    return IngestionResponse(
        status="accepted" if result.new_comment else "already_exists",
        new_comment=result.new_comment,
        comment_id=result.comment_id,
        processing_status=processed.status,
        outcome=processed.outcome,
        analysis_id=processed.analysis_id,
        match_found=processed.match_found,
        reply_id=processed.reply_id,
        opportunities_rebuilt=processed.opportunities_rebuilt,
        cached=processed.cached,
    )
