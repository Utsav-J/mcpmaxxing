"""Run directly or serve the same agent through A2A."""

import argparse
import asyncio
import os
from pathlib import Path
from uuid import uuid4

import uvicorn
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from examples.agent.a2a_server import create_app
from examples.agent.observability import status
from examples.agent.runner import stream


async def run(args, model):
    session, session_id = {}, uuid4().hex
    while True:
        if args.query is not None:
            query = args.query
        else:
            try:
                query = await asyncio.to_thread(input, "You: ")
            except EOFError:
                return
        if not query.strip():
            if args.query is not None:
                raise ValueError("Query must not be empty.")
            continue
        failed = False
        async for event in stream(
            query,
            args.mcp_url,
            model,
            k=args.k,
            log_dir=args.log_dir,
            conversation=session,
            session_id=session_id,
            embedding_enabled=args.embedding_enabled,
            per_intent=args.per_intent,
            normalize=args.normalize,
        ):
            if event["visibility"] in {"model_request", "model_response"} or event["stage"] in {
                "registry_created",
                "tool_invocation",
                "finished",
                "error",
            }:
                print(status(event), flush=True)
            if event["stage"] == "finished":
                print("Assistant:", event["output"])
                print(f"Logs: {event['jsonl_trace']} | {event['context_trace']}")
            if event["stage"] == "error":
                print("Failure:", ", ".join(event["types"]))
                failed = True
        if args.query is not None:
            if failed:
                raise SystemExit(1)
            return


def main():
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default=os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp"))
    parser.add_argument("--query", help="Single turn; omit for an interactive conversation")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    parser.add_argument("-k", type=int, default=3)
    parser.add_argument(
        "--embedding-enabled",
        action="store_true",
        help="Fuse embedding and BM25 tool rankings with RRF.",
    )
    parser.add_argument(
        "--per-intent", action="store_true", help="Retrieve top-1 per intent, capped by K."
    )
    parser.add_argument(
        "--normalize", action="store_true", help="Normalize English plural BM25 tokens."
    )
    parser.add_argument("--log-dir", type=Path, default=Path("artifacts/agent"))
    parser.add_argument("--serve", action="store_true", help="Serve the agent through A2A JSON-RPC")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument(
        "--public-url", help="Advertised A2A base URL; defaults to the listening URL"
    )
    args = parser.parse_args()
    if not os.getenv("GOOGLE_API_KEY"):
        parser.error("Set GOOGLE_API_KEY in the environment or .env.")
    if args.k < 1:
        parser.error("K must be positive.")
    model = ChatGoogleGenerativeAI(model=args.model, vertexai=False, timeout=60, max_retries=0)
    if args.serve:
        public_url = args.public_url or f"http://{args.host}:{args.port}"
        uvicorn.run(
            create_app(
                args.mcp_url,
                model,
                public_url=public_url,
                k=args.k,
                log_dir=args.log_dir,
                embedding_enabled=args.embedding_enabled,
                per_intent=args.per_intent,
                normalize=args.normalize,
            ),
            host=args.host,
            port=args.port,
        )
    else:
        try:
            asyncio.run(run(args, model))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
