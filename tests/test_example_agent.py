"""Check the isolated example over HTTP and through the real A2A streaming SDK."""

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("a2a")

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from langchain_core.messages import AIMessage

from examples.agent.a2a_server import create_app
from examples.agent.cache import Cache
from examples.agent.registry import ContextError, ToolContextRegistry
from examples.agent.runner import stream

pytestmark = pytest.mark.anyio


class Model:
    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        stage = json.loads(messages[-1]["content"])["stage"]
        calls = {
            "intent": [
                {
                    "name": "route_turn",
                    "args": {"kind": "tools", "retrieval_query": "Catalog books", "reply": ""},
                    "id": "s",
                }
            ],
            "arguments": [{"name": "get_books", "args": {"limit": 1}, "id": "c"}],
            "synthesis": [],
        }[stage]
        return AIMessage(
            content="One catalog book.",
            tool_calls=calls,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


@pytest.fixture
async def endpoint(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "modern_mcp", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        for _ in range(100):
            assert process.poll() is None, "HTTP server exited"
            with socket.socket() as connection:
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("HTTP server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        process.wait(timeout=5)


async def test_http_discovery_stage_context_and_markdown(endpoint, tmp_path):
    events = [
        event
        async for event in stream(
            "Catalog books imported last month", endpoint, Model(), log_dir=tmp_path
        )
    ]
    assert events[-1]["stage"] == "finished"
    registry = next(event for event in events if event["stage"] == "registry_created")
    assert len(registry["registry"]) == 7
    requests = [event for event in events if event["visibility"] == "model_request"]
    assert [event["stage"] for event in requests][-2:] == ["arguments", "synthesis"]
    argument = json.loads(requests[-2]["messages"][1]["content"])
    assert {block["category"] for block in argument["instructions"]} == {
        "reference",
        "execution",
        "domain",
    }
    synthesis = json.loads(requests[-1]["messages"][1]["content"])
    assert [policy["tool"] for policy in synthesis["presentation_policies"]] == ["get_books"]
    assert requests[-1]["tools"] == []
    for request in requests:
        assert not any(
            f'"{key}"' in json.dumps(request) for key in ("retrieval", "rankings", "context")
        )
    for event in events:
        assert event["sequence"] > 0 and event["elapsed_ms"] >= 0
    assert Path(events[-1]["markdown_trace"]).read_text("utf-8").startswith("# Agent context trace")
    assert len(Path(events[-1]["jsonl_trace"]).read_text("utf-8").splitlines()) == len(events)
    states = [event["agent_state"] for event in events if event["visibility"] == "graph_state"]
    assert states[-1]["output"] == "One catalog book."
    assert states[0]["output"] == ""  # Prior snapshots are not references to mutable state.


async def test_a2a_task_lifecycle(endpoint, tmp_path):
    app = create_app(endpoint, Model(), public_url="http://agent.test", log_dir=tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
        card = await http.get("http://agent.test/.well-known/agent-card.json")
        assert card.json()["capabilities"]["streaming"] is True
        client = await create_client("http://agent.test", ClientConfig(httpx_client=http))
        async with client:
            events = [
                event
                async for event in client.send_message(
                    SendMessageRequest(
                        message=new_text_message(
                            "Catalog books imported last month", role=Role.ROLE_USER
                        )
                    )
                )
            ]
    assert events[0].WhichOneof("payload") == "task"
    assert events[-1].status_update.status.state == TaskState.TASK_STATE_COMPLETED
    artifacts = [
        event.artifact_update.artifact
        for event in events
        if event.WhichOneof("payload") == "artifact_update"
    ]
    assert [artifact.name for artifact in artifacts] == ["answer", "context_trace"]
    assert artifacts[0].parts[0].text == "One catalog book."
    assert "model_request" in artifacts[1].parts[0].text
    trace = next(p for p in tmp_path.glob("*.jsonl") if not p.name.endswith(".context.jsonl"))
    assert json.loads(trace.read_text("utf-8").splitlines()[-1])["stage"] == "finished"


async def test_model_failure_keeps_request_context(endpoint, tmp_path):
    class BrokenModel(Model):
        async def ainvoke(self, messages):
            raise RuntimeError("a-secret-that-must-not-be-logged")

    events = [
        event async for event in stream("Catalog books", endpoint, BrokenModel(), log_dir=tmp_path)
    ]
    assert events[-1]["stage"] == "error"
    assert "RuntimeError" in events[-1]["types"]
    assert any(event["visibility"] == "model_request" for event in events)
    assert "a-secret-that-must-not-be-logged" not in json.dumps(events)


async def test_closing_stream_cancels_model(endpoint, tmp_path):
    cancelled = asyncio.Event()

    class WaitingModel(Model):
        async def ainvoke(self, messages):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    events = stream("Catalog books", endpoint, WaitingModel(), log_dir=tmp_path)
    async for event in events:
        if event["visibility"] == "model_request":
            await asyncio.sleep(0)  # Let the model begin its pending request.
            break
    await events.aclose()
    assert cancelled.is_set()
    trace = next(p for p in tmp_path.glob("*.jsonl") if not p.name.endswith(".context.jsonl"))
    assert json.loads(trace.read_text("utf-8").splitlines()[-1])["stage"] == "cancelled"


async def test_context_tampering_and_retrieval_isolation(client):
    registry = ToolContextRegistry(client, "remote")
    await registry.refresh()
    registry.records["get_books"]["context"]["retrieval"]["summary"] += " RETRIEVAL_SECRET"
    prepared = await registry.hydrate(["get_books"])
    assert "RETRIEVAL_SECRET" not in json.dumps(
        registry.argument_request("Catalog books", prepared)
    )
    prepared.instructions[0]["body"]["changed"] = True
    with pytest.raises(ContextError):
        registry.validate_call(prepared, "get_books", {})


def test_example_has_no_server_imports():
    for source in Path("examples/agent").glob("*.py"):
        assert "modern_mcp" not in source.read_text("utf-8")


async def test_conversation_cache_and_token_totals(endpoint, tmp_path):
    conversation = {}
    for turn in range(1, 3):
        events = [
            event
            async for event in stream(
                "Catalog books" if turn == 1 else "Those again",
                endpoint,
                Model(),
                log_dir=tmp_path,
                conversation=conversation,
                session_id="demo",
            )
        ]
        assert events[-1]["stage"] == "finished"
        assert events[-1]["turn_tokens"] == 45
        assert events[-1]["session_tokens"] == 45 * turn
        requests = [e for e in events if e["visibility"] == "model_request"]
        assert len(requests) == 3
        intent = json.loads(requests[0]["messages"][1]["content"])
        assert len(intent["history"]) == turn - 1
        if turn == 2:
            cache_events = [e for e in events if e["stage"] == "cache"]
            assert cache_events and all(e["status"] == "hit" for e in cache_events)
            result = next(e for e in events if e["stage"] == "tool_result")
            assert next(iter(result["result_metadata"].values()))["status"] == "hit"
    assert len(conversation["history"]) == 2
    assert "results" not in json.dumps(conversation["history"])
    context = Path(events[-1]["context_trace"])
    entries = [json.loads(line) for line in context.read_text("utf-8").splitlines()]
    assert len([e for e in entries if e["visibility"] == "model_request"]) == 6


async def test_persisted_catalog_skips_all_metadata_network_calls(client, tmp_path):
    cache = Cache(tmp_path / "cache.sqlite3", "remote")
    registry = ToolContextRegistry(client, "remote", cache=cache)
    await registry.warm()

    class NoNetwork:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected metadata network call: {name}")

    restarted = ToolContextRegistry(
        NoNetwork(), "remote", cache=Cache(tmp_path / "cache.sqlite3", "remote")
    )
    await restarted.warm()
    assert restarted.index == registry.index
    assert restarted.retrieve("books", 3) == registry.retrieve("books", 3)


async def test_chat_needs_one_model_call(endpoint, tmp_path):
    class Chat(Model):
        async def ainvoke(self, messages):
            assert json.loads(messages[-1]["content"])["stage"] == "intent"
            return AIMessage(content="Hello!")

    events = [e async for e in stream("Hello", endpoint, Chat(), log_dir=tmp_path)]
    assert events[-1]["output"] == "Hello!"
    assert events[-1]["usage_partial"] is True
    assert len([e for e in events if e["visibility"] == "model_request"]) == 1
    assert not any(e["stage"] == "tool_invocation" for e in events)


@pytest.mark.parametrize("branch,count", [("clarify", 2), ("no_match", 1)])
async def test_short_turn_branches_do_not_execute_tools(endpoint, tmp_path, branch, count):
    class ShortTurn(Model):
        async def ainvoke(self, messages):
            stage = json.loads(messages[-1]["content"])["stage"]
            if stage == "arguments":
                return AIMessage(content="Which vendor do you mean?")
            response = await super().ainvoke(messages)
            if branch == "no_match":
                response.tool_calls[0]["args"]["retrieval_query"] = "zzzzunmatchedzzzz"
            return response

    events = [e async for e in stream("Ambiguous request", endpoint, ShortTurn(), log_dir=tmp_path)]
    assert events[-1]["stage"] == "finished"
    assert len([e for e in events if e["visibility"] == "model_request"]) == count
    assert not any(e["stage"] == "tool_invocation" for e in events)
