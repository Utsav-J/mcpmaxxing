"""Build the one-turn tool-gating dataset from the committed bookstore fixture."""

import csv
import json
from pathlib import Path

from modern_mcp.bookstore import Bookstore
from modern_mcp.contracts import CONTRACTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets"
AUG = {"sold_from": "2026-08-01", "sold_before": "2026-09-01"}
RECEIPT_AUG = {"received_from": "2026-08-01", "received_before": "2026-09-01"}

# Each intent is (tool name, explicit expected arguments, selection rationale).
CASES = {
    "easy": [
        (
            "List all books in the catalog.",
            [("get_books", {}, "Catalog listing; no receipt detail requested.")],
        ),
        (
            "Tell me the title, author, and current stock for B001.",
            [
                (
                    "get_book_details",
                    {"book_id": "B001"},
                    "One exact book ID asks for catalog facts and lifetime totals.",
                )
            ],
        ),
        (
            "How many units of B003 are currently available?",
            [
                (
                    "get_stock_availability",
                    {"book_ids": ["B003"]},
                    "Current inventory snapshot, not sales history.",
                )
            ],
        ),
        (
            "Show the first page of stock receipts.",
            [
                (
                    "list_stock_receipts",
                    {"limit": 5},
                    "Individual dated receipt events are requested.",
                )
            ],
        ),
        (
            "Summarize vendor A's supply.",
            [
                (
                    "get_vendor_summary",
                    {"vendor_id": "VENDOR-A"},
                    "One vendor asks for one-vendor aggregate supply metrics.",
                )
            ],
        ),
        (
            "Give me monthly sales totals.",
            [("get_sales_trends", {}, "Grouped monthly totals, not event-level records.")],
        ),
        (
            "Compare vendors A and B by supply volume.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-B"]},
                    "Side-by-side supply comparison across two vendors.",
                )
            ],
        ),
        (
            "List individual sale records for B001.",
            [
                (
                    "get_sales",
                    {"book_ids": ["B001"], "limit": 5},
                    "Individual sale rows, not grouped trend buckets.",
                )
            ],
        ),
        (
            "List books in the fantasy genre.",
            [("get_books", {"genre": "fantasy"}, "Catalog filter by one canonical genre.")],
        ),
        (
            "Which books are out of stock?",
            [
                (
                    "get_stock_availability",
                    {"stock_status": "out_of_stock", "limit": 50},
                    "Current stock-status filter.",
                )
            ],
        ),
    ],
    "medium": [
        (
            "Which fiction books had receipts from vendor B during August 2026?",
            [
                (
                    "get_books",
                    {**RECEIPT_AUG, "genre": "fiction", "vendor_ids": ["VENDOR-B"]},
                    "Distinct catalog books filtered by same-receipt vendor/date and genre.",
                )
            ],
        ),
        (
            "Show B001 receipts from vendor B in August 2026.",
            [
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "book_ids": ["B001"], "vendor_ids": ["VENDOR-B"]},
                    "Dated receipt ledger with both book and vendor filters.",
                )
            ],
        ),
        (
            "Show low-stock science-fiction books.",
            [
                (
                    "get_stock_availability",
                    {"genre": "science-fiction", "stock_status": "low_stock", "limit": 50},
                    "Current stock state filtered by genre and status.",
                )
            ],
        ),
        (
            "Summarize vendor C's receipts during August 2026.",
            [
                (
                    "get_vendor_summary",
                    {"vendor_id": "VENDOR-C", **RECEIPT_AUG},
                    "One-vendor supply aggregate over an explicit receipt window.",
                )
            ],
        ),
        (
            "Give weekly fantasy sales for August 2026.",
            [
                (
                    "get_sales_trends",
                    {**AUG, "interval": "week", "genre": "fantasy"},
                    "Grouped calendar series with date and genre filters.",
                )
            ],
        ),
        (
            "List August sale rows in fiction with quantities from 3 through 6.",
            [
                (
                    "get_sales",
                    {**AUG, "genre": "fiction", "min_quantity": 3, "max_quantity": 6, "limit": 10},
                    "Detailed sale events with date, genre, and per-event quantity bounds.",
                )
            ],
        ),
        (
            "Compare all four vendors' receipt volume for August 2026.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-B", "VENDOR-C", "VENDOR-D"], **RECEIPT_AUG},
                    "Compare four vendors over the same bounded period.",
                )
            ],
        ),
        (
            "What are the catalog facts and lifetime stock totals for B100?",
            [
                (
                    "get_book_details",
                    {"book_id": "B100"},
                    "Exact-ID detail request; lifetime fixture totals.",
                )
            ],
        ),
        (
            "List fantasy books supplied by A or C in August 2026.",
            [
                (
                    "get_books",
                    {**RECEIPT_AUG, "genre": "fantasy", "vendor_ids": ["VENDOR-A", "VENDOR-C"]},
                    "OR across vendor IDs, AND with genre and receipt window.",
                )
            ],
        ),
        (
            "Show detailed sales of B003 with at least two units, from March through May 2026.",
            [
                (
                    "get_sales",
                    {
                        "sold_from": "2026-03-01",
                        "sold_before": "2026-06-01",
                        "book_ids": ["B003"],
                        "min_quantity": 2,
                        "limit": 20,
                    },
                    "Event-level sales filtered by book, date, and minimum quantity.",
                )
            ],
        ),
    ],
    "hard": [
        (
            "Show B001's current stock and its individual sale records.",
            [
                ("get_stock_availability", {"book_ids": ["B001"]}, "Current inventory snapshot."),
                (
                    "get_sales",
                    {"book_ids": ["B001"], "limit": 50},
                    "Individual event history requested alongside stock.",
                ),
            ],
        ),
        (
            "Compare vendors A and B for August receipts, and give me their monthly sales "
            "trend for August.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-B"], **RECEIPT_AUG},
                    "Vendor supply comparison.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "interval": "month"},
                    "Sales are a separate measure from receipts; grouped by month.",
                ),
            ],
        ),
        (
            "List science books in the catalog and the detailed receipts for science books "
            "in August.",
            [
                ("get_books", {"genre": "science"}, "Distinct catalog inventory by genre."),
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "genre": "science"},
                    "Event-level inbound receipts by genre and period.",
                ),
            ],
        ),
        (
            "Give me B001's lifetime totals and its August receipt rows.",
            [
                ("get_book_details", {"book_id": "B001"}, "One-book lifetime totals."),
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "book_ids": ["B001"]},
                    "Individual dated receipt events for that book.",
                ),
            ],
        ),
        (
            "Show current low-stock fantasy titles and daily fantasy sales for August.",
            [
                (
                    "get_stock_availability",
                    {"genre": "fantasy", "stock_status": "low_stock", "limit": 50},
                    "Current stock state filtered by genre and low-stock threshold.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "genre": "fantasy", "interval": "day"},
                    "Daily grouped sold-unit series for the same genre and date window.",
                ),
            ],
        ),
        (
            "Summarize vendor D's August supply and compare D with A over that same month.",
            [
                (
                    "get_vendor_summary",
                    {"vendor_id": "VENDOR-D", **RECEIPT_AUG},
                    "Detailed one-vendor summary.",
                ),
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-D"], **RECEIPT_AUG},
                    "Explicit pairwise comparison over identical dates.",
                ),
            ],
        ),
        (
            "Return August sale rows for B004 and weekly history sales for August.",
            [
                (
                    "get_sales",
                    {**AUG, "book_ids": ["B004"], "limit": 50},
                    "Event-level records for one exact book.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "interval": "week", "genre": "history"},
                    "Grouped weekly sales by the resolved history genre.",
                ),
            ],
        ),
        (
            "Which vendor supplied B003 in August, and how many units of B003 remain now?",
            [
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "book_ids": ["B003"]},
                    "Vendor/date-specific receipt rows for the book.",
                ),
                (
                    "get_stock_availability",
                    {"book_ids": ["B003"]},
                    "Current remaining inventory is a separate snapshot measure.",
                ),
            ],
        ),
        (
            "List books imported from vendor A in August and compare A's delivered volume "
            "with C's.",
            [
                (
                    "get_books",
                    {**RECEIPT_AUG, "vendor_ids": ["VENDOR-A"]},
                    "Distinct catalog books matching vendor and period.",
                ),
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-C"], **RECEIPT_AUG},
                    "Compare full delivered volume across the same window.",
                ),
            ],
        ),
        (
            "Give B002's individual sales and its current stock availability.",
            [
                (
                    "get_sales",
                    {"book_ids": ["B002"], "limit": 50},
                    "Individual sale records for the exact book.",
                ),
                (
                    "get_stock_availability",
                    {"book_ids": ["B002"]},
                    "Current remaining units, not lifetime sold units.",
                ),
            ],
        ),
    ],
    "very_complex": [
        (
            "For August 2026, compare vendors A–D by receipt volume, show B001's actual "
            "sales rows, and give the whole-store weekly sales trend.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-B", "VENDOR-C", "VENDOR-D"], **RECEIPT_AUG},
                    "Four-way supply comparison for the requested receipt window.",
                ),
                (
                    "get_sales",
                    {**AUG, "book_ids": ["B001"], "limit": 50},
                    "Raw event rows for one book, distinct from trend aggregation.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "interval": "week"},
                    "Whole-store weekly totals for the same calendar window.",
                ),
            ],
        ),
        (
            "Find fantasy books received from A or C in August, list the matching receipt "
            "rows, and report current availability for fantasy books.",
            [
                (
                    "get_books",
                    {
                        **RECEIPT_AUG,
                        "genre": "fantasy",
                        "vendor_ids": ["VENDOR-A", "VENDOR-C"],
                        "limit": 50,
                    },
                    "Resolve distinct catalog books using same-receipt matching.",
                ),
                (
                    "list_stock_receipts",
                    {
                        **RECEIPT_AUG,
                        "genre": "fantasy",
                        "vendor_ids": ["VENDOR-A", "VENDOR-C"],
                        "limit": 50,
                    },
                    "Show underlying receipt events with the exact same filters.",
                ),
                (
                    "get_stock_availability",
                    {"genre": "fantasy", "limit": 50},
                    "Current stock is a separate snapshot, not implied by receipts.",
                ),
            ],
        ),
        (
            "For science-fiction sales in August with quantity 3–6, show event rows, then "
            "summarize the same dates by day.",
            [
                (
                    "get_sales",
                    {
                        **AUG,
                        "genre": "science-fiction",
                        "min_quantity": 3,
                        "max_quantity": 6,
                        "limit": 50,
                    },
                    "Detailed transactions with per-sale quantity bounds.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "genre": "science-fiction", "interval": "day"},
                    "Daily aggregate series; do not apply transaction-level quantity filters "
                    "to grouped totals.",
                ),
            ],
        ),
        (
            "Give vendor B's August receipt summary, its August receipt ledger, and compare "
            "B with D for the same period.",
            [
                (
                    "get_vendor_summary",
                    {"vendor_id": "VENDOR-B", **RECEIPT_AUG},
                    "Aggregate one-vendor metrics.",
                ),
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "vendor_ids": ["VENDOR-B"], "limit": 50},
                    "Individual receipt rows for the same vendor and window.",
                ),
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-B", "VENDOR-D"], **RECEIPT_AUG},
                    "Side-by-side common-window vendor comparison.",
                ),
            ],
        ),
        (
            "For B001, report its current stock and August sale records, plus daily fiction "
            "sales for August.",
            [
                ("get_stock_availability", {"book_ids": ["B001"]}, "Current inventory snapshot."),
                (
                    "get_sales",
                    {**AUG, "book_ids": ["B001"], "limit": 50},
                    "Individual transactions for B001.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "genre": "fiction", "interval": "day"},
                    "Daily grouped sales for B001's fixture genre; explicitly a genre-level trend.",
                ),
            ],
        ),
        (
            "List all out-of-stock history books, show March history receipts, and compare "
            "vendors A and C by total March receipt volume.",
            [
                (
                    "get_stock_availability",
                    {"genre": "history", "stock_status": "out_of_stock", "limit": 50},
                    "Current inventory status and genre.",
                ),
                (
                    "list_stock_receipts",
                    {
                        "received_from": "2026-03-01",
                        "received_before": "2026-04-01",
                        "genre": "history",
                        "limit": 50,
                    },
                    "Historical inbound receipt rows for the genre.",
                ),
                (
                    "compare_vendors",
                    {
                        "vendor_ids": ["VENDOR-A", "VENDOR-C"],
                        "received_from": "2026-03-01",
                        "received_before": "2026-04-01",
                    },
                    "Compare supply totals for the same March receipt window.",
                ),
            ],
        ),
        (
            "Compare all vendors' August supply, then list August science sales with at least "
            "four units and give monthly science totals.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-B", "VENDOR-C", "VENDOR-D"], **RECEIPT_AUG},
                    "Compare four suppliers by incoming supply.",
                ),
                (
                    "get_sales",
                    {**AUG, "genre": "science", "min_quantity": 4, "limit": 50},
                    "Detailed individual science sales above the per-event quantity threshold.",
                ),
                (
                    "get_sales_trends",
                    {**AUG, "genre": "science", "interval": "month"},
                    "Monthly aggregate units; not filtered by each event's minimum quantity.",
                ),
            ],
        ),
        (
            "Find books with August receipts from vendor D, check the exact August receipt "
            "history for B004, and give B004's lifetime book totals.",
            [
                (
                    "get_books",
                    {**RECEIPT_AUG, "vendor_ids": ["VENDOR-D"], "limit": 50},
                    "Distinct books matched by vendor and August receipts.",
                ),
                (
                    "list_stock_receipts",
                    {**RECEIPT_AUG, "book_ids": ["B004"]},
                    "B004's individual August receipts, regardless of vendor.",
                ),
                (
                    "get_book_details",
                    {"book_id": "B004"},
                    "Lifetime totals and identity for the exact book.",
                ),
            ],
        ),
        (
            "For each vendor A and C, compare August receipts; also show the detailed sales "
            "rows for fiction books in August whose sale quantity is 2–5.",
            [
                (
                    "compare_vendors",
                    {"vendor_ids": ["VENDOR-A", "VENDOR-C"], **RECEIPT_AUG},
                    "Vendor supply comparison.",
                ),
                (
                    "get_sales",
                    {**AUG, "genre": "fiction", "min_quantity": 2, "max_quantity": 5, "limit": 50},
                    "Detailed transaction rows with genre and per-row quantity range.",
                ),
            ],
        ),
        (
            "Show weekly science-fiction sales for the full fixture period, detailed sales "
            "records for B002 over that period, and B002's current availability.",
            [
                (
                    "get_sales_trends",
                    {"interval": "week", "genre": "science-fiction"},
                    "Full-period grouped weekly trend for a genre.",
                ),
                (
                    "get_sales",
                    {"book_ids": ["B002"], "limit": 50},
                    "Full-period transaction ledger for the exact book.",
                ),
                (
                    "get_stock_availability",
                    {"book_ids": ["B002"]},
                    "Current availability snapshot.",
                ),
            ],
        ),
    ],
}


def summarize(tool: str, data: dict) -> str:
    if tool == "get_books":
        return f"{data['total_count']} books matched the catalog filters."
    if tool == "get_book_details":
        return (
            f"{data['book_id']} is {data['title']} by {data['author']}; "
            f"{data['stock_units']} units remain in the fixture snapshot."
        )
    if tool == "get_stock_availability":
        items = data["items"]
        if len(items) == 1:
            row = items[0]
            return f"{row['book_id']} has {row['stock_units']} units and is {row['stock_status']}."
        return f"{data['total_count']} books match the current stock filters."
    if tool == "list_stock_receipts":
        return (
            f"Found {data['receipt_count']} receipt rows totaling {data['received_units']} units "
            f"across {data['unique_book_count']} books."
        )
    if tool == "get_vendor_summary":
        return (
            f"{data['vendor_name']} supplied {data['received_units']} units in "
            f"{data['receipt_count']} receipt rows."
        )
    if tool == "compare_vendors":
        return (
            "; ".join(
                f"{item['vendor_name']}: {item['received_units']} units" for item in data["items"]
            )
            + "."
        )
    if tool == "get_sales_trends":
        filters = data["applied_filters"]
        period = f"{filters['sold_from']} to {filters['sold_before']}"
        return (
            f"Recorded {data['total_sold_units']} sold units in {period}, "
            f"grouped by {data['interval']}."
        )
    if tool == "get_sales":
        return (
            f"Found {data['total_count']} matching sale records totaling "
            f"{data['total_sold_units']} units; showing {len(data['items'])} on this page."
        )
    raise ValueError(f"No summary formatter for {tool}.")


def main():
    store = Bookstore()
    answers, mappings = [], []
    for difficulty, cases in CASES.items():
        if len(cases) != 10:
            raise ValueError(f"Expected 10 {difficulty} cases; found {len(cases)}.")
        prefix = {"easy": "E", "medium": "M", "hard": "H", "very_complex": "V"}[difficulty]
        for index, (query, intents) in enumerate(cases, start=1):
            query_id = f"{prefix}{index:02}"
            response_parts = []
            for call_order, (tool_name, arguments, rationale) in enumerate(intents, start=1):
                contract = CONTRACTS[tool_name]
                request = contract.input_model.model_validate(arguments)
                result = getattr(store, tool_name)(request).model_dump(mode="json")["data"]
                response_parts.append(summarize(tool_name, result))
                mappings.append(
                    {
                        "query_id": query_id,
                        "difficulty": difficulty,
                        "query": query,
                        "tool_name": tool_name,
                        "intent_index": call_order,
                        "expected_arguments_json": json.dumps(arguments, sort_keys=True),
                        "selection_rationale": rationale,
                    }
                )
            answers.append(
                {
                    "query_id": query_id,
                    "difficulty": difficulty,
                    "query": query,
                    "high_level_answer": " ".join(response_parts),
                }
            )

    OUT.mkdir(exist_ok=True)
    with (OUT / "query_to_answer.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=answers[0].keys())
        writer.writeheader()
        writer.writerows(answers)
    with (OUT / "query_to_tool.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=mappings[0].keys())
        writer.writeheader()
        writer.writerows(mappings)


if __name__ == "__main__":
    main()
