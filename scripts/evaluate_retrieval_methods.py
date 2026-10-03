"""Evaluate raw retrieval and Gemini intent decomposition at candidate caps 1..3."""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from mcp import Client

from examples.agent.cache import Cache
from examples.agent.embeddings import GoogleEmbeddingClient
from examples.agent.graph import BOOKSTORE_ROLE, GeminiAdapter, intent_request
from examples.agent.registry import ToolContextRegistry, digest
from modern_mcp.server import create_server
from scripts.evaluate_tool_filtering import percent, read_queries, summarize


async def evaluate(args):
    load_dotenv(Path.cwd() / ".env")
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GOOGLE_API_KEY.")
    queries = read_queries(args.dataset)
    fingerprint = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    prompt_hash = digest(
        {
            "request": intent_request("", [], per_intent=True),
            "role": BOOKSTORE_ROLE,
            "schema_version": 2,
        }
    )
    identity = {"dataset_sha256": fingerprint, "model": args.model, "prompt_sha256": prompt_hash}
    if args.routes.exists() and not args.regenerate:
        saved = json.loads(args.routes.read_text("utf-8"))
        if saved["identity"] != identity:
            raise ValueError("Saved intent splits use different inputs; use --regenerate.")
    else:
        saved = {"identity": identity, "routes": {}, "events": []}
    model = ChatGoogleGenerativeAI(
        model=args.model, vertexai=False, temperature=0, timeout=60, max_retries=0
    )
    adapter = GeminiAdapter(model, saved["events"].append)
    args.routes.parent.mkdir(parents=True, exist_ok=True)
    for query_id, item in queries.items():
        if query_id in saved["routes"]:
            continue
        request = intent_request(item["query"], [], per_intent=True)
        saved["routes"][query_id] = await adapter.route(request)
        args.routes.write_text(json.dumps(saved, indent=2, ensure_ascii=False), "utf-8")
        print(f"Intent generated: {query_id}", flush=True)
        await asyncio.sleep(args.request_interval)

    provider = GoogleEmbeddingClient(os.environ["GOOGLE_API_KEY"])
    all_rows = []
    try:
        async with Client(create_server()) as client:
            registry = ToolContextRegistry(client, "method-eval")
            await registry.refresh()
            hybrid = ToolContextRegistry(
                client,
                "method-eval",
                cache=Cache(args.cache, "method-eval"),
                embedding_enabled=True,
                embedding_client=provider,
            )
            await hybrid.warm()
            vectors = {}
            for query_id, item in queries.items():
                vectors[query_id] = (await hybrid.embed_query(item["query"]))[0]
            for cap in range(1, 4):
                for query_id, item in queries.items():
                    route = saved["routes"][query_id]
                    ranks = {
                        "BM25 raw": registry.retrieve(item["query"], cap),
                        "BM25 normalized raw": registry.retrieve(
                            item["query"], cap, normalize=True
                        ),
                        "BM25 + embedding RRF raw": hybrid.retrieve_with_query_vector(
                            item["query"], vectors[query_id], cap
                        ),
                    }
                    if route["kind"] == "tools":
                        ranks.update(
                            {
                                "BM25 whole-query rewrite": registry.retrieve(
                                    route["retrieval_query"], cap
                                ),
                                "BM25 per-intent": await registry.retrieve_per_intent(
                                    route["retrieval_queries"], cap
                                ),
                                "BM25 normalized per-intent": await registry.retrieve_per_intent(
                                    route["retrieval_queries"], cap, normalize=True
                                ),
                            }
                        )
                    else:
                        ranks.update(
                            {
                                name: []
                                for name in (
                                    "BM25 whole-query rewrite",
                                    "BM25 per-intent",
                                    "BM25 normalized per-intent",
                                )
                            }
                        )
                    for method, ranked in ranks.items():
                        all_rows.append(
                            {
                                "cap": cap,
                                "method": method,
                                "query_id": query_id,
                                "difficulty": item["difficulty"],
                                "query": item["query"],
                                "gold": set(item["gold"]),
                                "ranked": [name for name, _ in ranked],
                            }
                        )
            snapshot = registry.snapshot
    finally:
        await provider.aclose()

    methods = list(dict.fromkeys(row["method"] for row in all_rows))
    lines = [
        "# Retrieval comparison: maximum K=3",
        "",
        f"Run: {datetime.now(UTC).isoformat()}",
        "",
        "## Methodology",
        "",
        f"- Dataset: `{args.dataset.as_posix()}`; SHA-256 `{fingerprint}`.",
        f"- {len(queries)} queries; "
        f"{sum(len(q['gold']) for q in queries.values())} required tool labels.",
        f"- Catalog snapshot: `{snapshot}`.",
        f"- Intent model: `{args.model}`, temperature=0; one call per query, no history.",
        "- Gemini sees only query text and the production intent prompt: no tool catalog, "
        "gold labels, expected arguments, difficulty, or selection rationale. "
        "Generated text splits are frozen locally.",
        f"- Intent artifact: `{args.routes.as_posix()}`. "
        "Reuse with matching dataset/model/prompt hashes.",
        "- Raw baselines reproduce the earlier raw-query experiment. Whole-query rewrite is a "
        "control "
        "to separate rewriting effects from splitting effects; it uses the same intent response. "
        "When the model omits the optional whole-query text, its subqueries are joined "
        "with semicolons.",
        "- Normalization: deterministic English plural suffix reduction on corpus "
        "and query tokens; "
        "no hand-tuned aliases, metadata changes, or weight fitting on evaluation labels.",
        "- Per-intent: top-1 BM25 match per generated independent ask, deduplicated in ask order, "
        "with total cap K; no padding. Duplicate top tools do not trigger second-choice filling.",
        "- Embedding reference: gemini-embedding-001, 768 dimensions, normalized cosine; two top-K "
        "shortlists fused with equal-weight RRF (constant 60), then final cap K.",
        "- Query embeddings are recomputed in this run, reused across caps, and not persisted. "
        "Only tool embeddings use durable SQLite storage.",
        "- Strict accuracy requires all gold tools; macro recall weights queries equally; "
        "precision counts unlabeled candidates as extras. This is retrieval-only, "
        "not final call/answer accuracy.",
        "",
        "## Results",
        "",
        "| Max K | Method | Strict accuracy | Macro recall | Intent recall | "
        "Precision | Avg candidates |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for cap in range(1, 4):
        for method in methods:
            rows = [r for r in all_rows if r["cap"] == cap and r["method"] == method]
            metric = summarize(rows)
            lines.append(
                f"| {cap} | {method} | {percent(metric['strict_accuracy'])} "
                f"({metric['exact_queries']}/{metric['query_count']}) | "
                f"{percent(metric['macro_recall'])} | {percent(metric['intent_recall'])} | "
                f"{percent(metric['precision'])} | {metric['avg_candidates']:.2f} |"
            )
    lines += ["", "## Takeaway at K=3", ""]
    for method in methods:
        subset = [r for r in all_rows if r["cap"] == 3 and r["method"] == method]
        result = summarize(subset)
        lines.append(
            f"- **{method}:** {percent(result['strict_accuracy'])} strict accuracy, "
            f"{result['avg_candidates']:.2f} average candidates."
        )
    lines += [
        "",
        "The top-1-per-intent policy can reduce candidate count by discarding alternatives. "
        "A smaller candidate set is only useful if required-tool coverage survives; evaluate both "
        "metrics together. No production default was changed.",
        "",
        "## Difficulty breakdown at K=3",
        "",
        "| Method | Easy | Medium | Hard | Very complex |",
        "|---|---:|---:|---:|---:|",
    ]
    for method in methods:
        cells = []
        for difficulty in ("easy", "medium", "hard", "very_complex"):
            rows = [
                r
                for r in all_rows
                if r["cap"] == 3 and r["method"] == method and r["difficulty"] == difficulty
            ]
            cells.append(percent(summarize(rows)["strict_accuracy"]))
        lines.append("| " + method + " | " + " | ".join(cells) + " |")
    lines += ["", "## Misses at K=3", ""]
    for method in methods:
        lines += [f"### {method}", ""]
        misses = [
            r
            for r in all_rows
            if r["cap"] == 3 and r["method"] == method and not r["gold"] <= set(r["ranked"])
        ]
        if not misses:
            lines.append("All required tools retrieved for all queries.")
        for row in misses:
            missing = sorted(row["gold"] - set(row["ranked"]))
            lines.append(
                f"- **{row['query_id']}**: missing `{', '.join(missing)}`; "
                f"candidates: `{', '.join(row['ranked'])}`."
            )
        lines.append("")
    lines += [
        "## Limitations",
        "",
        "One authored 40-query corpus and one frozen Gemini generation per query; not a "
        "statistically robust estimate of generalization or model variability. No unrelated-query "
        "negatives. Methods were not tuned to labels, but were motivated by earlier error analysis "
        "on this corpus; validate on fresh queries before changing production defaults.",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), "utf-8")
    details = args.output.with_suffix(".json")
    details.write_text(
        json.dumps(
            {"identity": identity, "snapshot": snapshot, "rows": all_rows},
            default=lambda value: sorted(value),
            indent=2,
        ),
        "utf-8",
    )
    print(f"Report: {args.output.resolve()}")
    print(
        "\n".join(lines[lines.index("## Results") : lines.index("## Difficulty breakdown at K=3")])
    )


def main():
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("datasets/query_to_tool.csv"))
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    parser.add_argument(
        "--routes", type=Path, default=Path("artifacts/evaluation/intent-splits.json")
    )
    parser.add_argument(
        "--cache", type=Path, default=Path("artifacts/evaluation/method-cache.sqlite3")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/retrieval-method-comparison.md")
    )
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=4.5,
        help="Seconds between intent calls to respect API rate limits.",
    )
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
