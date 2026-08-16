import httpx

from app.config import Settings


class QuickAnalyzeConfigurationError(RuntimeError):
    pass


class QuickAnalyzeTimeoutError(RuntimeError):
    pass


class QuickAnalyzeUnavailableError(RuntimeError):
    pass


class N8NQuickAnalyzeClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.url = settings.n8n_quick_analyze_webhook_url
        self.secret = (
            settings.n8n_comment_monitor_secret.get_secret_value()
            if settings.n8n_comment_monitor_secret is not None
            else None
        )
        self.client = client or httpx.Client(timeout=settings.n8n_quick_analyze_timeout_seconds)

    def start(self, job_id: str, youtube_video_id: str, callback_base_url: str) -> None:
        if not self.url or not self.secret:
            raise QuickAnalyzeConfigurationError("n8n Quick Analyze webhook is not configured")
        try:
            response = self.client.post(
                self.url,
                headers={"X-Internal-API-Key": self.secret, "Content-Type": "application/json"},
                json={
                    "job_id": job_id,
                    "youtube_video_id": youtube_video_id,
                    "callback_base_url": callback_base_url.rstrip("/"),
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise QuickAnalyzeTimeoutError("n8n Quick Analyze request timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise QuickAnalyzeUnavailableError("n8n Quick Analyze webhook is unavailable") from exc
