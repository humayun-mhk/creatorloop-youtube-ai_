from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.semantic_search import MatchedChunk, MatchedVideo, SemanticMatchResponse
from app.services.embeddings import EmbeddingProviderError
from app.services.semantic_search import CommentNotFoundError, SemanticSearchResult, SemanticSearchService

router = APIRouter(prefix="/api/comments", tags=["semantic-search"])


def get_semantic_search_service(
    db: Annotated[Session, Depends(get_db)],
) -> SemanticSearchService:
    return SemanticSearchService(db, get_settings())


def response_from_result(result: SemanticSearchResult) -> SemanticMatchResponse:
    best = result.best
    return SemanticMatchResponse(
        match_found=result.match_found,
        similarity=best.similarity if best else None,
        video=(
            MatchedVideo(
                id=best.video_id,
                youtube_video_id=best.youtube_video_id,
                title=best.video_title,
            )
            if result.match_found and best
            else None
        ),
        chunk=(
            MatchedChunk(text=best.text, start_time=best.start_time)
            if result.match_found and best
            else None
        ),
    )


@router.post(
    "/{comment_id}/semantic-match",
    response_model=SemanticMatchResponse,
)
def semantic_match_comment(
    comment_id: int,
    service: Annotated[SemanticSearchService, Depends(get_semantic_search_service)],
) -> SemanticMatchResponse:
    try:
        return response_from_result(service.match_comment(comment_id))
    except CommentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "comment_not_found", "message": "Comment not found"},
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "embedding_unavailable", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to match comment"},
        ) from exc
