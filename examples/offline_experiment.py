"""Generate a reproducible JSON report; all model choices are scripted."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from examples.offline_adapter import run_flow
from modern_mcp.json_support import canonical_json
from modern_mcp.registry import ToolContextRegistry
from modern_mcp.server import create_server


async def experiment():
    cases = json.loads(Path(__file__).with_name("retrieval_cases.json").read_text("utf-8"))
    async with Client(create_server()) as client:
        registry = ToolContextRegistry(client, "offline-experiment")
        await registry.refresh()
        rows = []
        for case in cases:
            top3 = [name for name, _ in registry.retrieve(case["query"], 3)]
            required = set(case["required"])
            rows.append(
                {
                    **case,
                    "retrieved_at_3": top3,
                    "recall_at_1": len(required.intersection(top3[:1])) / len(required)
                    if required
                    else None,
                    "recall_at_3": len(required.intersection(top3)) / len(required)
                    if required
                    else None,
                    "precision_at_3": len(required.intersection(top3)) / len(top3)
                    if top3
                    else None,
                    "all_required_at_3": required.issubset(top3),
                    "no_match": not top3,
                }
            )
        query = "Show books imported last month from vendor A"
        calls = [
            {
                "name": "get_books",
                "arguments": {
                    "vendor_ids": ["VENDOR-A"],
                    "received_from": "2026-08-01",
                    "received_before": "2026-09-01",
                },
            }
        ]
        comparisons = []
        for k in (1, 3, 7):
            for mode in ("hydrate_candidates", "select_then_hydrate"):
                registry.resource_reads = 0
                await registry.refresh()
                state = await run_flow(registry, mode, query, calls, k)
                reads = registry.resource_reads
                request_sizes = [
                    len(canonical_json(request).encode()) for request in state["requests"]
                ]
                documents = registry.loaded_document_count
                await run_flow(registry, mode, query, calls, k)
                warm_reads = registry.resource_reads - reads
                comparisons.append(
                    {
                        "k": k,
                        "mode": mode,
                        "candidate_count": len(state["candidates"]),
                        "scripted_used_tools": list(state["results"]),
                        "loaded_category_documents": documents,
                        "cold_resource_read_calls": reads,
                        "warm_extra_read_calls": warm_reads,
                        "prospective_model_stages": len(request_sizes),
                        "stage_request_bytes": request_sizes,
                        "total_request_bytes": sum(request_sizes),
                    }
                )
                registry.resource_reads = 0
        await registry.refresh()
        prepared = await registry.hydrate(sorted(registry.records))
        argument = registry.argument_request(query, prepared)
        result = await registry.invoke(prepared, "get_books", calls[0]["arguments"])
        synthesis = await registry.synthesis_request(
            query, {"get_books": result}, prepared.snapshot
        )
        # Deliberate all-tool/full-context baseline: every category is loaded.
        for name in registry.records:
            document = await registry.load(name, "presentation")
            argument["instructions"].append(
                {
                    "tool": name,
                    "category": "presentation",
                    "body": document.body.model_dump(mode="json"),
                }
            )
        positive = [row for row in rows if row["required"]]
        return {
            "evidence": (
                "Offline authored corpus and scripted adapters; no LLM/tokenizer/hosted API used."
            ),
            "fixture": (await registry.reference())["manifest"],
            "corpus_cases": len(rows),
            "mean_recall_at_1": sum(row["recall_at_1"] for row in positive) / len(positive),
            "mean_recall_at_3": sum(row["recall_at_3"] for row in positive) / len(positive),
            "mean_precision_at_3": sum(row["precision_at_3"] or 0 for row in positive)
            / len(positive),
            "negative_no_match_count": sum(row["no_match"] for row in rows if not row["required"]),
            "retrieval_cases": rows,
            "context_comparisons": comparisons,
            "all_seven_full_context_baseline": {
                "loaded_category_documents": registry.loaded_document_count,
                "total_request_bytes": len(canonical_json(argument).encode())
                + len(canonical_json(synthesis).encode()),
                "prospective_model_stages": 2,
            },
            "limits": [
                "Request bytes are not model tokens.",
                "Scripted adapters do not establish model quality.",
                "Authored recall is not a general retrieval benchmark.",
                "100 books are not a scale benchmark.",
            ],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/offline-experiment.json"))
    args = parser.parse_args()
    report = asyncio.run(experiment())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(args.output.resolve()),
                "corpus_cases": report["corpus_cases"],
                "recall_at_3": report["mean_recall_at_3"],
                "negative_no_match_count": report["negative_no_match_count"],
            },
            indent=2,
        )
    )
