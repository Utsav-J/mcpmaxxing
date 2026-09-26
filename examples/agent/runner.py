"""Run a graph against a remote MCP and yield every observable boundary immediately."""

import asyncio
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from mcp import Client

from examples.agent.graph import Dependencies, GeminiAdapter, build_graph
from examples.agent.observability import Trace
from examples.agent.registry import ToolContextRegistry


async def stream(
    query,
    url,
    model,
    *,
    mode="select_then_hydrate",
    k=3,
    log_dir=Path("artifacts/agent"),
    run_id=None,
    task_context=None,
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
    with Trace(log_dir, run_id) as trace:

        def observe(event):
            events.put_nowait(trace.emit({**(task_context or {}), **event}))

        async def execute():
            try:
                state = {"query": query, "k": k}
                observe(
                    {
                        "stage": "initialization_start",
                        "visibility": "host_only",
                        "server": url,
                        "agent_state": state,
                    }
                )
                async with Client(url) as client:
                    registry = ToolContextRegistry(client, url)
                    await registry.refresh()
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
                    context = Dependencies(registry, GeminiAdapter(model, observe), observe)
                    async for update in build_graph(mode).astream(
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
                observe(
                    {
                        "stage": "finished",
                        "visibility": "host_only",
                        "output": state["output"],
                        "markdown_trace": str(trace.markdown_path),
                        "jsonl_trace": str(trace.jsonl_path),
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
                observe({"stage": "error", "visibility": "host_only", "types": sorted(types)})
            finally:
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
