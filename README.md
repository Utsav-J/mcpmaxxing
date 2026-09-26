# modern-mcp

Standalone read-only bookstore MCP server, served **only over Streamable HTTP** using
`mcp==2.2.0`. A separate host discovers its seven tools, constructs a private tool
context registry, and uses LangGraph + Gemini to load context in stages. The server
needs no model API key, agent process, or other MCP server.

## Run the server

Requires Python 3.14 and uv:

```powershell
uv sync --frozen --no-dev
uv run --frozen modern-mcp --port 8000
```

Endpoint: `http://127.0.0.1:8000/mcp`. The CLI has no stdio or SSE option.
Use `--host 0.0.0.0` or `MCP_HOST=0.0.0.0` for container networking. HTTP is
stateless, so requests do not depend on an in-memory session or sticky pod routing.
Packaged fixture/context files are resolved on the server, independently of its
working directory. Clients retrieve documents through MCP, without shared files.

The server's base dependencies exclude LangGraph/Gemini. Run the host as a separate
process with only the remote endpoint configured; no Google secret is needed on
the MCP server. Deployment configuration is deliberately deferred.

Host/Origin validation remains enabled. Set `MCP_ALLOWED_HOSTS` (comma-separated
host values, with `:*` for any port) for the eventual Service/ingress hostname;
set `MCP_ALLOWED_ORIGINS` for permitted browser origins.

## Run the agent example

The independent client lives in [examples/agent](examples/agent/README.md) and uses
this repository's environment. It imports no server code, constructs its own
registry using HTTP discovery, and runs LangGraph + Gemini with local Markdown
and JSONL traces. The same agent is exposed through the official A2A SDK.

```powershell
uv sync --frozen --extra agent
uv run --frozen --extra agent python -m examples.agent --serve --mcp-url http://127.0.0.1:8000/mcp
# In another terminal:
uv run --frozen --extra agent python -m examples.agent.client "Show books imported last month from vendor A"
```

Set `GOOGLE_API_KEY` in the environment or `.env`. Each task logs registry creation,
top-K retrieval, graph state after every node, exact model requests/responses,
tool invocations/results, and presentation policy loading. A2A streams Markdown
updates and returns the answer plus a context-trace artifact. See the example's
README for direct execution, stage boundaries, and limitations.

## Does the LLM automatically read tool `_meta`?

No. `tools/list` delivers tool definitions and `_meta` to the **host**. MCP does not
require a host to put arbitrary metadata into the model request. Tool selection
also does not automatically read resources or inject execution/presentation rules.
A host decides which definitions, messages, resources, and results reach its model.
See the [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
and [Gemini integration documentation](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).

Every tool advertises `_meta["modern_mcp/tool_context"]` with four categories:

- Retrieval: inline summaries, keywords, and example queries for private BM25.
- Execution instructions: immutable resource reference with URI, SHA-256, media type.
- Domain knowledge: the same resource reference contract.
- Presentation policy: the same resource reference contract.

The last three contain **references**, not full document bodies. A host could put
all bodies inline, but that still would not guarantee any particular model sees
or follows them. The reference host explicitly excludes retrieval metadata/scores,
loads execution/domain context before argument generation, then loads presentation
policies after results. It projects only names, descriptions, and input schemas
into provider business-tool definitions. Other hosts must implement the policy;
the server cannot enforce what an arbitrary host sends to its own LLM.

## Build a registry from another host

```python
from mcp import Client
from modern_mcp.registry import ToolContextRegistry

async def initialize(url):
    async with Client(url) as client:
        registry = ToolContextRegistry(client, url)
        await registry.refresh()  # tools/list + bookstore://reference, over HTTP
        names = [name for name, _ in registry.retrieve("Catalog books", k=3)]
        prepared = await registry.hydrate(names)  # resources/read, over HTTP
        request = registry.argument_request("Catalog books", prepared)
        # Send request to your model adapter; invoke while the client is connected.
        return request
```

`registry.py` implements discovery pagination, private BM25, schema validation,
context hash/identity checks, verified caching, and explicit model projections.
`refresh()` atomically rebuilds discovery/index/revision/cache. Restart the server
and refresh clients after authoring changes; automatic subscriptions are not added.
Prepared context/results from an older revision are rejected. Hashes detect
inconsistency, not the trustworthiness of an unknown server. Tool result strings
are supplied as untrusted data rather than policy instructions.

## Bookstore contract

Tools: `get_books`, `get_book_details`, `list_stock_receipts`,
`get_stock_availability`, `get_vendor_summary`, `get_sales_trends`, `compare_vendors`.
They enforce flat input schemas and typed structured output, read-only annotations,
stable error codes, default pages of 20 rows (maximum 50), and query/dataset-bound
cursors. Totals cover the entire matched set. Empty results succeed.

The fixture contains 100 books, 300 receipts, 200 sales, and four vendors. Its clock
is **2026-09-26**, Asia/Kolkata, with coverage `[2026-03-01, 2026-09-27)`.
Imports mean stock receipts; date/vendor filters must match the same receipt.
Stock means received minus sold units. Date bounds include the start and exclude
the end; last month is `[2026-08-01, 2026-09-01)`.

Public resources: `bookstore://reference`, `bookstore://fixtures/bookstore-demo-v1`,
`bookstore://books/{book_id}`, and 21 immutable execution/domain/presentation JSON
resources. Optional prompts: `review_imports`, `compare_vendor_supply`.
Authoring files live in `src/modern_mcp/context/`; startup rejects invalid context.

## Verify

```powershell
uv sync --frozen --extra agent --extra examples
uv run --frozen --extra agent python -m pytest -q
uv run --frozen --extra agent ruff check src examples scripts tests
uv run --frozen --extra agent ruff format --check src examples scripts tests
```

The A2A runner is `examples.agent`; `examples.langgraph_context_flows` is the older
reference experiment. Deterministic adapters
in `examples.offline_adapter` exist solely for tests and reproducible byte/recall
measurements (`python -m examples.offline_experiment`, `--extra examples`). These
measurements are not model-quality evaluations or token/cost estimates. Unit tests
require no Google key; a live end-to-end run requires a key and the running HTTP server.
