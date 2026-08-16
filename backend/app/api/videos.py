from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.video import VideoIndexRequest, VideoIndexResponse, VideoRead
from app.services.embeddings import EmbeddingProviderError
from app.services.video_indexing import (
    EmptyVideoContentError,
    VideoIndexingService,
    VideoNotFoundError,
    VideosService,
)

router = APIRouter(prefix="/api/videos", tags=["videos"])


def video_read(video: object, chunk_count: int) -> VideoRead:
    data = {column.name: getattr(video, column.name) for column in video.__table__.columns}
    data.update(
        index_status="indexed" if chunk_count else "pending",
        indexed_chunk_count=chunk_count,
    )
    return VideoRead.model_validate(data)


def get_video_indexing_service(db: Annotated[Session, Depends(get_db)]) -> VideoIndexingService:
    return VideoIndexingService(db, get_settings())


def get_videos_service(db: Annotated[Session, Depends(get_db)]) -> VideosService:
    return VideosService(db)


@router.post("/{video_id}/index", response_model=VideoIndexResponse)
def index_video(
    video_id: int,
    service: Annotated[VideoIndexingService, Depends(get_video_indexing_service)],
    request: Annotated[VideoIndexRequest | None, Body()] = None,
) -> VideoIndexResponse:
    settings = get_settings()
    try:
        result = service.index(video_id, request.transcript if request else None)
    except VideoNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "video_not_found", "message": "Video not found"},
        ) from exc
    except EmptyVideoContentError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_video_content", "message": str(exc)},
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "embedding_unavailable", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to index video"},
        ) from exc
    return VideoIndexResponse(
        video_id=result.video_id,
        indexed=True,
        chunk_count=result.chunk_count,
        embedding_model=settings.embedding_model,
        embedding_dimension=settings.embedding_dimension,
    )


@router.get("/{video_id}", response_model=VideoRead)
def get_video(
    video_id: int,
    service: Annotated[VideosService, Depends(get_videos_service)],
) -> VideoRead:
    result = service.get_with_index_status(video_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "video_not_found", "message": "Video not found"},
        )
    video, chunk_count = result
    return video_read(video, chunk_count)


@router.get("", response_model=list[VideoRead])
def list_videos(
    service: Annotated[VideosService, Depends(get_videos_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[VideoRead]:
    return [video_read(video, chunks) for video, chunks in service.list_creator_videos(offset, limit)]
