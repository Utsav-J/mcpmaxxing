"""Official A2A SDK task lifecycle around the LangGraph runner."""

import asyncio
import json
from contextlib import aclosing
from pathlib import Path

from a2a.helpers import new_task_from_user_message, new_text_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part, TaskState
from starlette.applications import Starlette

from examples.agent.observability import status
from examples.agent.runner import stream


class Executor(AgentExecutor):
    def __init__(self, url, model, **options):
        self.url, self.model, self.options = url, model, options
        # ponytail: demo sessions stay in memory; evict idle sessions for multi-user hosting.
        self.conversations = {}

    async def execute(self, context, event_queue):
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        session = self.conversations.setdefault(task.context_id, {"lock": asyncio.Lock()})
        async with session["lock"]:
            try:
                async with aclosing(
                    stream(
                        context.get_user_input(),
                        self.url,
                        self.model,
                        task_context={"a2a_task_id": task.id, "a2a_context_id": task.context_id},
                        conversation=session,
                        session_id=task.context_id,
                        **self.options,
                    )
                ) as events:
                    async for event in events:
                        message = new_text_message(
                            status(event), task_id=task.id, context_id=task.context_id
                        )
                        progress = {
                            key: event[key]
                            for key in (
                                "stage",
                                "turn",
                                "elapsed_ms",
                                "turn_tokens",
                                "session_tokens",
                                "usage_partial",
                            )
                        }
                        if event["stage"] == "error":
                            await updater.failed(
                                new_text_message(
                                    status(event) + " Failure: " + ", ".join(event["types"]),
                                    task_id=task.id,
                                    context_id=task.context_id,
                                )
                            )
                            return
                        if event["stage"] == "finished":
                            output = event["output"]
                            if not isinstance(output, str):
                                output = json.dumps(output, ensure_ascii=False, indent=2)
                            await updater.add_artifact(
                                [Part(text=output, media_type="text/markdown")], name="answer"
                            )
                            await updater.add_artifact(
                                [
                                    Part(
                                        text=Path(event["context_trace"]).read_text("utf-8"),
                                        media_type="application/x-ndjson",
                                    )
                                ],
                                name="context_trace",
                            )
                            await updater.update_status(
                                TaskState.TASK_STATE_COMPLETED,
                                message,
                                metadata={
                                    "progress": progress,
                                    "logs": {
                                        key: event[key]
                                        for key in (
                                            "jsonl_trace",
                                            "context_trace",
                                            "markdown_trace",
                                        )
                                    },
                                },
                            )
                            return
                        if event["visibility"] in {"model_request", "model_response"} or event[
                            "stage"
                        ] in {"registry_created", "tool_invocation"}:
                            await updater.update_status(
                                TaskState.TASK_STATE_WORKING,
                                message,
                                metadata={"progress": progress},
                            )
            except Exception as exc:
                await updater.failed(
                    new_text_message(
                        f"Agent failed: {type(exc).__name__}. See local logs.",
                        task_id=task.id,
                        context_id=task.context_id,
                    )
                )

    async def cancel(self, context, event_queue):
        # The SDK cancels execute(); runner's finally cancels its graph worker.
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def create_app(url, model, *, public_url="http://127.0.0.1:9999", **options):
    card = AgentCard(
        name="MCP Context Agent",
        version="0.1.0",
        description="Discovers remote MCP tools and applies their context in stages.",
        supported_interfaces=[
            AgentInterface(
                url=public_url.rstrip("/") + "/", protocol_binding="JSONRPC", protocol_version="1.0"
            )
        ],
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/markdown"],
        skills=[
            AgentSkill(
                id="remote_tools",
                name="Use remote MCP tools",
                description="Retrieve tools, load calling context, invoke, and present.",
                tags=["mcp", "tool-context"],
            )
        ],
    )
    # ponytail: in-memory A2A tasks; use the SDK's durable store when restart recovery matters.
    handler = DefaultRequestHandler(Executor(url, model, **options), InMemoryTaskStore(), card)
    return Starlette(
        routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, rpc_url="/")]
    )
