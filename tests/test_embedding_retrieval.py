import pytest

from examples.agent.cache import Cache
from examples.agent.embeddings import DIMENSIONS, EmbeddingError, GoogleEmbeddingClient
from examples.agent.registry import ContextError, ToolContextRegistry

pytestmark = pytest.mark.anyio


class FakeEmbeddingClient:
    model = "fake-embed-v1"
    dimensions = 2

    def __init__(self):
        self.calls = []

    async def embed(self, texts, *, task_type):
        self.calls.append((list(texts), task_type))
        if task_type == "RETRIEVAL_QUERY":
            return [[1.0, 0.0] for _ in texts]
        return [
            [1.0, 0.0] if text.splitlines()[0] == "Tool: get_book_details" else [0.0, 1.0]
            for text in texts
        ]


async def test_default_retrieval_does_not_use_embeddings(client):
    embedding_client = FakeEmbeddingClient()
    registry = ToolContextRegistry(
        client,
        "bm25-only",
        embedding_enabled=False,
        embedding_client=embedding_client,
    )
    await registry.warm()

    actual = await registry.retrieve_for_pipeline("books", 3)

    assert actual == registry.retrieve("books", 3)
    assert embedding_client.calls == []


async def test_hybrid_shortlist_rrf_embeds_request_and_reuses_durable_tool_vectors(
    client, tmp_path
):
    cache_path = tmp_path / "agent-cache.sqlite3"
    first_client = FakeEmbeddingClient()
    first = ToolContextRegistry(
        client,
        "hybrid",
        cache=Cache(cache_path, "hybrid"),
        embedding_enabled=True,
        embedding_client=first_client,
    )
    await first.warm()

    assert len(first_client.calls) == 1
    assert first_client.calls[0][1] == "RETRIEVAL_DOCUMENT"
    assert len(first_client.calls[0][0]) == 8
    ranking = await first.retrieve_for_pipeline("catalog book", 3)
    assert 1 <= len(ranking) <= 3
    assert any(name == "get_book_details" for name, _ in ranking)

    await first.retrieve_for_pipeline("catalog book again", 3)
    query_calls = [call for call in first_client.calls if call[1] == "RETRIEVAL_QUERY"]
    assert len(query_calls) == 2

    restarted_client = FakeEmbeddingClient()
    restarted = ToolContextRegistry(
        client,
        "hybrid",
        cache=Cache(cache_path, "hybrid"),
        embedding_enabled=True,
        embedding_client=restarted_client,
    )
    await restarted.warm()
    assert restarted_client.calls == []
    assert restarted.tool_embeddings == first.tool_embeddings

    await restarted.retrieve_for_pipeline("new request", 2)
    assert [call[1] for call in restarted_client.calls] == ["RETRIEVAL_QUERY"]

    first.records["get_books"]["context"]["retrieval"]["summary"] += " revised wording"
    await first._prepare_tool_embeddings()
    assert first_client.calls[-1][1] == "RETRIEVAL_DOCUMENT"
    assert len(first_client.calls[-1][0]) == 1
    assert first_client.calls[-1][0][0].startswith("Tool: get_books\n")


async def test_embedding_response_with_wrong_dimension_fails_loudly(client):
    class WrongDimensions(FakeEmbeddingClient):
        async def embed(self, texts, *, task_type):
            self.calls.append((list(texts), task_type))
            return [[1.0, 2.0, 3.0] for _ in texts]

    registry = ToolContextRegistry(
        client, "wrong-dimensions", embedding_enabled=True, embedding_client=WrongDimensions()
    )
    with pytest.raises(ContextError, match="inconsistent dimensions"):
        await registry.warm()


def test_durable_embeddings_do_not_expire_with_metadata_ttl(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("examples.agent.cache.time.time", lambda: clock[0])
    cache = Cache(tmp_path / "cache.sqlite3", "remote")
    cache.put_embedding("tool:doc-hash", [0.25, 0.75])

    clock[0] += 301

    assert cache.get_embedding("tool:doc-hash") == [0.25, 0.75]
    assert cache.get("catalog") is None


def test_google_embedding_client_requires_api_key():
    with pytest.raises(EmbeddingError, match="GOOGLE_API_KEY"):
        GoogleEmbeddingClient("")


async def test_google_embedding_client_validates_response_and_uses_retrieval_task(monkeypatch):
    class FakeEmbedding:
        values = [0.5] * DIMENSIONS

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        async def embed_content(self, **kwargs):
            assert kwargs["model"] == "gemini-embedding-001"
            assert kwargs["contents"] == ["tool query"]
            assert kwargs["config"].task_type == "RETRIEVAL_QUERY"
            assert kwargs["config"].output_dimensionality == DIMENSIONS
            return FakeResponse()

    class FakeAsyncClient:
        models = FakeModels()

        async def aclose(self):
            pass

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "unit-test-key"
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("examples.agent.embeddings.genai.Client", FakeClient)
    client = GoogleEmbeddingClient("unit-test-key")

    vectors = await client.embed(["tool query"], task_type="RETRIEVAL_QUERY")

    assert vectors == [[0.5] * DIMENSIONS]
    await client.aclose()


async def test_google_embedding_client_rejects_malformed_vectors(monkeypatch):
    class FakeResponse:
        embeddings = [type("Embedding", (), {"values": [float("nan")] * DIMENSIONS})()]

    class FakeModels:
        async def embed_content(self, **kwargs):
            return FakeResponse()

    class FakeAsyncClient:
        models = FakeModels()

        async def aclose(self):
            pass

    class FakeClient:
        def __init__(self, api_key):
            self.aio = FakeAsyncClient()

    monkeypatch.setattr("examples.agent.embeddings.genai.Client", FakeClient)
    client = GoogleEmbeddingClient("unit-test-key")

    with pytest.raises(EmbeddingError, match="invalid vector"):
        await client.embed(["bad"], task_type="RETRIEVAL_QUERY")


async def test_embedding_query_failure_is_not_converted_to_bm25_fallback(client):
    class FailedQuery(FakeEmbeddingClient):
        async def embed(self, texts, *, task_type):
            if task_type == "RETRIEVAL_QUERY":
                raise RuntimeError("provider down")
            return await super().embed(texts, task_type=task_type)

    registry = ToolContextRegistry(
        client,
        "failed-query",
        embedding_enabled=True,
        embedding_client=FailedQuery(),
    )
    await registry.warm()

    with pytest.raises(RuntimeError, match="provider down"):
        await registry.retrieve_for_pipeline("query", 3)
