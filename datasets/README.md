# Tool-gating evaluation dataset

One-turn, independent-prompt examples for evaluating agent tool selection and argument construction against this repository's bookstore MCP fixture. There are 10 queries in each tier: `easy`, `medium`, `hard`, and `very_complex` (40 queries total). Harder prompts combine independent asks in one user message; there are no multi-turn or memory-dependent cases yet.

## Files

- `query_to_answer.csv`: one row per query with a concise fixture-grounded high-level answer. Join to the tool mapping by `query_id`.
- `query_to_tool.csv`: one row per expected tool intent, with `intent_index`, expected arguments as JSON, and a selection rationale. A query with multiple independent asks has multiple rows, not an implied dependent call chain.

`get_sales` means individual event-level sale records. `get_sales_trends` means grouped date buckets and aggregate sold-unit totals. Their distinction is deliberately tested in several prompts.

Detailed `get_sales` output has 10 fields per sale row: `sale_id`, `book_id`, `title`, `author`, `genre`, `sold_date`, `quantity`, `weekday`, `week_start`, and `month`. This fixture contains no sale price or sales-vendor attribution.

Regenerate answer values from the current fixture and public contracts with:

```bash
uv run --frozen python scripts/generate_tool_gating_dataset.py
```
