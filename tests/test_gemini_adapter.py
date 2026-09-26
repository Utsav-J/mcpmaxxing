"""Check the actual Gemini boundary without requiring paid API calls."""

from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")

from examples.langgraph_context_flows import GeminiAdapter
from modern_mcp.registry import ToolContextRegistry

pytestmark = pytest.mark.anyio


async def test_model_projection_and_real_graph(client):
    from examples.langgraph_context_flows import Dependencies, build_graph

    events = []

    class Model:
        def bind_tools(self, tools):
            self.tools = tools
            return self

        async def ainvoke(self, messages):
            stage = events[-1]["stage"]
            calls = {
                "selection": [{"name": "select_tools", "args": {"names": ["get_books"]}}],
                "arguments": [{"name": "get_books", "args": {"limit": 1}}],
                "synthesis": [],
            }[stage]
            return SimpleNamespace(
                content="Answer", tool_calls=calls, invalid_tool_calls=[], usage_metadata=None
            )

    registry = ToolContextRegistry(client, "test")
    await registry.refresh()
    state = await build_graph("select_then_hydrate").ainvoke(
        {"query": "Catalog books imported last month", "k": 3},
        context=Dependencies(registry, GeminiAdapter(Model(), events.append), events.append),
    )
    assert state["output"] == "Answer"
    requests = [event for event in events if event["visibility"] == "model_request"]
    assert [event["stage"] for event in requests] == ["selection", "arguments", "synthesis"]
    assert requests[0]["tools"][0]["name"] == "select_tools"
    assert requests[1]["tools"][0]["name"] == "get_books"
    assert requests[2]["tools"] == []
    import json

    argument = json.loads(requests[1]["messages"][1]["content"])
    assert {block["category"] for block in argument["instructions"]} == {
        "reference",
        "execution",
        "domain",
    }
    synthesis = json.loads(requests[2]["messages"][1]["content"])
    assert synthesis["presentation_policies"][0]["tool"] == "get_books"
    for request in requests:
        serialized = json.dumps(request)
        assert '"retrieval"' not in serialized
        assert '"metadata"' not in serialized
        assert '"rankings"' not in serialized
    assert [event["stage"] for event in events].index("tool_results") < [
        event["stage"] for event in events
    ].index("synthesis")
