import json
from typing import Any

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
    """
    Small synchronous client for the protected n8n YouTube reply webhook.

    n8n is responsible for OAuth and YouTube comments.insert.
    This client is responsible for:
    - authenticating FastAPI -> n8n
    - passing a stable Idempotency-Key
    - preserving useful n8n/YouTube error details
    - validating the returned youtube_reply_id
    """

    MAX_ERROR_BODY_CHARS = 1600

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        if (
            not settings.n8n_reply_webhook_url
            or settings.n8n_reply_webhook_secret is None
        ):
            raise PublishingConfigurationError(
                "n8n reply webhook is not configured"
            )

        url = settings.n8n_reply_webhook_url.strip()

        if not url:
            raise PublishingConfigurationError(
                "n8n reply webhook URL is empty"
            )

        self.url = url
        self.secret = (
            settings.n8n_reply_webhook_secret
            .get_secret_value()
        )
        self.secret_header = (
            settings.n8n_reply_webhook_secret_header
        )

        self.client = client or httpx.Client(
            timeout=settings.n8n_reply_timeout_seconds,
            follow_redirects=True,
        )

    def publish(
        self,
        youtube_comment_id: str,
        reply: str,
    ) -> str:
        comment_id = youtube_comment_id.strip()
        final_reply = reply.strip()

        if not comment_id:
            raise YouTubePublishingError(
                "youtube_comment_id is required for publishing"
            )

        if not final_reply:
            raise YouTubePublishingError(
                "Reply text is empty"
            )

        if len(final_reply) > 2000:
            raise YouTubePublishingError(
                "Reply text exceeds 2000 characters"
            )

        try:
            response = self.client.post(
                self.url,
                headers={
                    self.secret_header: self.secret,
                    # One ReplySuggestion exists per YouTube comment in the
                    # current schema, so this is a stable retry key.
                    "Idempotency-Key": comment_id,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={
                    "youtube_comment_id": comment_id,
                    "reply": final_reply,
                },
            )

        except httpx.TimeoutException as exc:
            raise PublishingTimeoutError(
                "n8n publishing request timed out"
            ) from exc

        except httpx.RequestError as exc:
            raise PublishingUnavailableError(
                "n8n publishing webhook is unavailable: "
                f"{type(exc).__name__}"
            ) from exc

        if response.is_error:
            detail = self._response_detail(response)

            raise YouTubePublishingError(
                "n8n publishing failed with HTTP "
                f"{response.status_code}"
                f"{': ' + detail if detail else ''}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise YouTubePublishingError(
                "n8n publishing response was not valid JSON"
            ) from exc

        youtube_reply_id = self._extract_reply_id(
            payload
        )

        if not youtube_reply_id:
            raise YouTubePublishingError(
                "n8n response did not include a valid "
                "youtube_reply_id"
            )

        return youtube_reply_id

    @classmethod
    def _extract_reply_id(
        cls,
        payload: Any,
    ) -> str | None:
        if not isinstance(payload, dict):
            return None

        value = payload.get("youtube_reply_id")

        if not isinstance(value, str):
            return None

        value = value.strip()
        return value or None

    @classmethod
    def _response_detail(
        cls,
        response: httpx.Response,
    ) -> str:
        """
        Return a compact, sanitized representation of the n8n error.

        n8n often forwards the useful YouTube reason, such as:
        forbidden, quotaExceeded, commentsDisabled, etc.
        """

        try:
            payload = response.json()
            text = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (ValueError, TypeError):
            try:
                text = response.text.strip()
            except Exception:
                text = ""

        if not text:
            return ""

        # Avoid huge HTML/proxy bodies reaching FastAPI error responses/logs.
        if len(text) > cls.MAX_ERROR_BODY_CHARS:
            text = (
                text[: cls.MAX_ERROR_BODY_CHARS]
                + "..."
            )

        return text