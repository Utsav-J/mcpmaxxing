"""Real Gemini agent with staged tool context and live JSONL lifecycle tracing."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from examples.agent.registry import (
    ContextError,
    PreparedContext,
    ToolContextRegistry,
    canonical_json,
)


@dataclass
class Dependencies:
    registry: ToolContextRegistry
    adapter: Any
    observe: Any = lambda event: None


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
        ranked = runtime.context.registry.retrieve(state["query"], state.get("k", 3))
        names = [name for name, _ in ranked]
        runtime.context.observe(
            {
                "stage": "retrieval",
                "visibility": "host_only",
                "rankings": ranked,
                "candidates": names,
            }
        )
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
        runtime.context.observe(
            {
                "stage": "hydration",
                "visibility": "host_only",
                "tools": list(prepared.names),
                "instructions": list(prepared.instructions),
            }
        )
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
            runtime.context.observe(
                {"stage": "tool_invocation", "visibility": "host_only", "call": call}
            )
            results[call["name"]] = await runtime.context.registry.invoke(
                state["prepared"], call["name"], call["arguments"]
            )
        runtime.context.observe(
            {
                "stage": "tool_results",
                "visibility": "host_only",
                "calls": state["calls"],
                "results": results,
            }
        )
        return traced(state, "validate_and_invoke", results=results)

    async def synthesize(state: State, runtime: Runtime[Dependencies]):
        request = await runtime.context.registry.synthesis_request(
            state["query"], state["results"], state["prepared"].snapshot
        )
        runtime.context.observe(
            {
                "stage": "presentation_loaded",
                "visibility": "host_only",
                "presentation_policies": request["presentation_policies"],
            }
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


class GeminiAdapter:
    def __init__(self, model, observe):
        self.model = model
        self.observe = observe

    async def complete(self, request, tools=()):
        # Each phase gets a fresh projection: no raw metadata or retrieval scores.
        payload = {key: value for key, value in request.items() if key != "tools"}
        messages = [
            {"role": "system", "content": request["instruction"]},
            {"role": "user", "content": canonical_json(payload)},
        ]
        self.observe(
            {
                "stage": request["stage"],
                "visibility": "model_request",
                "messages": messages,
                "tools": list(tools),
            }
        )
        bound = self.model.bind_tools(list(tools)) if tools else self.model
        started = perf_counter()
        response = await bound.ainvoke(messages)
        if response.invalid_tool_calls:
            raise ContextError("Gemini returned invalid tool arguments.")
        self.observe(
            {
                "stage": request["stage"],
                "visibility": "model_response",
                "content": response.content,
                "tool_calls": response.tool_calls,
                "usage": response.usage_metadata,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            }
        )
        return response

    async def choose_names(self, request):
        tool = {
            "name": "select_tools",
            "description": "Select eligible tool names or decline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [item["name"] for item in request["candidates"]],
                        },
                    }
                },
                "required": ["names"],
            },
        }
        response = await self.complete(request, [tool])
        if not response.tool_calls:
            return []
        if len(response.tool_calls) != 1 or response.tool_calls[0]["name"] != "select_tools":
            raise ContextError("Expected one selection call.")
        names = response.tool_calls[0]["args"].get("names")
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise ContextError("Expected a list of tool names.")
        return names

    async def generate_calls(self, request):
        tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            }
            for tool in request["tools"]
        ]
        response = await self.complete(request, tools)
        return [{"name": call["name"], "arguments": call["args"]} for call in response.tool_calls]

    async def synthesize(self, request):
        return (await self.complete(request)).content
