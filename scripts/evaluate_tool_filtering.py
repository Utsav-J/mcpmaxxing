"""Compare the BM25 baseline with opt-in BM25+embedding tool retrieval."""

import argparse
import asyncio
import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import Client

from examples.agent.cache import Cache
from examples.agent.embeddings import DIMENSIONS, MODEL, GoogleEmbeddingClient
from examples.agent.registry import ToolContextRegistry
from modern_mcp.server import create_server

DATASET = Path("datasets/query_to_tool.csv")
TOOLS = (
    "get_books",
    "get_book_details",
    "list_stock_receipts",
    "get_stock_availability",
    "get_vendor_summary",
    "get_sales_trends",
    "get_sales",
    "compare_vendors",
)
DIFFICULTIES = ("easy", "medium", "hard", "very_complex")


def read_queries(path):
    grouped = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            item = grouped.setdefault(
                row["query_id"],
                {"query": row["query"], "difficulty": row["difficulty"], "gold": set()},
            )
            if item["query"] != row["query"] or item["difficulty"] != row["difficulty"]:
                raise ValueError(f"Inconsistent repeated query row: {row['query_id']}")
            item["gold"].add(row["tool_name"])
    if not grouped:
        raise ValueError(f"Dataset is empty: {path}")
    return grouped


def summarize(rows):
    query_count = len(rows)
    intent_count = sum(len(row["gold"]) for row in rows)
    retrieved_intents = sum(len(row["gold"] & set(row["ranked"])) for row in rows)
    candidate_count = sum(len(row["ranked"]) for row in rows)
    exact = sum(row["gold"] <= set(row["ranked"]) for row in rows)
    hits = sum(bool(row["gold"] & set(row["ranked"])) for row in rows)
    macro_recall = (
        sum(len(row["gold"] & set(row["ranked"])) / len(row["gold"]) for row in rows) / query_count
    )
    return {
        "macro_recall": macro_recall,
        "intent_recall": retrieved_intents / intent_count,
        "strict_accuracy": exact / query_count,
        "hit_rate": hits / query_count,
        "precision": retrieved_intents / candidate_count if candidate_count else 0,
        "avg_candidates": candidate_count / query_count,
        "retrieved_intents": retrieved_intents,
        "intent_count": intent_count,
        "exact_queries": exact,
        "query_count": query_count,
    }


def percent(value):
    return f"{value * 100:.1f}%"


def report_markdown(dataset, baseline, hybrid, tool_count):
    lines = [
        "# Deterministic BM25 vs. BM25 + Embedding Tool Filtering",
        "",
        "## Setup",
        "",
        f"- Dataset: `{dataset.as_posix()}`",
        f"- Queries: {len(baseline[0]['rows'])} labeled queries; "
        f"{baseline[0]['summary']['intent_count']} expected tool intents",
        f"- Catalog: {tool_count} tools",
        f"- Embedding model: `{MODEL}` ({DIMENSIONS} dimensions)",
        "- Query embeddings: computed once per query for this evaluation and reused "
        "across K values; runtime embeds each retrieval request.",
        "- Tool embeddings: content-addressed and durably cached in SQLite; query "
        "embeddings are not persisted.",
        "- Hybrid: top-K BM25 and embedding shortlists, deduplicated and fused by "
        "reciprocal rank fusion (RRF), then truncated to final K. RRF constant: 60.",
        "- Scores/rankings are evaluated directly; no chat/intent-generation model call.",
        "",
        "`Macro recall@K` averages each query's fraction of required tools retrieved, "
        "so multi-tool queries do not receive extra weight. `Intent recall@K` is the "
        "micro-average across all required tool labels. `Strict accuracy@K` requires "
        "every required tool for a query to appear. Candidate precision counts tools "
        "not labeled for that query as extra candidates.",
        "",
        "## Aggregate results by K",
        "",
        "| K | Method | Macro recall | Intent recall | Strict accuracy | Hit rate | "
        "Candidate precision | Avg candidates |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for index, k in enumerate(range(1, tool_count + 1)):
        for label, series in (("BM25", baseline), ("BM25 + embedding (RRF)", hybrid)):
            result = series[index]["summary"]
            lines.append(
                f"| {k} | {label} | {percent(result['macro_recall'])} | "
                f"{percent(result['intent_recall'])} "
                f"({result['retrieved_intents']}/{result['intent_count']}) | "
                f"{percent(result['strict_accuracy'])} "
                f"({result['exact_queries']}/{result['query_count']}) | "
                f"{percent(result['hit_rate'])} | {percent(result['precision'])} | "
                f"{result['avg_candidates']:.2f} |"
            )
    lines.extend(["", "## Comparison highlights", ""])
    for k, label in ((3, "Current default K=3"), (5, "Smallest K with full hybrid coverage")):
        if k > tool_count:
            continue
        base = baseline[k - 1]["summary"]
        fused = hybrid[k - 1]["summary"]
        strict_delta = (fused["strict_accuracy"] - base["strict_accuracy"]) * 100
        recall_delta = (fused["macro_recall"] - base["macro_recall"]) * 100
        lines.append(
            f"- **{label}:** strict accuracy {percent(base['strict_accuracy'])} → "
            f"{percent(fused['strict_accuracy'])} ({strict_delta:+.1f} percentage points); "
            f"macro recall {percent(base['macro_recall'])} → "
            f"{percent(fused['macro_recall'])} ({recall_delta:+.1f} pp)."
        )
    lines.extend(
        [
            "",
            "## Results by difficulty",
            "",
            "The following table shows strict query accuracy (all expected tools retrieved).",
            "",
            "| K | Method | Easy | Medium | Hard | Very complex |",
            "|---:|---|---:|---:|---:|---:|",
        ]
    )
    for index, k in enumerate(range(1, tool_count + 1)):
        for label, series in (("BM25", baseline), ("BM25 + embedding (RRF)", hybrid)):
            portions = [
                summarize([r for r in series[index]["rows"] if r["difficulty"] == difficulty])
                for difficulty in DIFFICULTIES
            ]
            cells = [
                f"{percent(row['strict_accuracy'])} ({row['exact_queries']}/{row['query_count']})"
                for row in portions
            ]
            lines.append(f"| {k} | {label} | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Interpretation notes",
            "",
            "- Compare the same K across methods; increasing K also increases the shortlist "
            "size for each retriever in the hybrid method.",
            "- The hybrid retrieves the union of two shortlists before RRF, so it can return "
            "fewer than K candidates if neither retriever has enough positive matches.",
            "- This authored dataset contains positive required-tool labels only. It does "
            "not measure unrelated-query rejection or abstention.",
            "- Retrieval coverage is not end-to-end tool-selection accuracy, argument "
            "accuracy, or final-answer quality. Production LLM intent rewriting is omitted.",
            "- Tool vectors use a durable content-addressed SQLite cache. Cache identity "
            "includes tool name/content, embedding provider/model, dimensions, and task type; "
            "changed inputs result in a fresh embedding. Query vectors are held only in memory.",
            "",
        ]
    )
    return "\n".join(lines)


async def evaluate(dataset, output, cache_path):
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GOOGLE_API_KEY to run the embedding comparison.")
    queries = read_queries(dataset)
    provider = GoogleEmbeddingClient(os.environ["GOOGLE_API_KEY"])
    cache = Cache(cache_path, "tool-filter-evaluation")
    try:
        async with Client(create_server()) as client:
            baseline_registry = ToolContextRegistry(client, "local-evaluation")
            await baseline_registry.refresh()
            hybrid_registry = ToolContextRegistry(
                client,
                "local-evaluation",
                cache=cache,
                embedding_enabled=True,
                embedding_client=provider,
            )
            await hybrid_registry.warm()
            tool_count = len(hybrid_registry.records)
            if set(hybrid_registry.records) != set(TOOLS):
                raise RuntimeError(
                    "The MCP tool inventory differs from the expected dataset catalog."
                )

            query_vectors = {}
            for query_id, item in queries.items():
                vectors = await hybrid_registry.embed_query(item["query"])
                if len(vectors) != 1:
                    raise RuntimeError("Embedding provider returned a mismatched query count.")
                query_vectors[query_id] = vectors[0]

            baseline, hybrid = [], []
            for k in range(1, tool_count + 1):
                baseline_rows, hybrid_rows = [], []
                for query_id, item in queries.items():
                    bm25_names = [name for name, _ in baseline_registry.retrieve(item["query"], k)]
                    hybrid_names = [
                        name
                        for name, _ in hybrid_registry.retrieve_with_query_vector(
                            item["query"], query_vectors[query_id], k
                        )
                    ]
                    common = {
                        "query_id": query_id,
                        "difficulty": item["difficulty"],
                        "gold": set(item["gold"]),
                    }
                    baseline_rows.append({**common, "ranked": bm25_names})
                    hybrid_rows.append({**common, "ranked": hybrid_names})
                baseline.append({"rows": baseline_rows, "summary": summarize(baseline_rows)})
                hybrid.append({"rows": hybrid_rows, "summary": summarize(hybrid_rows)})

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_markdown(dataset, baseline, hybrid, tool_count), encoding="utf-8")
        print(f"Report written to {output.resolve()}")
        print("\nK | BM25 strict accuracy | Hybrid strict accuracy | BM25 recall | Hybrid recall")
        for k, base, fused in zip(range(1, tool_count + 1), baseline, hybrid, strict=True):
            print(
                f"{k} | {percent(base['summary']['strict_accuracy'])} | "
                f"{percent(fused['summary']['strict_accuracy'])} | "
                f"{percent(base['summary']['macro_recall'])} | "
                f"{percent(fused['summary']['macro_recall'])}"
            )
    finally:
        await provider.aclose()


def main():
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/tool-filtering-comparison.md")
    )
    parser.add_argument(
        "--cache-path", type=Path, default=Path("artifacts/evaluation/embedding-cache.sqlite3")
    )
    args = parser.parse_args()
    asyncio.run(evaluate(args.dataset, args.output, args.cache_path))


if __name__ == "__main__":
    main()
