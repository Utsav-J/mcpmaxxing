# Specify the bookstore MCP tool context experiment

Label: wayfinder:map
Status: resolved

## Destination

An implementation-ready specification for a modern official Python MCP server that serves dummy bookstore data and publishes structured per-tool context for dynamic client consumption. The specification includes a small Python registry/retrieval reference and illustrative LangGraph integration; this effort stops before implementation.

## Notes

- The user subsequently authorized building the actual application without further clarification. That explicit instruction supersedes the earlier spec-only review gate and ends this planning effort. Adopted defaults, application commands, and evidence are in README; the remaining tickets now point to their implementations.

- User-confirmed scope, 2026-09-26: server first; client is a reference, not a production agent. No hosted model or embedding API is required.
- Use the latest stable official `mcp` SDK and supported current protocol, accepting the SDK's `MCPServer` replacement for official `FastMCP`. Pin the chosen release when implementing; never substitute the independent `fastmcp` package.
- Dummy catalog: 100 books. Imports mean stock receipts from vendors, with dates and quantities.
- Every business tool is read-only and has distinct retrieval metadata, execution instructions, domain knowledge, and presentation policy.
- Retrieval metadata never enters any model request. A deterministic client gate selects top-K tools. Execution instructions and domain knowledge must be loaded before tool invocation, early enough to inform argument generation.
- The review-ready draft is [Bookstore MCP tool context registry experiment](spec.md). It assembles confirmed choices and explicit technical defaults; remaining child tickets review the proposal before final approval.
- Sample LangGraph code illustrates integration; no actual model-backed agent or hosted service is a deliverable.
- Consult `wayfinder`, `grilling`, and `domain-modeling`; use `research` for factual investigations. Canonical terms: [Tool Context Registry](../../CONTEXT.md).
- Tracker: local Markdown fallback because no repository tracker was configured. If the user later wants tracker setup, `/setup-matt-pocock-skills` can configure it; this effort does not depend on that setup.
- Each child records its identity, parent, label, type, status, assignee, and blockers. Open, unassigned, unblocked children are the frontier; scan by filename order. Answers belong in child tickets, not this map. Research agents may resolve research tickets; charting does not resolve human decision tickets.
- Source research: [Official MCP capabilities](../../docs/research/mcp-capabilities.md), supplemented by [Verified v2 registry and LangGraph APIs](../../docs/research/mcp-v2-registry-langgraph.md). Use the v2 supplement for current registration/client signatures.
- Research assets stay in this working tree: there is no initial Git commit, so a throwaway research branch cannot yet be created without an unrelated repository initialization change.

## Decisions so far

<!-- Append a named link and one-line gist only when a child ticket is resolved. Confirmed scope is in Notes; unresolved decisions remain in their child tickets. -->

- [Verify current MCP metadata APIs and LangGraph context ordering](issues/01-verify-current-sdk-and-langgraph.md): official mcp 2.2.0 metadata/resource APIs and explicit graph ordering are available; Skills SDK support remains optional work, and offline request inspection does not establish model quality.
- [Choose the per-tool context publication contract](issues/02-context-publication-contract.md): inline retrieval plus local JSON instruction documents accessed through versioned MCP resource references.
- [Define bookstore tool boundaries and fixture semantics](issues/03-bookstore-tool-and-data-contract.md): seven typed read-only tool contracts, fixed calendar windows, and received-minus-sold inventory.
- [Choose a reproducible local tool-retrieval baseline](issues/04-local-retrieval-baseline.md): deterministic BM25 implemented, with no dense/model dependency.
- [Specify context loading and the illustrative LangGraph flow](issues/05-context-loading-and-langgraph-sample.md): both offline graphs run through real MCP calls and explicit projection boundaries.
- [Assign roles to descriptions, schemas, resources, prompts, skills, and transports](issues/06-protocol-features-and-transport.md): typed tools/resources/prompts and both transports implemented; skills extension deferred.
- [Define acceptance evidence and the implementation handoff](issues/07-experiment-evidence-and-handoff.md): contract suite, packaged assets, and the offline authored-corpus report verify the adopted baseline.

## Not yet specified

No uncharted scope remains for the implemented baseline. User authorization to build superseded the remaining formal planning gate.

## Out of scope

- Implementing the server, registry, fixtures, or runnable agent during this planning effort.
- Write tools, even simulated mutations.
- Hosted LLM or embedding API requirements.
- Dense/hybrid retrieval and embedding-model downloads in the first experiment; the user selected BM25 only.
- Additional context categories or subdocument retrieval in the first experiment; use one execution, one domain, and one presentation document per tool.
- A production LangGraph agent, production authentication/deployment, or a client framework spanning arbitrary MCP hosts.
- Claiming real-world performance or LLM-quality improvements from a 100-book dummy fixture or offline deterministic checks.
