# LangGraph + Gemini + A2A example

An agent example using the MCP server's existing environment. No separate project,
server imports, shared fixture files, preconfigured tool names, or telemetry backend.

The agent learns tools and context through MCP HTTP discovery. It understands the
public v1 tool-context contract (retrieval plus execution/domain/presentation
resource references), not the server implementation. It detects the metadata
namespace from those fields; no bookstore namespace or URI scheme is hardcoded.
The MCP server remains a separate process. A2A is the agent's outward task interface.

## Run through A2A

From the repository root, with `GOOGLE_API_KEY` in your environment or `.env`:

```powershell
uv sync --frozen --extra agent
uv run --frozen modern-mcp
```

Start the agent in another terminal:

```powershell
uv run --frozen --extra agent python -m examples.agent --serve --mcp-url http://127.0.0.1:8000/mcp --port 9999
```

Send a request from a third terminal:

```powershell
uv run --frozen --extra agent python -m examples.agent.client "Show books imported last month from vendor A" --url http://127.0.0.1:9999
```

Agent card: `http://127.0.0.1:9999/.well-known/agent-card.json`.
A2A 1.0 JSON-RPC endpoint: `http://127.0.0.1:9999/`.
The official SDK streams task status updates containing Markdown context snapshots,
then produces `answer` and `context_trace` artifacts and completes the task.
Failures mark the task failed; cancellation stops its graph/model work through
the SDK's cancellation lifecycle.

Direct execution uses the same graph and logging, without an A2A caller:

```powershell
uv run --frozen --extra agent python -m examples.agent --query "Show books imported last month from vendor A"
```

`--model` or `GEMINI_MODEL` selects Gemini (default `gemini-3.1-flash-lite`).
`-k` sets retrieval breadth. `--mode select_then_hydrate` chooses names before
loading execution/domain instructions; `hydrate_candidates` loads instructions
for all top-K candidates before argument generation. `--log-dir` defaults to
`artifacts/agent`. Use `--public-url` when the advertised A2A URL differs from the
listening address. No deployment configuration is included.

## Context and observability

Every task creates a private registry during initialization and a separate UUID
trace, keeping concurrent tasks' contexts separate. Events have a sequence number,
UTC timestamp, elapsed milliseconds, and one of these visibility labels:

- `host_only`: discovery metadata, resource catalog, reference documents, retrieval
  rankings, loaded context, validated invocations, results, completion/failure.
- `graph_state`: a full graph-state snapshot and loaded document cache after each
  node. Dependencies and credentials live outside graph state.
- `model_request`: the exact application messages and bound function schemas sent
  to the Gemini integration. Its SDK handles final provider wire conversion.
- `model_response`: returned content, function calls, usage metadata and duration.

The lifecycle is initialization → registry creation → retrieval → name selection
→ execution/domain hydration → argument generation → validated tool calls
→ tool results → presentation policy hydration → synthesis → completion.
Each graph-node completion adds a state snapshot; each model call logs its request
before invocation, so a failed call still leaves the context that caused it.

Model requests are fresh stage projections. Retrieval metadata/scores stay private;
selection gets candidate names/descriptions; argument generation gets schemas,
execution/domain context and discovered reference resources; synthesis gets result
data and policies for tools actually used. Private registry state is not forwarded
just because it appears in a diagnostic log. Tool result strings are untrusted data.

`<run-id>.md` contains readable Markdown sections with formatted JSON context;
`<run-id>.jsonl` contains the same immutable event snapshots for scripts. Both flush
after every event. The A2A client prints streamed Markdown; the service keeps the
full local logs. No observability plugin, exporter, or hosted tracing integration
is configured. Traces contain user queries/results, not Google credentials or
private model reasoning. Exception class names are logged instead of potentially
sensitive provider exception bodies.

## Deliberate limits

The graph makes one batch of distinct tool calls per task, with at most one call
per tool; it does not automatically page or replan. No cross-task chat memory is
sent to Gemini. A2A task records are in memory and do not survive a restart.
The registry uses a small lexical BM25 scan, validates arguments/output schemas,
and verifies context resource hashes and document identity. Hashes establish
consistency, not server trust. Public static JSON reference resources are discovered
and read during initialization; each context/reference resource is capped at 32 KiB.
Servers without the advertised v1 context contract are rejected.

## Verify

```powershell
uv run --frozen --extra agent python -m pytest tests/test_example_agent.py -q
```

The tests use a real separate HTTP MCP process, real A2A SDK streaming, and a local
model double for repeatability. A live Gemini run additionally exercises the provider.
Protocol setup follows the official
[A2A Python SDK v1 migration guide](https://github.com/a2aproject/a2a-python/blob/main/docs/migrations/v1_0/README.md).
