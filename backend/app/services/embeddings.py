import math

import httpx

from app.config import Settings


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingService:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.gemini_api_key is None:
            raise EmbeddingProviderError("GEMINI_API_KEY is not configured")
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self.api_key = settings.gemini_api_key.get_secret_value()
        self.client = client or httpx.Client(timeout=settings.embedding_timeout_seconds)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text, "RETRIEVAL_DOCUMENT") for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, "RETRIEVAL_QUERY")

    def embed_for_similarity(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text, "SEMANTIC_SIMILARITY") for text in texts]

    def _embed(self, text: str, task_type: str) -> list[float]:
        request = {
            "content": {"parts": [{"text": text}]},
            "embedContentConfig": {
                "taskType": task_type,
                "outputDimensionality": self.dimension,
                "autoTruncate": True,
            },
        }
        try:
            response = self.client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:embedContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=request,
            )
            response.raise_for_status()
            values = response.json()["embedding"]["values"]
            vector = [float(value) for value in values]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Gemini embedding request failed") from exc
        if len(vector) != self.dimension or not all(math.isfinite(value) for value in vector):
            raise EmbeddingProviderError(
                f"Gemini returned an invalid embedding dimension; expected {self.dimension}"
            )
        return vector
