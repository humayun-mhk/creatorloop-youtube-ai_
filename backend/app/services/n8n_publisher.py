import httpx

from app.config import Settings


class PublishingConfigurationError(RuntimeError):
    pass


class PublishingTimeoutError(RuntimeError):
    pass


class PublishingUnavailableError(RuntimeError):
    pass


class YouTubePublishingError(RuntimeError):
    pass


class N8NReplyPublisher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.n8n_reply_webhook_url or settings.n8n_reply_webhook_secret is None:
            raise PublishingConfigurationError("n8n reply webhook is not configured")
        self.url = settings.n8n_reply_webhook_url
        self.secret = settings.n8n_reply_webhook_secret.get_secret_value()
        self.secret_header = settings.n8n_reply_webhook_secret_header
        self.client = client or httpx.Client(timeout=settings.n8n_reply_timeout_seconds)

    def publish(self, youtube_comment_id: str, reply: str) -> str:
        try:
            response = self.client.post(
                self.url,
                headers={
                    self.secret_header: self.secret,
                    "Idempotency-Key": youtube_comment_id,
                    "Content-Type": "application/json",
                },
                json={"youtube_comment_id": youtube_comment_id, "reply": reply},
            )
        except httpx.TimeoutException as exc:
            raise PublishingTimeoutError("n8n publishing request timed out") from exc
        except httpx.RequestError as exc:
            raise PublishingUnavailableError("n8n publishing webhook is unavailable") from exc
        if response.is_error:
            raise YouTubePublishingError(f"n8n publishing failed with HTTP {response.status_code}")
        try:
            youtube_reply_id = response.json()["youtube_reply_id"]
        except (ValueError, KeyError, TypeError) as exc:
            raise YouTubePublishingError("n8n response did not include youtube_reply_id") from exc
        if not isinstance(youtube_reply_id, str) or not youtube_reply_id.strip():
            raise YouTubePublishingError("n8n returned an invalid youtube_reply_id")
        return youtube_reply_id.strip()
