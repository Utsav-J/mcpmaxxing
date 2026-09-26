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
            "selection": [{"name": "select_tools", "args": {"names": ["get_books"]}, "id": "s"}],
            "arguments": [{"name": "get_books", "args": {"limit": 1}, "id": "c"}],
            "synthesis": [],
        }[stage]
        return AIMessage(content="One catalog book.", tool_calls=calls)


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


@pytest.mark.parametrize("mode", ["select_then_hydrate", "hydrate_candidates"])
async def test_http_discovery_stage_context_and_markdown(endpoint, tmp_path, mode):
    events = [
        event
        async for event in stream(
            "Catalog books imported last month", endpoint, Model(), mode=mode, log_dir=tmp_path
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
    assert "output" not in states[0]  # Prior snapshots are not references to mutable state.


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
    trace = next(tmp_path.glob("*.jsonl"))
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
    trace = next(tmp_path.glob("*.jsonl"))
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
