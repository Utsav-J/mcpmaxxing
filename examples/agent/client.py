"""Send a query through A2A and print the streamed Markdown context updates."""

import argparse
import asyncio

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState


async def ask(url, query):
    async with httpx.AsyncClient(timeout=120) as http:
        async with await create_client(url, ClientConfig(httpx_client=http)) as client:
            async for event in client.send_message(
                SendMessageRequest(
                    message=new_text_message(query, role=Role.ROLE_USER),
                )
            ):
                kind = event.WhichOneof("payload")
                if kind == "status_update":
                    print(get_message_text(event.status_update.status.message), flush=True)
                    if event.status_update.status.state == TaskState.TASK_STATE_FAILED:
                        raise RuntimeError("Agent task failed; inspect the stage trace.")
                elif kind == "artifact_update" and event.artifact_update.artifact.name == "answer":
                    print("# Answer\n")
                    print("\n".join(part.text for part in event.artifact_update.artifact.parts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--url", default="http://127.0.0.1:9999")
    args = parser.parse_args()
    asyncio.run(ask(args.url, args.query))
