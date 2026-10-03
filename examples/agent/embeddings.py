"""Google embedding adapter used only by the opt-in agent retrieval path."""

import math

from google import genai
from google.genai import types

MODEL = "gemini-embedding-001"
DIMENSIONS = 768


class EmbeddingError(RuntimeError):
    """An embedding request failed or returned an invalid vector response."""


class GoogleEmbeddingClient:
    provider = "google"
    model = MODEL
    dimensions = DIMENSIONS

    def __init__(self, api_key: str):
        if not api_key:
            raise EmbeddingError("Embedding retrieval requires GOOGLE_API_KEY.")
        self._client = genai.Client(api_key=api_key)

    async def embed(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.aio.models.embed_content(
                model=MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=DIMENSIONS,
                ),
            )
        except Exception as exc:
            raise EmbeddingError("Google embedding request failed.") from exc

        embeddings = getattr(response, "embeddings", None)
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingError("Google embedding response count did not match the request.")
        vectors = []
        for embedding in embeddings:
            values = getattr(embedding, "values", None)
            if (
                not isinstance(values, list)
                or len(values) != DIMENSIONS
                or any(
                    not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in values
                )
            ):
                raise EmbeddingError("Google embedding response contained an invalid vector.")
            vectors.append([float(value) for value in values])
        return vectors

    async def aclose(self):
        await self._client.aio.aclose()
