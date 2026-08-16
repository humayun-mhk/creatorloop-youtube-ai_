import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.ingestion import authenticate_internal_api_key
from app.config import get_settings
from app.database.session import get_db
from app.schemas.quick_analyze import (
    QuickAnalyzeCommentRequest,
    QuickAnalyzeCommentResponse,
    QuickAnalyzeCompleteRequest,
    QuickAnalyzeFailureRequest,
    QuickAnalyzeRequest,
    QuickAnalyzeResult,
    QuickAnalyzeStarted,
    QuickAnalyzeVideoRequest,
)
from app.services.quick_analyze import (
    InvalidYouTubeUrlError,
    QuickAnalyzeNotFoundError,
    QuickAnalyzeService,
)
from app.services.quick_analyze_client import (
    N8NQuickAnalyzeClient,
    QuickAnalyzeConfigurationError,
    QuickAnalyzeTimeoutError,
    QuickAnalyzeUnavailableError,
)

router = APIRouter(prefix="/api/quick-analyze", tags=["quick-analyze"])


def get_quick_analyze_service(
    db: Annotated[Session, Depends(get_db)],
) -> QuickAnalyzeService:
    return QuickAnalyzeService(db, get_settings())


def get_quick_analyze_client() -> N8NQuickAnalyzeClient:
    return N8NQuickAnalyzeClient(get_settings())


def authenticate_monitor_secret(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    configured = get_settings().n8n_comment_monitor_secret
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected or x_internal_api_key is None or not secrets.compare_digest(
        x_internal_api_key, expected
    ):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_monitor_key", "message": "Invalid monitor key"},
        )


@router.post("", response_model=QuickAnalyzeStarted, status_code=202)
def start_quick_analyze(
    payload: QuickAnalyzeRequest,
    request: Request,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
    client: Annotated[N8NQuickAnalyzeClient, Depends(get_quick_analyze_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> QuickAnalyzeStarted:
    try:
        job = service.create(payload.youtube_video_url)
        client.start(job.public_id, job.youtube_video_id, str(request.base_url))
        service.mark_running(job.public_id)
        return QuickAnalyzeStarted(
            id=job.public_id, status="running", youtube_video_id=job.youtube_video_id
        )
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(422, detail={"code": "invalid_youtube_url", "message": str(exc)}) from exc
    except QuickAnalyzeConfigurationError as exc:
        if "job" in locals():
            service.fail(job.public_id, str(exc))
        raise HTTPException(503, detail={"code": "quick_analyze_not_configured", "message": str(exc)}) from exc
    except QuickAnalyzeTimeoutError as exc:
        if "job" in locals():
            service.fail(job.public_id, str(exc))
        raise HTTPException(504, detail={"code": "quick_analyze_timeout", "message": str(exc)}) from exc
    except QuickAnalyzeUnavailableError as exc:
        if "job" in locals():
            service.fail(job.public_id, str(exc))
        raise HTTPException(502, detail={"code": "quick_analyze_unavailable", "message": str(exc)}) from exc


@router.get("/{public_id}", response_model=QuickAnalyzeResult)
def get_quick_analyze(
    public_id: str,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
) -> QuickAnalyzeResult:
    job = service.get(public_id)
    if job is None:
        raise HTTPException(404, detail={"code": "quick_analyze_not_found", "message": "Quick Analyze job not found"})
    return service.response(job)


@router.post("/{public_id}/internal/video", status_code=204)
def attach_quick_analyze_video(
    public_id: str,
    payload: QuickAnalyzeVideoRequest,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
    _: Annotated[None, Depends(authenticate_monitor_secret)],
) -> None:
    try:
        service.attach_video(public_id, payload.video)
    except QuickAnalyzeNotFoundError as exc:
        raise HTTPException(404, detail={"code": "quick_analyze_not_found", "message": "Quick Analyze job not found"}) from exc
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(409, detail={"code": "video_mismatch", "message": str(exc)}) from exc


@router.post("/{public_id}/internal/comments", response_model=QuickAnalyzeCommentResponse)
def ingest_quick_analyze_comment(
    public_id: str,
    payload: QuickAnalyzeCommentRequest,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
    _: Annotated[None, Depends(authenticate_monitor_secret)],
) -> QuickAnalyzeCommentResponse:
    try:
        new_comment, comment_id, processing = service.ingest_and_process(
            public_id, payload.ingestion
        )
        return QuickAnalyzeCommentResponse(
            new_comment=new_comment, comment_id=comment_id, processing=processing
        )
    except QuickAnalyzeNotFoundError as exc:
        raise HTTPException(404, detail={"code": "quick_analyze_not_found", "message": "Quick Analyze job not found"}) from exc
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(409, detail={"code": "video_mismatch", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={"code": "database_error", "message": "Unable to import Quick Analyze comment"}) from exc


@router.post("/{public_id}/internal/complete", response_model=QuickAnalyzeResult)
def complete_quick_analyze(
    public_id: str,
    payload: QuickAnalyzeCompleteRequest,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
    _: Annotated[None, Depends(authenticate_monitor_secret)],
) -> QuickAnalyzeResult:
    try:
        service.complete(public_id)
        job = service.get(public_id)
        assert job is not None
        return service.response(job)
    except QuickAnalyzeNotFoundError as exc:
        raise HTTPException(404, detail={"code": "quick_analyze_not_found", "message": "Quick Analyze job not found"}) from exc


@router.post("/{public_id}/internal/fail", response_model=QuickAnalyzeResult)
def fail_quick_analyze(
    public_id: str,
    payload: QuickAnalyzeFailureRequest,
    service: Annotated[QuickAnalyzeService, Depends(get_quick_analyze_service)],
    _: Annotated[None, Depends(authenticate_monitor_secret)],
) -> QuickAnalyzeResult:
    try:
        service.fail(public_id, payload.message)
        job = service.get(public_id)
        assert job is not None
        return service.response(job)
    except QuickAnalyzeNotFoundError as exc:
        raise HTTPException(404, detail={"code": "quick_analyze_not_found", "message": "Quick Analyze job not found"}) from exc
