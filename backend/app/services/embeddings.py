# CREATORLOOP_GEMINI_QUOTA_FIX_V2
import logging
import math
import random
import re
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingService:
    """Gemini embedding client with batching and quota-aware retries."""

    RETRIABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    # Gemini commonly returns retry delays such as ~40s when a per-minute
    # embedding quota is exhausted. Keep a generous ceiling so we honor the
    # provider instead of retrying too early, but still avoid accidental
    # multi-hour sleeps caused by malformed responses.
    MAX_PROVIDER_RETRY_DELAY_SECONDS = 120.0
    RETRY_SAFETY_BUFFER_SECONDS = 1.0

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        if settings.gemini_api_key is None:
            raise EmbeddingProviderError("GEMINI_API_KEY is not configured")

        self.model_name = settings.embedding_model.removeprefix("models/")
        self.model_resource = f"models/{self.model_name}"
        self.dimension = settings.embedding_dimension
        self.api_key = settings.gemini_api_key.get_secret_value()
        self.batch_size = settings.embedding_batch_size
        self.max_retries = settings.embedding_max_retries

        self.client = client or httpx.Client(
            timeout=settings.embedding_timeout_seconds,
            follow_redirects=True,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed_many(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed_many([text], "RETRIEVAL_QUERY")[0]

    def embed_for_similarity(self, texts: list[str]) -> list[list[float]]:
        return self._embed_many(texts, "SEMANTIC_SIMILARITY")

    def _embed_many(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[list[float]]:
        if not texts:
            return []

        normalized: list[str] = []

        for text in texts:
            if not isinstance(text, str):
                raise EmbeddingProviderError("Embedding input must be text")

            cleaned = text.strip()

            if not cleaned:
                raise EmbeddingProviderError("Embedding input cannot be empty")

            normalized.append(cleaned)

        vectors: list[list[float]] = []

        for start in range(0, len(normalized), self.batch_size):
            batch = normalized[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch, task_type))

        if len(vectors) != len(normalized):
            raise EmbeddingProviderError(
                f"Gemini returned {len(vectors)} embeddings for "
                f"{len(normalized)} inputs"
            )

        return vectors

    def _embed_batch(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[list[float]]:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"{self.model_resource}:batchEmbedContents"
        )

        request_body: dict[str, Any] = {
            "requests": [
                {
                    "model": self.model_resource,
                    "content": {
                        "parts": [{"text": text}],
                    },
                    "embedContentConfig": {
                        "taskType": task_type,
                        "outputDimensionality": self.dimension,
                        "autoTruncate": True,
                    },
                }
                for text in texts
            ]
        }

        response: httpx.Response | None = None
        last_network_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(
                    endpoint,
                    headers={
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=request_body,
                )
                last_network_error = None

            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_network_error = exc

                if attempt >= self.max_retries:
                    raise EmbeddingProviderError(
                        "Gemini embedding network request failed after "
                        f"{attempt + 1} attempts: {type(exc).__name__}"
                    ) from exc

                delay = self._fallback_retry_delay(attempt)

                self._sleep_before_retry(
                    delay=delay,
                    reason=type(exc).__name__,
                    attempt=attempt,
                )
                continue

            if response.status_code in self.RETRIABLE_STATUS_CODES:
                if attempt >= self.max_retries:
                    raise EmbeddingProviderError(
                        self._http_error_message(response, attempt + 1)
                    )

                delay = self._retry_delay_from_response(
                    response=response,
                    attempt=attempt,
                )

                self._sleep_before_retry(
                    delay=delay,
                    reason=f"HTTP {response.status_code}",
                    attempt=attempt,
                )
                continue

            if not response.is_success:
                raise EmbeddingProviderError(
                    self._http_error_message(response, attempt + 1)
                )

            break

        if response is None:
            if last_network_error is not None:
                raise EmbeddingProviderError(
                    "Gemini embedding request failed before receiving a response"
                ) from last_network_error

            raise EmbeddingProviderError(
                "Gemini embedding request failed before receiving a response"
            )

        try:
            payload = response.json()
            embeddings = payload["embeddings"]
        except (ValueError, KeyError, TypeError) as exc:
            raise EmbeddingProviderError(
                "Gemini embedding response was not valid JSON "
                "or did not contain embeddings"
            ) from exc

        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingProviderError(
                "Gemini returned an invalid embedding count; "
                f"expected {len(texts)}"
            )

        vectors: list[list[float]] = []

        for index, item in enumerate(embeddings):
            try:
                values = item["values"]
                vector = [float(value) for value in values]
            except (KeyError, TypeError, ValueError) as exc:
                raise EmbeddingProviderError(
                    f"Gemini returned an invalid embedding at index {index}"
                ) from exc

            self._validate_vector(vector, index)
            vectors.append(vector)

        return vectors

    def _validate_vector(
        self,
        vector: list[float],
        index: int,
    ) -> None:
        if len(vector) != self.dimension:
            raise EmbeddingProviderError(
                f"Gemini returned embedding dimension {len(vector)} at index "
                f"{index}; expected {self.dimension}"
            )

        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingProviderError(
                f"Gemini returned non-finite embedding values at index {index}"
            )

    def _retry_delay_from_response(
        self,
        response: httpx.Response,
        attempt: int,
    ) -> float:
        """
        Determine how long to wait before retrying.

        Priority:
        1. Retry-After header
        2. google.rpc.RetryInfo retryDelay in Gemini JSON
        3. "Please retry in 40.7s" style Gemini error message
        4. Conservative 60s fallback for HTTP 429
        5. Exponential backoff for other transient errors
        """

        header_delay = self._parse_retry_after(
            response.headers.get("retry-after")
        )
        if header_delay is not None:
            return self._bounded_provider_delay(header_delay)

        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")

            if isinstance(error, dict):
                details = error.get("details")

                if isinstance(details, list):
                    for detail in details:
                        if not isinstance(detail, dict):
                            continue

                        retry_delay = detail.get("retryDelay")

                        if retry_delay is not None:
                            parsed = self._parse_duration_seconds(retry_delay)

                            if parsed is not None:
                                return self._bounded_provider_delay(parsed)

                message = error.get("message")

                if isinstance(message, str):
                    parsed = self._parse_retry_delay_from_text(message)

                    if parsed is not None:
                        return self._bounded_provider_delay(parsed)

        parsed_from_body = self._parse_retry_delay_from_text(response.text)

        if parsed_from_body is not None:
            return self._bounded_provider_delay(parsed_from_body)

        # When Gemini returns RESOURCE_EXHAUSTED without an explicit delay,
        # waiting roughly one quota window is safer than retrying after 1-8s.
        if response.status_code == 429:
            return 60.0 + random.uniform(0.5, 1.5)

        return self._fallback_retry_delay(attempt)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None

        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None

        return seconds if seconds >= 0 else None

    @staticmethod
    def _parse_duration_seconds(value: Any) -> float | None:
        """
        Parse common Google retry duration forms:
        - "40s"
        - "40.748399002s"
        - 40
        - 40.7
        """

        if isinstance(value, (int, float)):
            seconds = float(value)
            return seconds if seconds >= 0 else None

        if not isinstance(value, str):
            return None

        text = value.strip()

        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", text)

        if not match:
            return None

        try:
            seconds = float(match.group(1))
        except ValueError:
            return None

        return seconds if seconds >= 0 else None

    @staticmethod
    def _parse_retry_delay_from_text(text: str | None) -> float | None:
        if not text:
            return None

        # Example returned by Gemini:
        # "Please retry in 40.748399002s."
        match = re.search(
            r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)s",
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        try:
            seconds = float(match.group(1))
        except ValueError:
            return None

        return seconds if seconds >= 0 else None

    def _bounded_provider_delay(self, seconds: float) -> float:
        # Add a small buffer so we do not retry exactly on the quota boundary.
        delay = seconds + self.RETRY_SAFETY_BUFFER_SECONDS

        return max(
            0.5,
            min(delay, self.MAX_PROVIDER_RETRY_DELAY_SECONDS),
        )

    @staticmethod
    def _fallback_retry_delay(attempt: int) -> float:
        return min(
            (2**attempt) + random.uniform(0.0, 0.5),
            8.0,
        )

    def _sleep_before_retry(
        self,
        delay: float,
        reason: str,
        attempt: int,
    ) -> None:
        logger.warning(
            "Retrying Gemini embedding request in %.2fs after %s "
            "(attempt %s/%s)",
            delay,
            reason,
            attempt + 1,
            self.max_retries + 1,
        )

        time.sleep(delay)

    @staticmethod
    def _http_error_message(
        response: httpx.Response,
        attempts: int,
    ) -> str:
        try:
            body = response.text.strip()
        except Exception:
            body = "<unreadable response body>"

        if not body:
            body = "<empty response body>"
        elif len(body) > 1200:
            body = body[:1200] + "..."

        return (
            "Gemini embedding request failed with HTTP "
            f"{response.status_code} after {attempts} attempt(s): {body}"
        )