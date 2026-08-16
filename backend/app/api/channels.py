import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.ingestion import authenticate_internal_api_key
from app.config import get_settings
from app.database.models import Channel
from app.database.session import get_db
from app.schemas.channel import (
    ChannelActionResponse,
    ChannelConnectRequest,
    ChannelIdentity,
    ChannelRead,
    ChannelSyncProgress,
    ChannelSyncRead,
    CurrentChannelResponse,
    VideoBatchImportRequest,
    VideoBatchImportResponse,
)
from app.services.channel_sync_client import (
    ChannelSyncConfigurationError,
    ChannelSyncTimeoutError,
    ChannelSyncUnavailableError,
    InvalidChannelSyncResponseError,
    N8NChannelSyncClient,
)
from app.services.channels import (
    ChannelMismatchError,
    ChannelNotFoundError,
    ChannelsService,
)
from app.services.embeddings import EmbeddingProviderError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


def get_channels_service(db: Annotated[Session, Depends(get_db)]) -> ChannelsService:
    return ChannelsService(db, get_settings())


def get_channel_sync_client() -> N8NChannelSyncClient:
    return N8NChannelSyncClient(get_settings())


def _callback_base_url(request: Request) -> str:
    """
    Return a normalized public callback base URL for n8n.

    Render/Vercel proxy headers should make request.base_url resolve to the
    public HTTPS host. Removing the trailing slash prevents accidental //api
    callback URLs inside n8n.
    """
    return str(request.base_url).rstrip("/")


def _fail_sync_safely(service: ChannelsService, channel_id: int) -> None:
    """
    Mark a channel sync as failed without hiding the original sync exception.
    """
    try:
        service.fail_sync(channel_id)
    except Exception:
        logger.exception(
            "Unable to mark channel sync as failed",
            extra={"channel_id": channel_id},
        )


def authenticate_channel_sync_webhook(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()

    configured = settings.n8n_channel_sync_webhook_secret
    monitor = settings.n8n_comment_monitor_secret

    expected_values = [
        item.get_secret_value()
        for item in (configured, monitor)
        if item is not None and item.get_secret_value()
    ]

    valid = (
        x_internal_api_key is not None
        and bool(expected_values)
        and any(
            secrets.compare_digest(x_internal_api_key, expected)
            for expected in expected_values
        )
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_sync_key",
                "message": "Invalid channel sync key",
            },
        )


def current_response(channel: Channel | None) -> CurrentChannelResponse:
    if channel is None:
        return CurrentChannelResponse(
            connected=False,
            channel=None,
            sync=None,
        )

    return CurrentChannelResponse(
        connected=True,
        channel=ChannelRead.model_validate(channel),
        sync=ChannelSyncRead(
            status=channel.sync_status,
            video_sync_status=channel.video_sync_status,
            comment_sync_status=channel.comment_sync_status,
            index_status=channel.index_status,
            videos_discovered=channel.videos_discovered,
            videos_indexed=channel.videos_indexed,
            comments_imported=channel.comments_imported,
            last_video_sync_at=channel.last_video_sync_at,
            last_comment_sync_at=channel.last_comment_sync_at,
            last_full_sync_at=channel.last_full_sync_at,
        ),
    )


@router.get("/current", response_model=CurrentChannelResponse)
def get_current_channel(
    service: Annotated[ChannelsService, Depends(get_channels_service)],
) -> CurrentChannelResponse:
    return current_response(service.current())


@router.post("/connect", response_model=CurrentChannelResponse)
def connect_channel(
    payload: ChannelConnectRequest,
    request: Request,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    client: Annotated[N8NChannelSyncClient, Depends(get_channel_sync_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> CurrentChannelResponse:
    callback_base_url = _callback_base_url(request)
    channel: Channel | None = None

    try:
        identity = client.connect(payload.target_channel, callback_base_url)

        channel = service.upsert(identity, status="connected")
        service.start_sync(channel.id)

        try:
            client.start_sync(
                channel.id,
                channel.youtube_channel_id,
                callback_base_url,
            )
        except Exception:
            _fail_sync_safely(service, channel.id)
            raise

        refreshed = service.get(channel.id)
        if refreshed is None:
            raise ChannelNotFoundError(
                f"Channel {channel.id} disappeared after connection"
            )

        return current_response(refreshed)

    except ChannelSyncConfigurationError as exc:
        logger.warning("Channel sync is not configured: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "sync_not_configured", "message": str(exc)},
        ) from exc

    except ChannelSyncTimeoutError as exc:
        logger.warning("Channel sync timed out: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "sync_timeout", "message": str(exc)},
        ) from exc

    except (ChannelSyncUnavailableError, InvalidChannelSyncResponseError) as exc:
        logger.warning("Channel sync service rejected/unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "sync_unavailable", "message": str(exc)},
        ) from exc

    except SQLAlchemyError as exc:
        if channel is not None:
            _fail_sync_safely(service, channel.id)
        logger.exception("Database error while connecting channel")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to connect channel",
            },
        ) from exc


@router.post(
    "/sync",
    response_model=ChannelActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_channel_sync(
    request: Request,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    client: Annotated[N8NChannelSyncClient, Depends(get_channel_sync_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> ChannelActionResponse:
    callback_base_url = _callback_base_url(request)

    try:
        channel = service.current()
    except SQLAlchemyError as exc:
        logger.exception("Database error while loading current channel")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to load connected channel",
            },
        ) from exc

    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "channel_not_connected",
                "message": "Connect a channel first",
            },
        )

    try:
        service.start_sync(channel.id)

        logger.info(
            "Starting n8n channel sync",
            extra={
                "channel_id": channel.id,
                "youtube_channel_id": channel.youtube_channel_id,
                "callback_base_url": callback_base_url,
            },
        )

        client.start_sync(
            channel.id,
            channel.youtube_channel_id,
            callback_base_url,
        )

    except ChannelSyncConfigurationError as exc:
        _fail_sync_safely(service, channel.id)
        logger.warning("Channel sync is not configured: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "sync_not_configured", "message": str(exc)},
        ) from exc

    except ChannelSyncTimeoutError as exc:
        _fail_sync_safely(service, channel.id)
        logger.warning("Channel sync timed out: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "sync_timeout", "message": str(exc)},
        ) from exc

    except (ChannelSyncUnavailableError, InvalidChannelSyncResponseError) as exc:
        _fail_sync_safely(service, channel.id)
        logger.warning("Channel sync service rejected/unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "sync_unavailable", "message": str(exc)},
        ) from exc

    except SQLAlchemyError as exc:
        _fail_sync_safely(service, channel.id)
        logger.exception(
            "Database error while starting channel sync",
            extra={"channel_id": channel.id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to start channel sync",
            },
        ) from exc

    except Exception as exc:
        _fail_sync_safely(service, channel.id)
        logger.exception(
            "Unexpected error while starting channel sync",
            extra={"channel_id": channel.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "sync_internal_error",
                "message": "Unexpected error while starting channel sync",
            },
        ) from exc

    return ChannelActionResponse(
        status="syncing",
        channel_id=channel.id,
    )


@router.post(
    "/{channel_id}/sync-video/{youtube_video_id}",
    response_model=ChannelActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_unknown_video(
    channel_id: int,
    youtube_video_id: str,
    request: Request,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    client: Annotated[N8NChannelSyncClient, Depends(get_channel_sync_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> ChannelActionResponse:
    callback_base_url = _callback_base_url(request)

    try:
        channel = service.get(channel_id)
    except SQLAlchemyError as exc:
        logger.exception(
            "Database error while loading channel for video sync",
            extra={"channel_id": channel_id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to load channel",
            },
        ) from exc

    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "channel_not_found",
                "message": "Channel not found",
            },
        )

    try:
        # The public-channel workflow currently supports connect/sync.
        # Until a dedicated single-video n8n action exists, a full sync is the
        # safe fallback for a newly discovered video.
        service.start_sync(channel_id)

        client.start_sync(
            channel_id,
            channel.youtube_channel_id,
            callback_base_url,
        )

    except ChannelSyncConfigurationError as exc:
        _fail_sync_safely(service, channel_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "sync_not_configured", "message": str(exc)},
        ) from exc

    except ChannelSyncTimeoutError as exc:
        _fail_sync_safely(service, channel_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "sync_timeout", "message": str(exc)},
        ) from exc

    except (ChannelSyncUnavailableError, InvalidChannelSyncResponseError) as exc:
        _fail_sync_safely(service, channel_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "sync_unavailable", "message": str(exc)},
        ) from exc

    except SQLAlchemyError as exc:
        _fail_sync_safely(service, channel_id)
        logger.exception(
            "Database error while starting video-triggered sync",
            extra={
                "channel_id": channel_id,
                "youtube_video_id": youtube_video_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_error",
                "message": "Unable to start video sync",
            },
        ) from exc

    except Exception as exc:
        _fail_sync_safely(service, channel_id)
        logger.exception(
            "Unexpected error while starting video-triggered sync",
            extra={
                "channel_id": channel_id,
                "youtube_video_id": youtube_video_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "sync_internal_error",
                "message": "Unexpected error while starting video sync",
            },
        ) from exc

    return ChannelActionResponse(
        status="syncing",
        channel_id=channel_id,
    )


@router.get("/{channel_id}/sync-status", response_model=CurrentChannelResponse)
def get_sync_status(
    channel_id: int,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
) -> CurrentChannelResponse:
    channel = service.get(channel_id)

    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "channel_not_found",
                "message": "Channel not found",
            },
        )

    return current_response(channel)


@router.post("/internal/resolve", response_model=CurrentChannelResponse)
def resolve_channel(
    identity: ChannelIdentity,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> CurrentChannelResponse:
    return current_response(service.upsert(identity, status="connected"))


@router.post(
    "/{channel_id}/internal/progress",
    response_model=CurrentChannelResponse,
)
def update_sync_progress(
    channel_id: int,
    progress: ChannelSyncProgress,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> CurrentChannelResponse:
    try:
        return current_response(service.apply_progress(channel_id, progress))
    except ChannelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "channel_not_found",
                "message": "Channel not found",
            },
        ) from exc


@router.post(
    "/{channel_id}/internal/videos",
    response_model=VideoBatchImportResponse,
)
def import_channel_videos(
    channel_id: int,
    payload: VideoBatchImportRequest,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> VideoBatchImportResponse:
    try:
        video_ids, discovered, indexed = service.import_videos(
            channel_id,
            payload,
        )
    except ChannelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "channel_not_found",
                "message": "Channel not found",
            },
        ) from exc
    except ChannelMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "channel_mismatch",
                "message": str(exc),
            },
        ) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "embedding_unavailable",
                "message": str(exc),
            },
        ) from exc

    return VideoBatchImportResponse(
        status="accepted",
        videos_received=len(video_ids),
        videos_discovered=discovered,
        videos_indexed=indexed,
        video_ids=video_ids,
    )