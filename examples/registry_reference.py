"""Run real MCP discovery/retrieval/hydration without sending anything to a model."""

import argparse
import asyncio
import json
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from modern_mcp.registry import ToolContextRegistry


async def run(query, url=None, k=3):
    target = url or StdioServerParameters(command=sys.executable, args=["-m", "modern_mcp"])
    async with Client(target) as client:
        registry = ToolContextRegistry(client, url or "local-bookstore")
        await registry.refresh()
        ranked = registry.retrieve(query, k)
        names = [name for name, _ in ranked]
        prepared = await registry.hydrate(names) if names else None
        return {
            "client_only_rankings": ranked,
            "fixed_last_month": await registry.relative_window("last month"),
            "prospective_model_request": registry.argument_request(query, prepared)
            if prepared
            else None,
            "note": "Offline reference: rankings are diagnostics, outside the model request.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="Show books imported last month from vendor A")
    parser.add_argument("--url", help="Optional Streamable HTTP server URL")
    parser.add_argument("-k", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.query, args.url, args.k)), indent=2))
