"""Author the committed JSON context documents. Not used by the running server."""

import json
from pathlib import Path

from modern_mcp.contracts import CONTRACTS

CONTEXT = {
    "get_books": {
        "keywords": [
            "books",
            "catalog",
            "list",
            "genre",
            "imported",
            "received",
            "vendor",
            "titles",
            "find",
            "browse",
        ],
        "queries": [
            "Show books imported last month from vendor A",
            "List fantasy books in the catalog",
        ],
        "use": (
            "Find distinct catalog books, including books matched through "
            "vendor/date receipt filters."
        ),
        "avoid": (
            "Use list_stock_receipts for individual arrivals; "
            "get_stock_availability for remaining units."
        ),
        "parameters": [
            {
                "parameter": "vendor_ids",
                "rules": [
                    "OR within IDs; AND with genre and receipt window.",
                    "Vendor and date must match the SAME receipt row.",
                ],
                "examples": ['["VENDOR-A","VENDOR-B"]'],
            },
            {
                "parameter": "received_from/received_before",
                "rules": [
                    "Translate last month using the reference clock, not today's clock.",
                    "Supply both ISO bounds or neither.",
                ],
                "examples": ["2026-08-01 inclusive, 2026-09-01 exclusive"],
            },
        ],
        "terms": {
            "catalog book": "A distinct local book, not a delivery row.",
            "matched_received_units": (
                "Units summed from receipt rows matching ALL filters, not remaining stock."
            ),
        },
        "rules": [
            "Repeated deliveries do not duplicate catalog results.",
            "With no receipt filters, include unsupplied catalog books.",
        ],
        "example": (
            "B001 arrived from A in July and September and B in August; "
            "an August A query must not return it."
        ),
        "format": "table",
        "formats": [
            "single: short labeled book entry",
            "multiple: book_id/title/genre table",
            "source: genuine resource link if supported; otherwise source label",
        ],
        "facts": ["Applied filters", "Page completeness", "Received units are not available stock"],
    },
    "get_book_details": {
        "keywords": [
            "book",
            "details",
            "detail",
            "everything",
            "information",
            "B001",
            "author",
            "title",
            "about",
            "identity",
        ],
        "queries": ["Tell me everything about book B001", "What is B001"],
        "use": "Retrieve one exact book's identity and lifetime fixture totals.",
        "avoid": (
            "Do not guess an ID from a title. Resolve via get_books first; "
            "use receipt tool for a ledger."
        ),
        "parameters": [
            {
                "parameter": "book_id",
                "rules": ["Use an existing local ID such as B001; unknown IDs fail."],
                "examples": ["B001"],
            }
        ],
        "terms": {
            "book_id": "Local catalog identity, not ISBN.",
            "lifetime totals": "Totals over fixture coverage only.",
        },
        "rules": [
            "Detail totals obey stock = received minus sold.",
            "The bounded detail omits full receipt and sales history.",
        ],
        "example": "B001 has 20 received, 3 sold, and 17 remaining units in this fixture.",
        "format": "detail",
        "formats": [
            "single: titled key/value facts",
            "source: link book resource if host can open it; otherwise labeled reference",
        ],
        "facts": ["Book ID", "Snapshot date for stock", "Fixture scope for totals"],
    },
    "list_stock_receipts": {
        "keywords": [
            "receipts",
            "receipt",
            "arrivals",
            "arrived",
            "deliveries",
            "delivery",
            "ledger",
            "when",
            "history",
            "quantity",
            "import",
            "dated",
        ],
        "queries": ["When did B001 arrive", "List dated vendor receipt quantities"],
        "use": "Inspect individual vendor receipt events, dates, and delivered quantities.",
        "avoid": (
            "Use get_books for distinct catalog rows, "
            "get_stock_availability for current remaining units."
        ),
        "parameters": [
            {
                "parameter": "received_from/received_before",
                "rules": ["Both ISO dates or neither; start included, end excluded."],
                "examples": ["2026-08-01 to 2026-09-01"],
            },
            {
                "parameter": "book_ids/vendor_ids",
                "rules": ["Distinct known IDs; OR within each list, AND across filters."],
                "examples": ['book_ids=["B001"]'],
            },
        ],
        "terms": {
            "receipt row": "One book arriving from one vendor with a date and positive quantity.",
            "receipt_count": "Count of matched rows, not units or shipment invoices.",
        },
        "rules": [
            "Received units, unique books, and receipt count are different measures.",
            "Full-match totals include every page.",
        ],
        "example": "Three B001 receipt events deliver 20 units but represent one unique book.",
        "format": "table",
        "formats": [
            "chronological: receipt/date/vendor/book/quantity rows",
            "source: link only when host supports the returned resource URI",
        ],
        "facts": [
            "Inclusive/exclusive period",
            "Full-match totals versus page rows",
            "Pagination notice",
        ],
    },
    "get_stock_availability": {
        "keywords": [
            "stock",
            "available",
            "availability",
            "copies",
            "remaining",
            "on",
            "hand",
            "inventory",
            "low",
            "out",
            "units",
        ],
        "queries": ["How many copies are available", "Show low stock inventory"],
        "use": "Read current snapshot availability for catalog books.",
        "avoid": (
            "Do not answer historical stock questions using this snapshot; "
            "no historical parameter exists."
        ),
        "parameters": [
            {
                "parameter": "stock_status",
                "rules": ["all, out_of_stock, low_stock, in_stock are exact enum values."],
                "examples": ["low_stock"],
            },
            {
                "parameter": "book_ids",
                "rules": ["Supply distinct known IDs or null for all."],
                "examples": ['["B003"]'],
            },
        ],
        "terms": {
            "available units": "Received units minus sold units; equal to on-hand here.",
            "low_stock": "1–5 units; out-of-stock means zero.",
        },
        "rules": [
            "No reservations, returns, or backorders.",
            "All values use the fixed 2026-09-26 snapshot.",
        ],
        "example": "B003 has 3 units available; B002 is out of stock; B100 was never supplied.",
        "format": "scalar",
        "formats": [
            "single: book ID and value with units",
            "multiple: stock table with text status labels",
        ],
        "facts": [
            "Units",
            "2026-09-26 snapshot",
            "Low/out-of-stock text labels",
            "Page completeness",
        ],
    },
    "get_vendor_summary": {
        "keywords": [
            "vendor",
            "supplier",
            "summary",
            "totals",
            "total",
            "supplied",
            "supply",
            "one",
            "volume",
            "breakdown",
        ],
        "queries": ["Vendor B supply totals", "Summarize one supplier's delivered units"],
        "use": "Aggregate supply volume for one known vendor over a common receipt window.",
        "avoid": (
            "Use compare_vendors for two or more vendors; this does not measure vendor quality."
        ),
        "parameters": [
            {
                "parameter": "vendor_id",
                "rules": ["One canonical ID from bookstore://reference."],
                "examples": ["VENDOR-B"],
            }
        ],
        "terms": {
            "unique books": "Distinct book IDs received in the selected window.",
            "genre breakdown": "Per-genre supplied counts and units, including zeros.",
        },
        "rules": [
            "Supply volume is not pricing, reliability, or quality evidence.",
            "Summary arithmetic uses the full matched set.",
        ],
        "example": (
            "A vendor may deliver the same book twice: two receipts, one unique book, summed units."
        ),
        "format": "detail",
        "formats": [
            "one metric: scalar with period",
            "several metrics: labeled summary",
            "genre request: small breakdown table",
        ],
        "facts": [
            "Vendor name and ID",
            "Receipt period",
            "Distinct definitions of units/books/receipts",
        ],
    },
    "get_sales": {
        "keywords": [
            "sales",
            "sale",
            "transactions",
            "ledger",
            "records",
            "individual",
            "detailed",
            "rows",
            "quantity",
            "weekday",
            "book",
        ],
        "queries": [
            "Show individual sales for August",
            "List sale records for B001 with quantities",
            "Find large sales in the science genre",
        ],
        "use": "List individual sale records enriched with book details and calendar fields.",
        "avoid": (
            "Use get_sales_trends for grouped totals or charts. Revenue and vendor attribution "
            "are not available in the fixture."
        ),
        "parameters": [
            {
                "parameter": "sold_from/sold_before",
                "rules": [
                    "These are SALE date bounds; both provided or neither; start included, "
                    "end excluded."
                ],
                "examples": ["2026-08-01 to 2026-09-01"],
            },
            {
                "parameter": "book_ids/genre",
                "rules": [
                    "Use known book IDs; filters combine with AND; IDs inside the list are OR."
                ],
                "examples": ['book_ids=["B001"]', "genre=fiction"],
            },
            {
                "parameter": "min_quantity/max_quantity",
                "rules": ["Filter per-sale quantities; minimum must not exceed maximum."],
                "examples": ["min_quantity=3, max_quantity=8"],
            },
            {
                "parameter": "limit/cursor",
                "rules": [
                    "Page size is 1–50; only continue with the returned cursor for the same "
                    "filters and limit."
                ],
                "examples": ["limit=20"],
            },
        ],
        "terms": {
            "sale record": "One fixture event with a sale ID, book ID, sale date, and quantity.",
            "week_start": "Monday of the ISO-style calendar week containing sold_date.",
            "month": "Calendar month in YYYY-MM form.",
        },
        "rules": [
            "Each row is one sale record, not an aggregate bucket.",
            "Rows add title, author, genre, weekday, week_start, and month from local book/date "
            "data.",
            "Total units cover all rows matching filters, not only the returned page.",
        ],
        "example": (
            "For an individual ledger use get_sales; for a monthly series use get_sales_trends."
        ),
        "format": "table",
        "formats": [
            "Present a concise table with date, sale ID, book, and quantity; avoid dumping every "
            "field unless asked.",
            "State total matching records/units and whether more pages exist.",
        ],
        "facts": [
            "Inclusive/exclusive date window",
            "Matched total versus page rows",
            "Fixture source and limitations",
        ],
    },
    "get_sales_trends": {
        "keywords": [
            "sales",
            "sale",
            "sold",
            "trends",
            "trend",
            "monthly",
            "weekly",
            "daily",
            "chart",
            "time",
            "series",
        ],
        "queries": ["Monthly science book sales", "Chart weekly sold units"],
        "use": "Read sold units grouped by sale date and calendar interval.",
        "avoid": (
            "Do not infer sales from imports; revenue, profit, forecast, "
            "and vendor-attributed sales are unsupported."
        ),
        "parameters": [
            {
                "parameter": "interval",
                "rules": ["day, week, month only; weeks start Monday; edge buckets are clipped."],
                "examples": ["month"],
            },
            {
                "parameter": "sold_from/sold_before",
                "rules": ["These are SALE date bounds, both provided or neither."],
                "examples": ["2026-08-01 to 2026-09-01"],
            },
        ],
        "terms": {
            "sold units": "Integer quantity actually sold in the fixture.",
            "zero bucket": "An interval with no recorded sales, still returned.",
        },
        "rules": [
            "Sales are attributed to books, not supplying vendors.",
            "No currency or revenue in this experiment.",
        ],
        "example": "April has zero sales, so its zero bucket remains visible in a monthly series.",
        "format": "chart",
        "formats": [
            "series and chart-capable host: date/unit chart",
            "chart-incapable host: chronological table",
            "one point: single labeled value",
        ],
        "facts": ["Axes with date and sold-unit labels", "Period", "Source", "Zero buckets"],
    },
    "compare_vendors": {
        "keywords": [
            "compare",
            "comparison",
            "versus",
            "vs",
            "vendors",
            "suppliers",
            "ranking",
            "side",
            "by",
            "difference",
        ],
        "queries": ["Compare vendor A and vendor C", "Suppliers side by side by delivered volume"],
        "use": "Compare two to four vendors' supply volume for the SAME date window.",
        "avoid": (
            "For one vendor use get_vendor_summary. "
            "Do not claim volume proves best quality or reliability."
        ),
        "parameters": [
            {
                "parameter": "vendor_ids",
                "rules": ["2–4 distinct canonical IDs, including zero-supply vendors."],
                "examples": ['["VENDOR-A","VENDOR-C"]'],
            }
        ],
        "terms": {
            "comparison period": "A single common receipt window for all selected vendors.",
            "overlap": "The same catalog book may appear under several vendors.",
        },
        "rules": [
            "Do not sum vendor unique-book counts into a combined unique count.",
            "Supply volume alone does not establish quality.",
        ],
        "example": (
            "If A and B each supplied B001, their individual unique counts add to two "
            "but there is only one combined book."
        ),
        "format": "table",
        "formats": [
            "multiple vendors: side-by-side metrics table",
            "one chosen metric and capable host: optional bar chart",
        ],
        "facts": ["Common period", "Consistent units", "Zero rows", "Evidence-limited conclusions"],
    },
}


def write_context(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "tools": {}}
    for name, c in CONTEXT.items():
        entry = {
            "retrieval": {
                "summary": CONTRACTS[name].description,
                "keywords": c["keywords"],
                "example_queries": c["queries"],
            }
        }
        bodies = {
            "execution": {
                "purpose": c["use"],
                "when_to_use": [c["use"]],
                "when_not_to_use": [c["avoid"]],
                "parameter_rules": c["parameters"],
                "preconditions": [
                    "Read bookstore://reference for vendor IDs and fixed clock.",
                    "Use ISO paired dates, known IDs, and no unsupported parameters.",
                ],
            },
            "domain": {
                "terms": c["terms"],
                "business_rules": c["rules"],
                "examples": [c["example"]],
                "limitations": [
                    "Local dummy fixture, 2026-03-01 through 2026-09-26, Asia/Kolkata."
                ],
            },
            "presentation": {
                "default_format": c["format"],
                "format_rules": c["formats"],
                "required_facts": c["facts"],
                "tone": "Concise, factual, and evidence-limited.",
                "citation_rules": [
                    "Use returned source_uri; hyperlink only if host supports it.",
                    "Otherwise use a labeled plain reference. Never invent HTTP URLs.",
                ],
                "fallback_format": "text",
                "user_format_precedence": True,
            },
        }
        for category, body in bodies.items():
            folder = root / name
            folder.mkdir(exist_ok=True)
            document = {"schema_version": 1, "tool_name": name, "category": category, "body": body}
            (folder / f"{category}.json").write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
            key = {
                "execution": "execution_instructions",
                "domain": "domain_knowledge",
                "presentation": "presentation_policy",
            }[category]
            entry[key] = {"file": f"{name}/{category}.json"}
        manifest["tools"][name] = entry
    (root / "tool_contexts.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    write_context(Path(__file__).resolve().parents[1] / "src/modern_mcp/context")
