import logging
import math
import random
import time
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingService:
    """Gemini embedding client with batching, validation, and transient retries."""

    RETRIABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

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
                        f"Gemini embedding network request failed after "
                        f"{attempt + 1} attempts: {type(exc).__name__}"
                    ) from exc

                self._sleep_before_retry(attempt, reason=type(exc).__name__)
                continue

            if response.status_code in self.RETRIABLE_STATUS_CODES:
                if attempt >= self.max_retries:
                    raise EmbeddingProviderError(
                        self._http_error_message(response, attempt + 1)
                    )

                self._sleep_before_retry(
                    attempt,
                    reason=f"HTTP {response.status_code}",
                    retry_after=response.headers.get("retry-after"),
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
                "Gemini embedding response was not valid JSON or did not contain embeddings"
            ) from exc

        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingProviderError(
                f"Gemini returned an invalid embedding count; "
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

    def _validate_vector(self, vector: list[float], index: int) -> None:
        if len(vector) != self.dimension:
            raise EmbeddingProviderError(
                f"Gemini returned embedding dimension {len(vector)} at index "
                f"{index}; expected {self.dimension}"
            )

        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingProviderError(
                f"Gemini returned non-finite embedding values at index {index}"
            )

    def _sleep_before_retry(
        self,
        attempt: int,
        reason: str,
        retry_after: str | None = None,
    ) -> None:
        delay: float

        if retry_after:
            try:
                delay = max(0.0, min(float(retry_after), 30.0))
            except ValueError:
                delay = 0.0
        else:
            delay = 0.0

        if delay <= 0:
            delay = min((2**attempt) + random.uniform(0.0, 0.5), 8.0)

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
        elif len(body) > 800:
            body = body[:800] + "..."

        return (
            f"Gemini embedding request failed with HTTP "
            f"{response.status_code} after {attempts} attempt(s): {body}"
        )