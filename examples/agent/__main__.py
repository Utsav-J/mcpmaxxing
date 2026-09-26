"""Run directly or serve the same agent through A2A."""

import argparse
import asyncio
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from examples.agent.a2a_server import create_app
from examples.agent.runner import stream


async def run(args, model):
    failed = False
    async for event in stream(
        args.query, args.mcp_url, model, mode=args.mode, k=args.k, log_dir=args.log_dir
    ):
        print(f"[{event['elapsed_ms']:.0f}ms] {event['stage']} ({event['visibility']})", flush=True)
        if event["stage"] == "finished":
            print(event["output"])
            print(f"\nContext trace: {event['markdown_trace']}")
        if event["stage"] == "error":
            print("Failure types:", ", ".join(event["types"]))
            failed = True
    if failed:
        raise SystemExit(1)


def main():
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp-url", default=os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp"))
    parser.add_argument("--query", default="Show books imported last month from vendor A")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    parser.add_argument(
        "--mode",
        choices=["select_then_hydrate", "hydrate_candidates"],
        default="select_then_hydrate",
    )
    parser.add_argument("-k", type=int, default=3)
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
    model = ChatGoogleGenerativeAI(model=args.model, vertexai=False, timeout=60, max_retries=2)
    if args.serve:
        public_url = args.public_url or f"http://{args.host}:{args.port}"
        uvicorn.run(
            create_app(
                args.mcp_url,
                model,
                public_url=public_url,
                mode=args.mode,
                k=args.k,
                log_dir=args.log_dir,
            ),
            host=args.host,
            port=args.port,
        )
    else:
        asyncio.run(run(args, model))


if __name__ == "__main__":
    main()
