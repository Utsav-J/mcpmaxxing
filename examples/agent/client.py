"""Interactive A2A CLI: brief progress, Markdown answers, detailed logs on the agent."""

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_message_text, new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest, TaskState
from google.protobuf.json_format import MessageToDict, ParseDict

from examples.agent.cache import Cache


async def ask(url, query=None):
    context_id = uuid4().hex
    cache = Cache(Path("artifacts/agent/client-cache.sqlite3"), url)
    async with httpx.AsyncClient(timeout=120) as http:
        while True:
            if query is None:
                try:
                    current = await asyncio.to_thread(input, "You: ")
                except EOFError:
                    return
            else:
                current = query
            if not current.strip():
                if query is not None:
                    raise ValueError("Query must not be empty.")
                continue
            saved = cache.get("a2a/agent-card")
            if saved is None:
                card = await A2ACardResolver(http, url).get_agent_card()
                cache.put("a2a/agent-card", MessageToDict(card))
            else:
                card = ParseDict(saved, AgentCard())
            # Client.close also closes a supplied HTTP client; create one per connection.
            async with httpx.AsyncClient(timeout=120) as transport:
                async with await create_client(
                    card, ClientConfig(httpx_client=transport)
                ) as client:
                    failed = False
                    async for event in client.send_message(
                        SendMessageRequest(
                            message=new_text_message(
                                current, role=Role.ROLE_USER, context_id=context_id
                            )
                        )
                    ):
                        kind = event.WhichOneof("payload")
                        if kind == "status_update":
                            print(get_message_text(event.status_update.status.message), flush=True)
                            if event.status_update.status.state == TaskState.TASK_STATE_FAILED:
                                failed = True
                            if event.status_update.status.state == TaskState.TASK_STATE_COMPLETED:
                                logs = MessageToDict(event.status_update.metadata).get("logs", {})
                                print(
                                    "Logs:",
                                    logs.get("jsonl_trace", ""),
                                    "|",
                                    logs.get("context_trace", ""),
                                )
                        elif (
                            kind == "artifact_update"
                            and event.artifact_update.artifact.name == "answer"
                        ):
                            print("Assistant:")
                            print(
                                "\n".join(
                                    part.text for part in event.artifact_update.artifact.parts
                                )
                            )
                    if query is not None:
                        if failed:
                            raise SystemExit(1)
                        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="Omit for interactive chat; EOF/Ctrl+C exits")
    parser.add_argument("--url", default="http://127.0.0.1:9999")
    args = parser.parse_args()
    try:
        asyncio.run(ask(args.url, args.query))
    except KeyboardInterrupt:
        pass
