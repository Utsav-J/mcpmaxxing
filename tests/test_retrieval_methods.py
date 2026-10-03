from types import SimpleNamespace

import pytest

from examples.agent.graph import GeminiAdapter, intent_request
from examples.agent.registry import ToolContextRegistry, tokens

pytestmark = pytest.mark.anyio


def test_plural_normalization_and_default_tokens():
    assert tokens("Books receipts deliveries availability") == [
        "books",
        "receipts",
        "deliveries",
        "availability",
    ]
    assert tokens("Books receipts deliveries availability", normalize=True) == [
        "book",
        "receipt",
        "delivery",
        "availability",
    ]
    assert tokens("sales trends genres", True) == ["sale", "trend", "genre"]


async def test_normalized_corpus_and_queries_match(client):
    registry = ToolContextRegistry(client, "test")
    await registry.refresh()
    assert registry.retrieve("stock receipt", 3, normalize=True) == registry.retrieve(
        "stock receipts", 3, normalize=True
    )


async def test_per_intent_deduplicates_caps_and_does_not_pad():
    class Registry(ToolContextRegistry):
        async def retrieve_for_pipeline(self, query, k=3, *, normalize=False):
            assert k == 1
            return [(query, 5.0)] if query != "no match" else []

    registry = Registry(None, "fake")
    assert await registry.retrieve_per_intent(["a", "a", "b", "c"], 2) == [("a", 5.0), ("b", 5.0)]
    assert await registry.retrieve_per_intent(["no match", "a"], 3) == [("a", 5.0)]


async def test_intent_schema_requires_subqueries_and_can_join_whole_query():
    class Model:
        def bind_tools(self, tools):
            schema = tools[0]["parameters"]
            assert "retrieval_queries" in schema["required"]
            return self

        async def ainvoke(self, messages):
            return SimpleNamespace(
                content="",
                invalid_tool_calls=[],
                usage_metadata=None,
                tool_calls=[
                    {
                        "name": "route_turn",
                        "args": {
                            "kind": "tools",
                            "reply": "",
                            "retrieval_queries": ["current stock", "monthly sales"],
                        },
                    }
                ],
            )

    route = await GeminiAdapter(Model(), lambda event: None).route(
        intent_request("stock and sales", [], per_intent=True)
    )
    assert route["retrieval_query"] == "current stock; monthly sales"
    assert route["retrieval_queries"] == ["current stock", "monthly sales"]
