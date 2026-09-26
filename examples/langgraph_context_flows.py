"""Two runnable offline LangGraph examples with explicit injectable model boundaries.

Scripted adapters demonstrate ordering and projection, NOT model quality.
Replace only the Adapter methods to connect a model in a future experiment.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from modern_mcp.json_support import canonical_json
from modern_mcp.registry import ContextError, PreparedContext, ToolContextRegistry


class Adapter(Protocol):
    async def choose_names(self, request: dict) -> list[str]: ...
    async def generate_calls(self, request: dict) -> list[dict]: ...
    async def synthesize(self, request: dict) -> Any: ...


@dataclass
class ScriptedAdapter:
    calls: list[dict]

    async def choose_names(self, request):
        return list(dict.fromkeys(call["name"] for call in self.calls))

    async def generate_calls(self, request):
        return self.calls

    async def synthesize(self, request):
        return {
            "kind": "offline-scripted-output",
            "tools_used": list(request["untrusted_result_data"]),
            "note": "Presentation request constructed; no model was called.",
        }


@dataclass
class Dependencies:
    registry: ToolContextRegistry
    adapter: Adapter


class State(TypedDict, total=False):
    query: str
    k: int
    candidates: list[str]
    selected: list[str]
    prepared: PreparedContext
    requests: list[dict]
    calls: list[dict]
    results: dict[str, Any]
    output: Any
    trace: list[str]


def traced(state, name, **updates):
    return {"trace": [*state.get("trace", []), name], **updates}


def build_graph(mode):
    if mode not in {"hydrate_candidates", "select_then_hydrate"}:
        raise ValueError("Unknown loading mode.")

    async def retrieve(state: State, runtime: Runtime[Dependencies]):
        names = [
            name for name, _ in runtime.context.registry.retrieve(state["query"], state.get("k", 3))
        ]
        return traced(state, "retrieve", candidates=names)

    async def select(state: State, runtime: Runtime[Dependencies]):
        registry = runtime.context.registry
        request = registry.selection_request(state["query"], state["candidates"])
        names = await runtime.context.adapter.choose_names(request)
        registry.validate_selection(state["candidates"], names)
        return traced(state, "select_names", selected=names, requests=[request])

    async def hydrate(state: State, runtime: Runtime[Dependencies]):
        names = state["candidates"] if mode == "hydrate_candidates" else state["selected"]
        prepared = await runtime.context.registry.hydrate(names)
        return traced(state, "load_execution_and_domain", prepared=prepared)

    async def arguments(state: State, runtime: Runtime[Dependencies]):
        request = runtime.context.registry.argument_request(state["query"], state["prepared"])
        calls = await runtime.context.adapter.generate_calls(request)
        allowed = state["prepared"].names
        if any(set(call) != {"name", "arguments"} or call["name"] not in allowed for call in calls):
            raise ContextError("Adapter generated a call outside the hydrated tool set.")
        return traced(
            state, "generate_arguments", calls=calls, requests=[*state.get("requests", []), request]
        )

    async def invoke(state: State, runtime: Runtime[Dependencies]):
        if len({call["name"] for call in state["calls"]}) != len(state["calls"]):
            raise ContextError("This small reference accepts at most one call per tool per run.")
        results = {}
        for call in state["calls"]:
            runtime.context.registry.validate_call(
                state["prepared"], call["name"], call["arguments"]
            )
        for call in state["calls"]:
            results[call["name"]] = await runtime.context.registry.invoke(
                state["prepared"], call["name"], call["arguments"]
            )
        return traced(state, "validate_and_invoke", results=results)

    async def synthesize(state: State, runtime: Runtime[Dependencies]):
        request = await runtime.context.registry.synthesis_request(
            state["query"], state["results"], state["prepared"].snapshot
        )
        output = await runtime.context.adapter.synthesize(request)
        return traced(
            state,
            "load_presentation_and_synthesize",
            output=output,
            requests=[*state["requests"], request],
        )

    def no_call(state: State):
        return traced(
            state,
            "no_call",
            results={},
            output={"kind": "no-call", "note": "No eligible tool call."},
        )

    graph = StateGraph(State, context_schema=Dependencies)
    for name, fn in [
        ("retrieve", retrieve),
        ("select", select),
        ("hydrate", hydrate),
        ("arguments", arguments),
        ("invoke", invoke),
        ("synthesize", synthesize),
        ("no_call", no_call),
    ]:
        graph.add_node(name, fn)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        lambda state: "eligible" if state["candidates"] else "empty",
        {"eligible": "hydrate" if mode == "hydrate_candidates" else "select", "empty": "no_call"},
    )
    if mode == "select_then_hydrate":
        graph.add_conditional_edges(
            "select",
            lambda state: "eligible" if state["selected"] else "empty",
            {"eligible": "hydrate", "empty": "no_call"},
        )
    graph.add_edge("hydrate", "arguments")
    graph.add_conditional_edges(
        "arguments",
        lambda state: "calls" if state["calls"] else "empty",
        {"calls": "invoke", "empty": "no_call"},
    )
    graph.add_edge("invoke", "synthesize")
    graph.add_edge("synthesize", END)
    graph.add_edge("no_call", END)
    return graph.compile()


async def run_flow(registry, mode, query, calls, k=3):
    graph = build_graph(mode)
    return await graph.ainvoke(
        {"query": query, "k": k}, context=Dependencies(registry, ScriptedAdapter(calls))
    )


async def demo(query, tool, arguments, url=None):
    target = url or StdioServerParameters(command=sys.executable, args=["-m", "modern_mcp"])
    summaries = []
    async with Client(target) as client:
        for mode in ("hydrate_candidates", "select_then_hydrate"):
            registry = ToolContextRegistry(client, url or "local-bookstore")
            await registry.refresh()
            state = await run_flow(registry, mode, query, [{"name": tool, "arguments": arguments}])
            summaries.append(
                {
                    "mode": mode,
                    "trace": state["trace"],
                    "output": state["output"],
                    "resource_reads": registry.resource_reads,
                    "request_bytes": [
                        len(canonical_json(request).encode()) for request in state["requests"]
                    ],
                    "loaded_documents": registry.loaded_document_count,
                }
            )
    return summaries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="Show books imported last month from vendor A")
    parser.add_argument(
        "--tool", default="get_books", help="Scripted tool choice, NOT an automatic model choice"
    )
    parser.add_argument(
        "--arguments",
        default='{"received_from":"2026-08-01","received_before":"2026-09-01","vendor_ids":["VENDOR-A"]}',
    )
    parser.add_argument("--url")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(demo(args.query, args.tool, json.loads(args.arguments), args.url)), indent=2
        )
    )
