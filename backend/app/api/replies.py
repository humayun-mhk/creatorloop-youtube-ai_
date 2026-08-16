from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.api.ingestion import authenticate_internal_api_key
from app.database.session import get_db
from app.schemas.reply import ReplyApprovalRequest, ReplyRead
from app.services.n8n_publisher import (
    PublishingConfigurationError,
    PublishingTimeoutError,
    PublishingUnavailableError,
    YouTubePublishingError,
)
from app.services.reply_approval import (
    InvalidReplyTransitionError,
    ReplyApprovalService,
    ReplyNotFoundError as ApprovalReplyNotFoundError,
)
from app.services.replies import (
    CommentNotFoundError,
    RepliesService,
    ReplyNotEligibleError,
    ReplySuggestionService,
)
from app.services.reply_generator import InvalidGeneratedReplyError, ReplyProviderError

reply_router = APIRouter(prefix="/api/replies", tags=["replies"])
comment_reply_router = APIRouter(prefix="/api/comments", tags=["replies"])


def get_reply_suggestion_service(
    db: Annotated[Session, Depends(get_db)],
) -> ReplySuggestionService:
    return ReplySuggestionService(db, get_settings())


def get_replies_service(db: Annotated[Session, Depends(get_db)]) -> RepliesService:
    return RepliesService(db)


def get_reply_approval_service(
    db: Annotated[Session, Depends(get_db)],
) -> ReplyApprovalService:
    return ReplyApprovalService(db, get_settings())


@reply_router.post("/{reply_id}/approve", response_model=ReplyRead)
def approve_reply(
    reply_id: int,
    service: Annotated[ReplyApprovalService, Depends(get_reply_approval_service)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
    request: Annotated[ReplyApprovalRequest | None, Body()] = None,
) -> ReplyRead:
    try:
        return ReplyRead.model_validate(
            service.approve(reply_id, request.reply if request else None)
        )
    except ApprovalReplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "reply_not_found", "message": "Reply suggestion not found"}) from exc
    except InvalidReplyTransitionError as exc:
        raise HTTPException(status_code=409, detail={"code": "invalid_reply_state", "message": str(exc)}) from exc
    except PublishingConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "publishing_not_configured", "message": str(exc)}) from exc
    except PublishingTimeoutError as exc:
        raise HTTPException(status_code=504, detail={"code": "publishing_timeout", "message": str(exc)}) from exc
    except PublishingUnavailableError as exc:
        raise HTTPException(status_code=502, detail={"code": "publishing_unavailable", "message": str(exc)}) from exc
    except YouTubePublishingError as exc:
        raise HTTPException(status_code=502, detail={"code": "youtube_publishing_failed", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail={"code": "database_error", "message": "Unable to approve reply"}) from exc


@reply_router.post("/{reply_id}/ignore", response_model=ReplyRead)
def ignore_reply(
    reply_id: int,
    service: Annotated[ReplyApprovalService, Depends(get_reply_approval_service)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> ReplyRead:
    try:
        return ReplyRead.model_validate(service.ignore(reply_id))
    except ApprovalReplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "reply_not_found", "message": "Reply suggestion not found"}) from exc
    except InvalidReplyTransitionError as exc:
        raise HTTPException(status_code=409, detail={"code": "invalid_reply_state", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail={"code": "database_error", "message": "Unable to ignore reply"}) from exc


@comment_reply_router.post("/{comment_id}/reply-suggestion", response_model=ReplyRead)
def generate_reply_suggestion(
    comment_id: int,
    service: Annotated[ReplySuggestionService, Depends(get_reply_suggestion_service)],
) -> ReplyRead:
    try:
        return ReplyRead.model_validate(service.generate(comment_id).reply)
    except CommentNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "comment_not_found", "message": "Comment not found"},
        ) from exc
    except ReplyNotEligibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "reply_not_eligible", "message": str(exc)},
        ) from exc
    except InvalidGeneratedReplyError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_model_response", "message": str(exc)},
        ) from exc
    except ReplyProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "reply_generation_unavailable", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to generate reply"},
        ) from exc


@reply_router.get("", response_model=list[ReplyRead])
def list_replies(
    service: Annotated[RepliesService, Depends(get_replies_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ReplyRead]:
    return [ReplyRead.model_validate(reply) for reply in service.list(offset, limit)]


@reply_router.get("/{reply_id}", response_model=ReplyRead)
def get_reply(
    reply_id: int,
    service: Annotated[RepliesService, Depends(get_replies_service)],
) -> ReplyRead:
    reply = service.get(reply_id)
    if reply is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "reply_not_found", "message": "Reply suggestion not found"},
        )
    return ReplyRead.model_validate(reply)
