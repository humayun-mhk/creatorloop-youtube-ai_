import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.ingestion import authenticate_internal_api_key
from app.config import get_settings
from app.database.session import get_db
from app.schemas.analysis import AnalysisRead
from app.schemas.comment import CommentRead
from app.schemas.processing import CommentProcessResponse
from app.services.classifier import (
    ClassificationProviderError,
    InvalidClassificationError,
)
from app.services.comment_analysis import (
    CommentAnalysisService,
    CommentNotFoundError,
)
from app.services.comment_processing import CommentProcessingService
from app.services.comments import CommentsService
from app.services.embeddings import EmbeddingProviderError
from app.services.reply_generator import (
    InvalidGeneratedReplyError,
    ReplyProviderError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/comments",
    tags=["comments"],
)


def get_analysis_service(
    db: Annotated[Session, Depends(get_db)],
) -> CommentAnalysisService:
    return CommentAnalysisService(
        db,
        get_settings(),
    )


def get_comments_service(
    db: Annotated[Session, Depends(get_db)],
) -> CommentsService:
    return CommentsService(db)


def get_comment_processing_service(
    db: Annotated[Session, Depends(get_db)],
) -> CommentProcessingService:
    return CommentProcessingService(
        db,
        get_settings(),
    )


def _deferred(
    *,
    comment_id: int,
    code: str,
    exc: Exception,
) -> CommentProcessResponse:
    logger.warning(
        "Comment %s processing deferred: %s: %s",
        comment_id,
        code,
        exc,
    )

    return CommentProcessResponse(
        comment_id=comment_id,
        status="deferred",
        outcome=code,
        error_code=code,
        error_message=str(exc),
    )


@router.post(
    "/{comment_id}/process",
    response_model=CommentProcessResponse,
)
def process_comment(
    comment_id: int,
    service: Annotated[
        CommentProcessingService,
        Depends(get_comment_processing_service),
    ],
    _: Annotated[
        None,
        Depends(authenticate_internal_api_key),
    ],
) -> CommentProcessResponse:
    """Run the AI pipeline for one stored comment.

    Provider failures return a successful 'deferred' response instead of
    killing the n8n workflow. CommentProcessingService marks the pipeline
    failed, so the same comment can be retried on a later channel poll.
    """

    try:
        result = service.process(
            comment_id,
            rebuild_opportunities=False,
        )
        return CommentProcessResponse.model_validate(
            result.__dict__
        )

    except CommentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "comment_not_found",
                "message": "Comment not found",
            },
        ) from exc

    except InvalidClassificationError as exc:
        return _deferred(
            comment_id=comment_id,
            code="invalid_classification",
            exc=exc,
        )

    except ClassificationProviderError as exc:
        return _deferred(
            comment_id=comment_id,
            code="classification_unavailable",
            exc=exc,
        )

    except EmbeddingProviderError as exc:
        return _deferred(
            comment_id=comment_id,
            code="embedding_unavailable",
            exc=exc,
        )

    except InvalidGeneratedReplyError as exc:
        return _deferred(
            comment_id=comment_id,
            code="invalid_generated_reply",
            exc=exc,
        )

    except ReplyProviderError as exc:
        return _deferred(
            comment_id=comment_id,
            code="reply_generation_unavailable",
            exc=exc,
        )

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "database_error",
                "message": "Unable to process comment",
            },
        ) from exc


@router.post(
    "/{comment_id}/analyze",
    response_model=AnalysisRead,
)
def analyze_comment(
    comment_id: int,
    service: Annotated[
        CommentAnalysisService,
        Depends(get_analysis_service),
    ],
) -> AnalysisRead:
    try:
        return AnalysisRead.model_validate(
            service.analyze(comment_id).analysis
        )
    except CommentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "comment_not_found",
                "message": "Comment not found",
            },
        ) from exc
    except InvalidClassificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invalid_model_response",
                "message": (
                    "Gemini returned invalid classification data"
                ),
            },
        ) from exc
    except ClassificationProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "classification_unavailable",
                "message": str(exc),
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to analyze comment",
            },
        ) from exc


@router.get(
    "",
    response_model=list[CommentRead],
)
def list_comments(
    service: Annotated[
        CommentsService,
        Depends(get_comments_service),
    ],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CommentRead]:
    return [
        CommentRead.model_validate(item)
        for item in service.list(offset, limit)
    ]


@router.get(
    "/{comment_id}",
    response_model=CommentRead,
)
def get_comment(
    comment_id: int,
    service: Annotated[
        CommentsService,
        Depends(get_comments_service),
    ],
) -> CommentRead:
    comment = service.get(comment_id)

    if comment is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "comment_not_found",
                "message": "Comment not found",
            },
        )

    return CommentRead.model_validate(comment)
