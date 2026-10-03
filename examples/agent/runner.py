"""Run a graph against a remote MCP and yield every observable boundary immediately."""

import asyncio
import os
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from mcp import Client
from mcp.types import DiscoverResult

from examples.agent.cache import Cache
from examples.agent.embeddings import GoogleEmbeddingClient
from examples.agent.graph import Dependencies, GeminiAdapter, build_graph
from examples.agent.observability import Trace
from examples.agent.registry import ToolContextRegistry


async def stream(
    query,
    url,
    model,
    *,
    k=3,
    log_dir=Path("artifacts/agent"),
    run_id=None,
    task_context=None,
    conversation=None,
    session_id=None,
    embedding_enabled=False,
    embedding_client=None,
    per_intent=False,
    normalize=False,
):
    target = urlsplit(url)
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("Supply an HTTP(S) MCP endpoint.")
    if target.username or target.password or target.query or target.fragment:
        raise ValueError("Use an endpoint without embedded credentials, query, or fragment.")
    if not query.strip() or type(k) is not int or k < 1:
        raise ValueError("Supply a nonempty query and positive K.")
    events = asyncio.Queue()
    run_id = run_id or uuid4().hex
    conversation = conversation if conversation is not None else {}
    conversation.setdefault("history", [])
    conversation.setdefault("tokens", 0)
    conversation.setdefault("usage_missing", 0)
    conversation["turn"] = conversation.get("turn", 0) + 1
    turn_tokens = 0
    model_pending = False
    with Trace(log_dir, run_id, session_id) as trace:

        def observe(event):
            nonlocal turn_tokens, model_pending
            if event["visibility"] == "model_request":
                model_pending = True
            if event["visibility"] == "model_response":
                model_pending = False
                usage = event.get("usage") or {}
                tokens = usage.get("total_tokens")
                if isinstance(tokens, int) and tokens >= 0:
                    turn_tokens += tokens
                    conversation["tokens"] += tokens
                else:
                    conversation["usage_missing"] += 1
            if event["stage"] in {"error", "cancelled"} and model_pending:
                conversation["usage_missing"] += 1
                model_pending = False
            events.put_nowait(
                trace.emit(
                    {
                        **(task_context or {}),
                        **event,
                        "turn": conversation["turn"],
                        "turn_tokens": turn_tokens,
                        "session_tokens": conversation["tokens"],
                        "usage_partial": conversation["usage_missing"] > 0,
                    }
                )
            )

        def remember(state, output):
            conversation["history"].append(
                {"user": query, "assistant": output, "calls": state.get("calls", [])}
            )
            conversation["history"][:] = conversation["history"][-10:]

        async def execute():
            active_embedding_client = embedding_client
            owns_embedding_client = False
            state = {"query": query, "k": k, "history": conversation["history"].copy()}
            try:
                if embedding_enabled and active_embedding_client is None:
                    active_embedding_client = GoogleEmbeddingClient(os.getenv("GOOGLE_API_KEY", ""))
                    owns_embedding_client = True
                observe(
                    {
                        "stage": "initialization_start",
                        "visibility": "host_only",
                        "server": url,
                        "agent_state": state,
                    }
                )
                cache = Cache(Path(log_dir) / "cache.sqlite3", url, observe)
                discovery = cache.get("server/discover")
                options = (
                    {
                        "mode": discovery["version"],
                        "prior_discover": DiscoverResult.model_validate(discovery["result"]),
                    }
                    if discovery
                    else {}
                )
                async with Client(url, **options) as client:
                    if not discovery and client.session.discover_result is not None:
                        cache.put(
                            "server/discover",
                            {
                                "version": client.protocol_version,
                                "result": client.session.discover_result.model_dump(mode="json"),
                            },
                        )
                    registry = ToolContextRegistry(
                        client,
                        url,
                        cache=cache,
                        embedding_enabled=embedding_enabled,
                        embedding_client=active_embedding_client,
                    )
                    await registry.warm()
                    observe(
                        {
                            "stage": "registry_created",
                            "visibility": "host_only",
                            "snapshot": registry.snapshot,
                            "registry": registry.records,
                            "resources": registry.resources,
                            "reference_context": registry.references,
                            "agent_state": state,
                        }
                    )
                    context = Dependencies(
                        registry,
                        GeminiAdapter(model, observe),
                        observe,
                        per_intent=per_intent,
                        normalize=normalize,
                    )
                    async for update in build_graph().astream(
                        state, context=context, stream_mode="updates"
                    ):
                        for node, changes in update.items():
                            state.update(changes)
                            observe(
                                {
                                    "stage": node,
                                    "visibility": "graph_state",
                                    "agent_state": state,
                                    "loaded_context": registry._cache,
                                }
                            )
                remember(state, state["output"])
                observe(
                    {
                        "stage": "finished",
                        "visibility": "host_only",
                        "output": state["output"],
                        "markdown_trace": str(trace.markdown_path),
                        "jsonl_trace": str(trace.jsonl_path),
                        "context_trace": str(trace.context_path),
                    }
                )
            except asyncio.CancelledError:
                observe({"stage": "cancelled", "visibility": "host_only"})
                raise
            except Exception as exc:
                # Log exception classes only: provider errors may contain credentials.
                pending, seen, types = [exc], set(), set()
                while pending:
                    error = pending.pop()
                    if id(error) in seen:
                        continue
                    seen.add(id(error))
                    types.add(type(error).__name__)
                    if isinstance(error, BaseExceptionGroup):
                        pending.extend(error.exceptions)
                    if error.__cause__:
                        pending.append(error.__cause__)
                remember(state, "The turn failed: " + ", ".join(sorted(types)))
                observe(
                    {
                        "stage": "error",
                        "visibility": "host_only",
                        "types": sorted(types),
                        "jsonl_trace": str(trace.jsonl_path),
                        "context_trace": str(trace.context_path),
                    }
                )
            finally:
                if owns_embedding_client:
                    with suppress(Exception):
                        await active_embedding_client.aclose()
                events.put_nowait(None)

        worker = asyncio.create_task(execute())
        try:
            while (event := await events.get()) is not None:
                yield event
            await worker
        finally:
            if not worker.done():
                worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
