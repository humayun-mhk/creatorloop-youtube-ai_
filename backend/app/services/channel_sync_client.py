import httpx

from app.config import Settings
from app.schemas.channel import ChannelIdentity


class ChannelSyncConfigurationError(RuntimeError):
    pass


class ChannelSyncTimeoutError(RuntimeError):
    pass


class ChannelSyncUnavailableError(RuntimeError):
    pass


class InvalidChannelSyncResponseError(RuntimeError):
    pass


class N8NChannelSyncClient:
    """Small boundary client: FastAPI asks n8n to read YouTube; n8n never owns analysis."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.url = settings.n8n_channel_sync_webhook_url
        self.secret = (
            settings.n8n_channel_sync_webhook_secret.get_secret_value()
            if settings.n8n_channel_sync_webhook_secret is not None
            else None
        )
        self.client = client or httpx.Client(timeout=settings.n8n_channel_sync_timeout_seconds)

    def connect(self, target_channel: str, callback_base_url: str) -> ChannelIdentity:
        payload = self._post(
            "connect",
            callback_base_url,
            target_channel=target_channel,
        )
        try:
            return ChannelIdentity.model_validate(payload["channel"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidChannelSyncResponseError(
                "n8n did not return a valid public YouTube channel"
            ) from exc

    def start_sync(
        self,
        channel_id: int,
        youtube_channel_id: str,
        callback_base_url: str,
    ) -> None:
        self._post(
            "sync",
            callback_base_url,
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
    ) -> dict:
        if not self.url or not self.secret:
            raise ChannelSyncConfigurationError("n8n channel sync webhook is not configured")
        try:
            response = self.client.post(
                self.url,
                headers={
                    self.settings.n8n_channel_sync_webhook_secret_header: self.secret,
                    "Content-Type": "application/json",
                },
                json={
                    "action": action,
                    "channel_id": channel_id,
                    "youtube_channel_id": youtube_channel_id,
                    "target_channel": target_channel,
                    "callback_base_url": callback_base_url.rstrip("/"),
                    "initial_sync_video_limit": self.settings.initial_sync_video_limit,
                },
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
        except httpx.TimeoutException as exc:
            raise ChannelSyncTimeoutError("n8n channel sync request timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise ChannelSyncUnavailableError("n8n channel sync webhook is unavailable") from exc
        if not isinstance(data, dict):
            raise InvalidChannelSyncResponseError("n8n returned an invalid sync response")
        return data
