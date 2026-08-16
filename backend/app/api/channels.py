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
from app.services.channels import ChannelMismatchError, ChannelNotFoundError, ChannelsService
from app.services.embeddings import EmbeddingProviderError

router = APIRouter(prefix="/api/channels", tags=["channels"])


def get_channels_service(db: Annotated[Session, Depends(get_db)]) -> ChannelsService:
    return ChannelsService(db, get_settings())


def get_channel_sync_client() -> N8NChannelSyncClient:
    return N8NChannelSyncClient(get_settings())


def authenticate_channel_sync_webhook(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    configured = get_settings().n8n_channel_sync_webhook_secret
    monitor = get_settings().n8n_comment_monitor_secret
    expected_values = [
        item.get_secret_value() for item in (configured, monitor) if item is not None
    ]
    valid = x_internal_api_key is not None and any(
        secrets.compare_digest(x_internal_api_key, expected) for expected in expected_values
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_sync_key", "message": "Invalid channel sync key"},
        )


def current_response(channel: Channel | None) -> CurrentChannelResponse:
    if channel is None:
        return CurrentChannelResponse(connected=False, channel=None, sync=None)
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
    try:
        identity = client.connect(payload.target_channel, str(request.base_url))
        channel = service.upsert(identity, status="connected")
        service.start_sync(channel.id)
        try:
            client.start_sync(channel.id, channel.youtube_channel_id, str(request.base_url))
        except Exception:
            service.fail_sync(channel.id)
            raise
        return current_response(service.get(channel.id))
    except ChannelSyncConfigurationError as exc:
        raise HTTPException(503, detail={"code": "sync_not_configured", "message": str(exc)}) from exc
    except ChannelSyncTimeoutError as exc:
        raise HTTPException(504, detail={"code": "sync_timeout", "message": str(exc)}) from exc
    except (ChannelSyncUnavailableError, InvalidChannelSyncResponseError) as exc:
        raise HTTPException(502, detail={"code": "sync_unavailable", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, detail={"code": "database_error", "message": "Unable to connect channel"}) from exc


@router.post("/sync", response_model=ChannelActionResponse, status_code=202)
def start_channel_sync(
    request: Request,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    client: Annotated[N8NChannelSyncClient, Depends(get_channel_sync_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> ChannelActionResponse:
    channel = service.current()
    if channel is None:
        raise HTTPException(409, detail={"code": "channel_not_connected", "message": "Connect a channel first"})
    service.start_sync(channel.id)
    try:
        client.start_sync(channel.id, channel.youtube_channel_id, str(request.base_url))
    except ChannelSyncConfigurationError as exc:
        service.fail_sync(channel.id)
        raise HTTPException(503, detail={"code": "sync_not_configured", "message": str(exc)}) from exc
    except ChannelSyncTimeoutError as exc:
        service.fail_sync(channel.id)
        raise HTTPException(504, detail={"code": "sync_timeout", "message": str(exc)}) from exc
    except (ChannelSyncUnavailableError, InvalidChannelSyncResponseError) as exc:
        service.fail_sync(channel.id)
        raise HTTPException(502, detail={"code": "sync_unavailable", "message": str(exc)}) from exc
    return ChannelActionResponse(status="syncing", channel_id=channel.id)


@router.post("/{channel_id}/sync-video/{youtube_video_id}", response_model=ChannelActionResponse, status_code=202)
def sync_unknown_video(
    channel_id: int,
    youtube_video_id: str,
    request: Request,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    client: Annotated[N8NChannelSyncClient, Depends(get_channel_sync_client)],
    _: Annotated[None, Depends(authenticate_internal_api_key)],
) -> ChannelActionResponse:
    if service.get(channel_id) is None:
        raise HTTPException(404, detail={"code": "channel_not_found", "message": "Channel not found"})
    try:
        # The public-channel workflow supports connect/sync. A full incremental
        # sync is the safe fallback for a newly discovered video.
        service.start_sync(channel_id)
        client.start_sync(channel_id, service.get(channel_id).youtube_channel_id, str(request.base_url))
    except ChannelSyncConfigurationError as exc:
        raise HTTPException(503, detail={"code": "sync_not_configured", "message": str(exc)}) from exc
    except ChannelSyncTimeoutError as exc:
        raise HTTPException(504, detail={"code": "sync_timeout", "message": str(exc)}) from exc
    except ChannelSyncUnavailableError as exc:
        raise HTTPException(502, detail={"code": "sync_unavailable", "message": str(exc)}) from exc
    return ChannelActionResponse(status="syncing", channel_id=channel_id)


@router.get("/{channel_id}/sync-status", response_model=CurrentChannelResponse)
def get_sync_status(
    channel_id: int,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
) -> CurrentChannelResponse:
    channel = service.get(channel_id)
    if channel is None:
        raise HTTPException(404, detail={"code": "channel_not_found", "message": "Channel not found"})
    return current_response(channel)


@router.post("/internal/resolve", response_model=CurrentChannelResponse)
def resolve_channel(
    identity: ChannelIdentity,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> CurrentChannelResponse:
    return current_response(service.upsert(identity, status="connected"))


@router.post("/{channel_id}/internal/progress", response_model=CurrentChannelResponse)
def update_sync_progress(
    channel_id: int,
    progress: ChannelSyncProgress,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> CurrentChannelResponse:
    try:
        return current_response(service.apply_progress(channel_id, progress))
    except ChannelNotFoundError as exc:
        raise HTTPException(404, detail={"code": "channel_not_found", "message": "Channel not found"}) from exc


@router.post("/{channel_id}/internal/videos", response_model=VideoBatchImportResponse)
def import_channel_videos(
    channel_id: int,
    payload: VideoBatchImportRequest,
    service: Annotated[ChannelsService, Depends(get_channels_service)],
    _: Annotated[None, Depends(authenticate_channel_sync_webhook)],
) -> VideoBatchImportResponse:
    try:
        video_ids, discovered, indexed = service.import_videos(channel_id, payload)
    except ChannelNotFoundError as exc:
        raise HTTPException(404, detail={"code": "channel_not_found", "message": "Channel not found"}) from exc
    except ChannelMismatchError as exc:
        raise HTTPException(409, detail={"code": "channel_mismatch", "message": str(exc)}) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(503, detail={"code": "embedding_unavailable", "message": str(exc)}) from exc
    return VideoBatchImportResponse(
        status="accepted",
        videos_received=len(video_ids),
        videos_discovered=discovered,
        videos_indexed=indexed,
        video_ids=video_ids,
    )
