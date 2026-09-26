"""Deterministic fixtures for offline measurements only; never used by the live agent."""

from dataclasses import dataclass


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


async def run_flow(registry, mode, query, calls, k=3):
    from examples.langgraph_context_flows import Dependencies, build_graph

    return await build_graph(mode).ainvoke(
        {"query": query, "k": k}, context=Dependencies(registry, ScriptedAdapter(calls))
    )
