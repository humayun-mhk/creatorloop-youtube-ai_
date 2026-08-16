import logging
from typing import Any

import httpx

from app.config import Settings
from app.schemas.channel import ChannelIdentity

logger = logging.getLogger(__name__)


class ChannelSyncConfigurationError(RuntimeError):
    pass


class ChannelSyncTimeoutError(RuntimeError):
    pass


class ChannelSyncUnavailableError(RuntimeError):
    pass


class InvalidChannelSyncResponseError(RuntimeError):
    pass


class N8NChannelSyncClient:
    """
    Boundary client between FastAPI and the n8n public-channel workflow.

    FastAPI owns application state and AI analysis.
    n8n owns YouTube orchestration and calls FastAPI back with imported data.
    """

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.url = settings.n8n_channel_sync_webhook_url
        self.secret = (
            settings.n8n_channel_sync_webhook_secret.get_secret_value()
            if settings.n8n_channel_sync_webhook_secret is not None
            else None
        )

        self.secret_header = settings.n8n_channel_sync_webhook_secret_header
        self.timeout = settings.n8n_channel_sync_timeout_seconds

        # Supplying a client is useful for tests.
        # Otherwise create one for this dependency instance.
        self.client = client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
        )

    def connect(
        self,
        target_channel: str,
        callback_base_url: str,
    ) -> ChannelIdentity:
        payload = self._post(
            action="connect",
            callback_base_url=callback_base_url,
            target_channel=target_channel,
        )

        try:
            return ChannelIdentity.model_validate(payload["channel"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "n8n connect response did not contain a valid channel object"
            )
            raise InvalidChannelSyncResponseError(
                "n8n did not return a valid public YouTube channel"
            ) from exc

    def start_sync(
        self,
        channel_id: int,
        youtube_channel_id: str,
        callback_base_url: str,
    ) -> None:
        # n8n normally returns HTTP 202 for this action.
        # Any 2xx response is treated as successful.
        self._post(
            action="sync",
            callback_base_url=callback_base_url,
            channel_id=channel_id,
            youtube_channel_id=youtube_channel_id,
        )

    def _post(
        self,
        action: str,
        callback_base_url: str,
        channel_id: int | None = None,
        youtube_channel_id: str | None = None,
        target_channel: str | None = None,
    ) -> dict[str, Any]:
        if not self.url:
            raise ChannelSyncConfigurationError(
                "N8N_CHANNEL_SYNC_WEBHOOK_URL is not configured"
            )

        if not self.secret:
            raise ChannelSyncConfigurationError(
                "N8N_CHANNEL_SYNC_WEBHOOK_SECRET is not configured"
            )

        if not self.secret_header:
            raise ChannelSyncConfigurationError(
                "N8N_CHANNEL_SYNC_WEBHOOK_SECRET_HEADER is not configured"
            )

        callback = callback_base_url.rstrip("/")

        payload: dict[str, Any] = {
            "action": action,
            "callback_base_url": callback,
            "initial_sync_video_limit": self.settings.initial_sync_video_limit,
        }

        # Avoid sending unnecessary null values to n8n.
        if channel_id is not None:
            payload["channel_id"] = channel_id

        if youtube_channel_id:
            payload["youtube_channel_id"] = youtube_channel_id

        if target_channel:
            payload["target_channel"] = target_channel

        logger.info(
            "Calling n8n channel sync webhook",
            extra={
                "action": action,
                "channel_id": channel_id,
                "youtube_channel_id": youtube_channel_id,
                "callback_base_url": callback,
            },
        )

        try:
            response = self.client.post(
                str(self.url),
                headers={
                    self.secret_header: self.secret,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )

        except httpx.TimeoutException as exc:
            logger.warning(
                "n8n channel sync request timed out",
                extra={"action": action, "channel_id": channel_id},
            )
            raise ChannelSyncTimeoutError(
                "n8n channel sync request timed out"
            ) from exc

        except httpx.RequestError as exc:
            logger.warning(
                "Unable to reach n8n channel sync webhook: %s",
                exc,
            )
            raise ChannelSyncUnavailableError(
                f"Unable to reach n8n channel sync webhook: {exc}"
            ) from exc

        # httpx considers every 2xx response successful, including 202.
        if not response.is_success:
            safe_body = self._safe_response_preview(response)

            logger.warning(
                "n8n channel sync returned HTTP %s: %s",
                response.status_code,
                safe_body,
            )

            raise ChannelSyncUnavailableError(
                f"n8n channel sync returned HTTP "
                f"{response.status_code}: {safe_body}"
            )

        if not response.content:
            # An empty successful response is valid for the sync action,
            # but connect must return a channel object.
            if action == "connect":
                raise InvalidChannelSyncResponseError(
                    "n8n connect webhook returned an empty response"
                )
            return {}

        try:
            data = response.json()
        except ValueError as exc:
            safe_body = self._safe_response_preview(response)

            logger.warning(
                "n8n returned non-JSON success response: %s",
                safe_body,
            )

            raise InvalidChannelSyncResponseError(
                f"n8n returned a non-JSON response: {safe_body}"
            ) from exc

        if not isinstance(data, dict):
            raise InvalidChannelSyncResponseError(
                "n8n returned an invalid sync response"
            )

        logger.info(
            "n8n channel sync webhook accepted request",
            extra={
                "action": action,
                "channel_id": channel_id,
                "status_code": response.status_code,
            },
        )

        return data

    @staticmethod
    def _safe_response_preview(
        response: httpx.Response,
        limit: int = 500,
    ) -> str:
        """
        Return a small response preview for logs/errors.

        This does not include request headers, so the webhook secret is not
        exposed in Render logs.
        """
        try:
            text = response.text.strip()
        except Exception:
            return "<unreadable response body>"

        if not text:
            return "<empty response body>"

        if len(text) > limit:
            return text[:limit] + "..."

        return text