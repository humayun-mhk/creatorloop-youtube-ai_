from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.analysis import AnalysisRead
from app.schemas.comment import CommentRead
from app.services.classifier import ClassificationProviderError, InvalidClassificationError
from app.services.comment_analysis import CommentAnalysisService, CommentNotFoundError
from app.services.comments import CommentsService
from app.api.ingestion import authenticate_internal_api_key
from app.schemas.processing import CommentProcessResponse
from app.services.comment_processing import CommentProcessingService
from app.services.embeddings import EmbeddingProviderError
from app.services.reply_generator import InvalidGeneratedReplyError, ReplyProviderError

router = APIRouter(prefix="/api/comments", tags=["comments"])


def get_analysis_service(db: Annotated[Session, Depends(get_db)]) -> CommentAnalysisService:
    return CommentAnalysisService(db, get_settings())


def get_comments_service(db: Annotated[Session, Depends(get_db)]) -> CommentsService:
    return CommentsService(db)


def get_comment_processing_service(
    db: Annotated[Session, Depends(get_db)],
) -> CommentProcessingService:
    return CommentProcessingService(db, get_settings())


@router.post("/{comment_id}/process", response_model=CommentProcessResponse)
def process_comment(
    comment_id: int,
    service: Annotated[CommentProcessingService, Depends(get_comment_processing_service)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> CommentProcessResponse:
    try:
        return CommentProcessResponse.model_validate(service.process(comment_id).__dict__)
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


@router.post("/{comment_id}/analyze", response_model=AnalysisRead)
def analyze_comment(comment_id: int, service: Annotated[CommentAnalysisService, Depends(get_analysis_service)]) -> AnalysisRead:
    try:
        return AnalysisRead.model_validate(service.analyze(comment_id).analysis)
    except CommentNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "comment_not_found", "message": "Comment not found"}) from exc
    except InvalidClassificationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"code": "invalid_model_response", "message": "Gemini returned invalid classification data"}) from exc
    except ClassificationProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "classification_unavailable", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "database_error", "message": "Unable to analyze comment"}) from exc


@router.get("", response_model=list[CommentRead])
def list_comments(
    service: Annotated[CommentsService, Depends(get_comments_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CommentRead]:
    return [CommentRead.model_validate(item) for item in service.list(offset, limit)]


@router.get("/{comment_id}", response_model=CommentRead)
def get_comment(comment_id: int, service: Annotated[CommentsService, Depends(get_comments_service)]) -> CommentRead:
    comment = service.get(comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail={"code": "comment_not_found", "message": "Comment not found"})
    return CommentRead.model_validate(comment)
