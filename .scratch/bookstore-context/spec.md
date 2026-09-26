# Bookstore MCP tool context registry experiment

Status: implementation baseline. The user authorized building the application without further clarification, superseding the remaining formal planning review gate.
Specification date: 2026-09-26.
Planning map: [Specify the bookstore MCP tool context experiment](map.md).

## 1. Outcome and scope

Implement a modern read-only Python MCP server serving dummy bookstore data. Every tool advertises inline retrieval metadata and resource references for execution instructions, domain knowledge, and presentation policy. A small Python reference client demonstrates discovery, a structured tool context registry, deterministic BM25 selection, and dynamic instruction loading. Illustrative LangGraph code shows two context-loading strategies without requiring a model provider or constructing a production agent.

The main deliverable is the MCP server and its context contract. This planning effort produces this specification and supporting documents; implementation is a later effort.

Confirmed choices:

- Latest stable official `mcp` SDK, accepting `MCPServer` as the successor to official FastMCP.
- Exactly 100 catalog books; imports are vendor stock receipts with dates and quantities.
- Seven read-only business tools.
- Retrieval metadata inline; the other three categories reference local JSON documents exposed through MCP resources.
- BM25 only; no dense/hybrid retrieval, embedding download, or hosted API requirement.
- Both candidate-first hydration and selection-before-hydration flows.
- Execution/domain context loaded before generating tool-call arguments.
- Fixed reference date 2026-09-26, calendar-month interpretation, inclusive-start/exclusive-end windows.
- Simple stock accounting: received units minus sold units; no reservations, returns, or backorders.
- Presentation supports single values/short text, tables, genuine reference hyperlinks, and charts with a text fallback.

Implementation defaults chosen to make the draft concrete are explicitly specified below: IDs/genres, fixture row counts, limits, K, BM25 formula, transports, units-only sales, and presentation precedence. They are design recommendations, not additional facts attributed to the user.

## 2. SDK, dependencies, and transports

The research baseline is official `mcp==2.2.0`, with `from mcp.server import MCPServer`, and current protocol revision 2026-07-28. Use the SDK's version negotiation rather than hand-rolling JSON-RPC or assuming every client uses the newest revision. A newer release may be selected at implementation time only after checking its API compatibility and updating the lockfile and documented version. [Verified public SDK APIs](../../docs/research/mcp-v2-registry-langgraph.md).

Keep the repository's Python 3.14 baseline unless dependency installation reveals a concrete incompatibility. Use typed Pydantic models for registration, metadata validation, category documents, and results. Declare directly imported dependencies directly. Lock runtime/development versions with the existing uv-based project workflow.

Provide stdio as the primary local reference transport and Streamable HTTP on loopback as a smoke-tested alternative. Log to stderr; no diagnostic output on the stdio protocol stream. No legacy SSE demonstration, production hosting, or authentication setup is required for this dummy local experiment.

The LangGraph example is an optional example dependency, not a required dependency to start the server. Use the verified `StateGraph` API; pin and document the selected LangGraph version during implementation.

## 3. Fixtures and domain invariants

Use packaged UTF-8 JSON fixtures or a deterministic generator whose output is committed as fixtures. No network source or mutable database is required. Load and validate the fixture once at startup and construct in-memory lookup indexes.

Default fixture design:

- `B001` through `B100`: exactly 100 books, with unique IDs, titles, authors, and one genre each. No ISBN is required; do not invent ISBNs or imply the ID is an ISBN.
- Four vendors: `VENDOR-A` through `VENDOR-D`, displayed as Vendor A through Vendor D.
- Genres: `fiction`, `science-fiction`, `fantasy`, `history`, `science`, `business`.
- 300 stock-receipt rows and 200 sale rows spanning 2026-03-01 through 2026-09-26 inclusive. Each receipt row describes one book received from one vendor, with a unique receipt ID, receipt date, and positive integer quantity. Receipt-row count is not a count of multi-line shipment invoices.
- Each sale row describes one book, sale date, unique sale ID, and positive integer quantity. Use units-only sales; revenue/currency rules are deferred.
- Fixture manifest includes dataset ID `bookstore-demo-v1`, revision, canonical content digest, `coverage_start=2026-03-01`, `as_of_date=2026-09-26`, and `timezone=Asia/Kolkata`.

Stock is received units minus sold units. Available units equal on-hand units. For every book and each event date, cumulative sales cannot exceed cumulative receipts; same-day receipts are available before same-day sales. The fixture starts with zero stock. All IDs referenced by rows exist. No future-dated rows are present.

Include deliberate edge cases: one unsupplied catalog book, one out-of-stock book, one low-stock book, multiple receipts for the same book, multiple vendors supplying the same book, receipts on both date-window boundaries, no-sale intervals, and one genre/vendor/window combination with no matches.

Do not rely on a random seed alone for golden tests; designate fixed edge-case records and expected outputs, and generate remaining rows without changing those expectations.

## 4. Common input, date, and pagination rules

Business-tool inputs use JSON Schema with `additionalProperties=false`, explicit field descriptions, typed enums/IDs, and bounded list sizes. Unknown parameters, invalid IDs, invalid enums, duplicate IDs, empty explicit filter lists, and malformed dates are errors. `null`/omitted optional filters mean no restriction, not an empty selection.

Vendor filters accept IDs, not free-text vendor names. The client gets the tiny vendor/genre directory from a public resource when needed; a user saying "Vendor A" maps to `VENDOR-A` through that directory. Never guess a book ID from a title; obtain it from a catalog result or ask for clarification in a future model adapter.

Date inputs are ISO `YYYY-MM-DD` dates with start included and end excluded. Both bounds must be supplied together or both omitted; start must precede end. Missing bounds mean the entire fixture coverage, not a hidden "recent" default. Explicit windows must lie inside `[2026-03-01, 2026-09-27)`; reject unsupported windows instead of reporting partial coverage as complete.

The small reference date resolver uses the manifest's fixed reference date. "Last month" resolves to `[2026-08-01, 2026-09-01)`. "Last 30 days" is a different explicitly described interval, `[2026-08-28, 2026-09-27)`, including the reference date. The tools themselves require dates, not relative strings. Return the applied bounds with results.

List inputs use `limit=20`, range 1–50, and an optional opaque `cursor`. Cursors bind the dataset digest, tool name, canonical filter values, ordering, page size, and offset. Stable order is defined per tool. Reject malformed cursors, mismatched filters/page sizes, and old dataset cursors. A cursor is not an authorization token and needs no secret-based security claim in this read-only fixture.

All paginated results return `items`, `total_count`, `next_cursor`, and `applied_filters`. `total_count` covers the entire matched result, not just the current page. Include source scope so presentation cannot describe a page as the full set. Summary tools aggregate over all matching fixture rows, never over an accidental first page.

## 5. Typed outputs, provenance, and errors

All successful results are typed object envelopes with `data` and `provenance`. Define a distinct output model for each tool; do not return arbitrary dictionaries or one untyped universal payload.

Provenance contains dataset ID/revision, content SHA-256, as-of date, timezone, a source resource URI, and effective coverage. The result data contains applied filters and an empty-or-populated `warnings` list; pagination fields belong to list payloads. Warnings communicate actual limitations, not boilerplate disclaimers.

Sources are local MCP resources such as `bookstore://fixtures/bookstore-demo-v1` or `bookstore://books/B001`. No fixture value supplies arbitrary HTML, executable chart code, or fabricated external URLs. The resources themselves are readable and give the corresponding bounded fixture description or book detail.

Use generated output schemas and SDK structured results. Validate results at both the server's typed return boundary and the reference client's output-schema boundary. If the SDK also returns text alongside structured data, the model projection consumes one canonical structured view rather than duplicating both forms. [Structured result behavior](../../docs/research/mcp-v2-registry-langgraph.md).

Normal empty sets are successful results. An unknown validly formatted entity ID is a tool error, not a zero-value success. Invalid arguments produce a tool-level error with `isError=true` and a stable code such as `INVALID_ARGUMENT`, `UNKNOWN_ID`, `INVALID_CURSOR`, or `UNSUPPORTED_WINDOW`; malformed protocol requests use the SDK's protocol errors. Error content is bounded and contains neither traceback nor internal file paths. Do not pretend an error payload conforms to a success output schema.

## 6. Seven tool contracts

Each tool has a concise visible description, its typed input/output schemas, read-only annotations, inline retrieval material, and distinct execution/domain/presentation documents. Annotations are descriptive hints; actual read-only behavior follows from the implementation containing no mutation operations.

### get_books

Description: "List catalog books, optionally filtered by genre and stock receipts from vendors during a date window."

Inputs: `genre: Genre | null`, `vendor_ids: list[VendorId] | null` (1–4), `received_from: date | null`, `received_before: date | null`, `limit`, `cursor`.

Return distinct catalog rows ordered by `book_id`. With no receipt filters, include all catalog books matching genre, including unsupplied books. With a vendor or date filter, include a book only if the SAME receipt row satisfies all supplied receipt conditions. Vendor lists use OR within the list; genre and receipt conditions combine with AND. Do not join a July delivery from Vendor A to an August delivery from Vendor B to claim an August Vendor A import.

Items contain `book_id`, `title`, `author`, `genre`, and `matched_received_units` (integer when receipt filters apply, otherwise null). The units are summed only from matching receipt rows. This is a catalog list, not a receipt ledger or current stock response.

Execution distinction: translate relative periods before calling; use this for catalog identities, and `list_stock_receipts` for delivery rows/quantities.
Domain distinction: one book can have many receipts; unique books and received units are different measures.
Presentation distinction: compact table for several books; a short labeled entry for one book; show applied filters and pagination status. Never call matched received units "remaining stock".

### get_book_details

Description: "Get catalog facts and lifetime fixture stock totals for one exact book ID."

Input: `book_id: BookId`, required.

Return `book_id`, `title`, `author`, `genre`, `vendor_ids`, `total_received_units`, `total_sold_units`, and `stock_units`. Vendor IDs are the distinct supplying vendors in the fixture. No unbounded embedded receipt/sale history.

Execution distinction: use a known ID; use catalog listing to resolve titles. A missing entity is an error.
Domain distinction: book IDs identify this local catalog and are not ISBNs; detail totals are over the fixture's lifetime.
Presentation distinction: a short titled detail view. Link the book resource only if the host can open its URI; otherwise show a labeled source reference. Multiple scalar facts can be a compact key/value list.

### list_stock_receipts

Description: "List dated vendor stock-receipt rows and received quantities, optionally filtered by books or genre."

Inputs: `received_from`, `received_before`, `vendor_ids: list[VendorId] | null` (1–4), `book_ids: list[BookId] | null` (1–100), `genre: Genre | null`, `limit`, `cursor`.

Return receipt rows ordered by `(received_date, receipt_id)`, with `receipt_id`, `received_date`, `vendor_id`, `book_id`, `title`, and `quantity`. Filters combine with AND across categories and OR within ID lists. List payload additionally includes matched `receipt_count`, `received_units`, and `unique_book_count` calculated across the entire matched set.

Execution distinction: use when the question asks what arrived and when, or asks for receipt-level quantities. Do not use for remaining inventory.
Domain distinction: repeated receipt rows represent repeated stock arrivals; receipt count, book count, and units are not interchangeable.
Presentation distinction: chronological table, with separately labeled full-match totals and page completeness. Show the source resource as a real supported link or plain reference.

### get_stock_availability

Description: "Show available stock units at the fixture's current snapshot, optionally restricted to books, genre, or stock status."

Inputs: `book_ids: list[BookId] | null` (1–100), `genre: Genre | null`, `stock_status: Literal['all','out_of_stock','low_stock','in_stock']='all'`, `limit`, `cursor`.

Return rows ordered by `book_id`, each with ID, title, genre, `stock_units`, and computed `stock_status`. Statuses are mutually exclusive: out-of-stock is 0, low-stock is 1–5, in-stock is greater than 5. There is no historical `as_of` parameter; every result labels 2026-09-26 as the snapshot.

Execution distinction: use for current stock only; reject unsupported historical claims rather than substitute current values.
Domain distinction: available equals on-hand in this fixture because reservations/backorders are absent.
Presentation distinction: one requested book can be a single labeled value, e.g. "B001: 4 units available as of 2026-09-26." Several books use a stock table; low/out-of-stock states are explicit labels, not color-only indicators.

### get_vendor_summary

Description: "Summarize receipt rows, unique books, and units supplied by one vendor during a receipt-date window."

Inputs: `vendor_id: VendorId`, required; `received_from`, `received_before`.

Return vendor ID/name, applied receipt window, `receipt_count`, `unique_book_count`, `received_units`, and `genre_breakdown` (six genre entries with counts/units, including zeros). No full book list.

Execution distinction: use for one vendor's totals; use `compare_vendors` for a comparison across vendors.
Domain distinction: summary measures supply volume only; it contains no delivery-time, pricing, quality, or reliability evidence.
Presentation distinction: a short vendor summary with labeled totals; use a small genre table only when it helps the question. A request for one metric can return a single value with period and provenance.

### get_sales_trends

Description: "Summarize sold book units by calendar interval over a sale-date window, optionally filtered by genre."

Inputs: `sold_from: date | null`, `sold_before: date | null`, `interval: Literal['day','week','month']='month'`, `genre: Genre | null`.

Return chronological `points` containing `period_start`, `period_before`, and `sold_units`, plus `total_sold_units`, interval, applied filters, and units. Use Asia/Kolkata calendar dates; weeks start Monday and months start on the first. First/last buckets are clipped to the query window. Include zero-sale buckets. At most 210 points; fixture coverage ensures daily queries remain within this bound. No money, profit, forecast, or vendor attribution of sales.

Execution distinction: receipt dates are not sale dates; never infer sales from imports. Choose a supported interval and clarify unsupported revenue questions rather than fabricating revenue.
Domain distinction: a book supplied by several vendors does not tell us which vendor's units were sold; sales are by book only.
Presentation distinction: line/bar chart for several intervals if the host supports charts, with date and sold-unit labels. Otherwise use a chronological table or short trend summary. One point can be a single labeled value. Claims must reflect the actual sequence, including zeros.

### compare_vendors

Description: "Compare receipt volume for two to four vendors over the same receipt-date window."

Inputs: `vendor_ids: list[VendorId]`, required (2–4 distinct IDs); `received_from`, `received_before`.

Return one row per requested vendor in vendor-ID order, including zero-supply rows, with name, receipt count, unique book count, and received units. Include shared period and metric definitions. The combined unique-book count is not the sum of vendors' unique counts; do not publish a misleading combined count.

Execution distinction: compare a common period and the same metrics; for one vendor call `get_vendor_summary`.
Domain distinction: greater volume is not evidence of greater quality or reliability, and shared books overlap vendors.
Presentation distinction: side-by-side table by default; an optional bar chart for one selected metric with units. Label an observation such as "most units supplied" rather than "best vendor". Source references support the data, not invented external rankings.

## 7. Context publication and resource roles

The normative storage/projection details are in [Local tool context publication contract](../../docs/design/tool-context-contract.md). Package one execution, domain, and presentation JSON document per tool; every tool's documents contain the distinctions in section 6. Shared boilerplate must not replace tool-specific rules.

Advertise the complete authorized tool inventory through MCP discovery. Query-dependent top-K exposure happens in the client registry, not by mutating protocol discovery as a side effect of a search query. The standard tool description stays short and discriminative; schema field descriptions carry invariant parameter syntax; execution documents carry contextual selection/interpretation rules.

Provide these public non-retrieval resources:

- `bookstore://reference`: fixture clock/coverage, vendor directory, genre IDs, and core terminology.
- `bookstore://fixtures/bookstore-demo-v1`: bounded fixture provenance, semantics, counts, and revision; not the entire ledger.
- `bookstore://books/{book_id}`: a resource template returning the same bounded detail facts as `get_book_details`.
- Immutable per-tool category resource URIs from the manifest, with application/json bodies and hashes.

The reference resource may enter model context because it has execution/domain information and no retrieval corpus. Read it when names or relative dates require resolution; cache it by server/snapshot. Book resources and the fixture descriptor are genuine source references for returned data. MCP reads do not themselves insert resource content into a model request.

## 8. Prompts and skills

Provide two optional user-invoked MCP prompt templates: `review_imports(received_from, received_before, vendor_ids)` and `compare_vendor_supply(received_from, received_before, vendor_ids)`. Templates describe the task and reference appropriate tools/resources; they do not embed all tool instructions or the retrieval corpus, automatically execute tools, or bypass the context gate. Validate argument encodings; standard prompt arguments arrive as strings, so document canonical ISO dates and comma-separated vendor IDs for these templates. The ordinary tools still use typed JSON arguments.

A prompt result is a reusable workflow starting point, not a system-policy replacement. Test retrieving and rendering templates without a model.

Do not invent built-in `list_skills` APIs in this SDK baseline. The official skills protocol extension exists, but built-in Python SDK support was not verified in the selected release. Document a future skills packaging experiment for a multi-tool import review, with resource/prompt fallback and explicit host support. Implementing a custom skills extension is outside this first build. [SDK/extension support research](../../docs/research/mcp-v2-registry-langgraph.md).

## 9. Deterministic BM25 reference

The reference consumes the original standalone query string, not model-generated expansion. Follow-up contextual rewriting belongs to a later full agent. The client may supply an already standalone query explicitly.

Build one document per tool by concatenating its retrieval summary, keywords, and positive example queries in fixed field order. Do not index execution/domain/presentation text, negative examples, results, or user conversation history. Normalize query and corpus with Unicode case-folding and split into alphanumeric tokens; treat hyphens as separators, retain digits, and do not silently add stemming, stopword removal, or synonym APIs.

Use BM25 with `k1=1.5`, `b=0.75`, positive IDF `ln(1 + (N - df + 0.5)/(df + 0.5))`, and each distinct query token counted once. Standard length normalization uses the average document token count. Specify this formula rather than depend on a library's potentially different IDF convention. Empty queries/corpus documents are validation cases. Round only displayed scores; rank using full computed values, then lexicographic tool name to break exact ties.

Default `K=3`, configurable from 1–7. Return at most K positive-score tools; no positive score means no candidates and no dispatch, not arbitrary top-K tools with zero relevance. Retrieval scores/debug records remain client-only. This gate narrows model exposure and dispatch eligibility; it is not authorization or proof of intent. No automatic exposure of an unselected tool.

## 10. Two LangGraph example modes

The detailed code topology and boundaries are in [Two context-loading flows](../../docs/design/context-loading-flows.md).

Mode A loads execution/domain context for every top-K candidate, then constructs the argument-generating request with selected tool definitions. Mode B constructs a names/descriptions-only selection request, validates its provisional name subset, loads that subset's execution/domain context, then constructs the argument-generating request. Both allow declining a tool after reading its rules.

Before invocation, validate tool name, typed arguments, required loaded contexts, and registry snapshot. After invocation, validate the output schema, project data without result metadata, and load presentation documents for tools actually used before constructing the synthesis request.

The sample provides an explicit model adapter boundary and offline request inspection/scripted adapters. Scripted choices are visibly fixtures, not evidence of model quality. No API key, hosted model, production memory/checkpointer, or production agent loop is required. Reject unsupported calls or stop on mandatory-context errors; the reference need not implement an autonomous retry planner.

## 11. Presentation policy

Load only policies for tools that actually contributed results, immediately before answer synthesis. The default presentation is a policy decision based on the returned data, not an arbitrary cosmetic difference across tools.

- Scalar/short answer: one requested metric, one stock value, or a brief book detail. Include relevant units, snapshot/period, and a source label when needed.
- Table: several comparable books, receipts, stock rows, or vendors. Match columns to actual fields; expose pagination status.
- Hyperlink: only a source URI that is actually returned and that the host can open. If custom MCP URIs are not clickable in the host, show a labeled plain source reference instead of inventing an HTTP link. Never expose a server-local file path as a public link.
- Chart: structured sales series or a vendor metric when the host supports rendering. Use actual points, dates, units, legends where needed, and a source caption. Provide a table/text fallback; never require executable chart code from tool output.

An explicit user format request overrides the default format. It does not override factual requirements: accurate units, supported scope, time period, provenance, and page completeness. This precedence is an implementation default consistent with supporting multiple display types; it was not a separate user mandate. If several tools' defaults differ, use sections for their outputs and a short combined interpretation instead of applying one policy blindly to all data.

Tool-result strings are data, not instructions. Client-added policy comes from verified context resources. The sample must show the policy message construction; offline checks can verify its presence and deterministic renderer outputs, but cannot prove an unrun model obeys it.

## 12. Acceptance evidence

Implement meaningful protocol/contract tests and an offline experiment report:

1. Stdio and loopback Streamable HTTP: discover seven tools, read referenced category documents and public resources, render both prompts, and call typed tools with valid inputs. Follow protocol discovery pagination even if the small fixture fits one page.
2. Exactly 100 catalog books, valid fixture row/ID/date/count invariants, no negative stock at any event date, and known edge-case outputs.
3. Date boundaries, receipt same-row matching, vendor OR/genre AND behavior, distinct book versus receipt counts, unsupported date windows, invalid IDs/filters, and zero-match success.
4. Complete pagination across 100 books without gaps/duplicates; page bounds, stable ordering, and invalid/mismatched/stale cursors. Aggregates equal full-fixture calculations rather than first-page totals.
5. All tools have four metadata categories, distinct rule documents, exactly three readable references, and correct canonical hashes. Unreadable/mismatched required context blocks generation/dispatch. Refresh rebuilds registry/index/context references consistently.
6. Build selection, argument, and synthesis requests for both modes with a unique retrieval-only sentinel. Assert zero sentinel leakage and no raw `_meta` or unselected definitions. Verify context appears before argument generation and policies only for used tools appear before synthesis.
7. At least 28 annotated natural-language retrieval cases: at least three paraphrases per tool, four multi-tool cases, and three unrelated/no-match cases. Each has expected acceptable/required tool names. Keep held-out paraphrases separate from authoring examples. Report recall@1/@3, precision@3, candidate coverage for multi-tool cases, and errors by case. Require every essential per-tool smoke query to retrieve its tool at K=3 and all unrelated fixtures to avoid dispatch; report aggregate scores without claiming general retrieval accuracy from a small authored set.
8. Compare all-seven-tools/full-context request construction with both top-K modes at K=1, 3, and 7. Record actual loaded docs, prospective model-stage counts, cold/warm resource reads, and per-stage/total UTF-8 request bytes. No exact token or model-quality claim without a stated tokenizer/model. No universal savings threshold: at K=7 the context baseline may be similar and staged selection adds overhead.
9. Offline presentation cases cover scalar output, table pagination notice, real-link versus plain-reference fallback, chart-capable versus chart-incapable host, and multi-tool policy composition. Scripted renderers are test fixtures, not proof of LLM adherence.
10. Bounded output checks: list page limit 50, series limit 210, detail without embedded full ledgers, and context document limit 32 KiB canonical UTF-8 bytes per category. Record timings/environment when measuring; do not claim production scale from 100 books.

Suggested retrieval scenarios include "books imported last month from Vendor A", "what is B001", "when did B001 arrive", "how many copies are available", "Vendor B supply totals", "monthly science book sales", "compare Vendor A and Vendor C", and "list imported fantasy books and their current availability". Golden expected arguments/results must be written from the fixed fixture, not generated by the code under test.

## 13. Implementation handoff

Suggested structure:

```text
src/modern_mcp/
  server.py          # official SDK registration and transports
  models.py          # typed business/schema contracts
  bookstore.py       # pure fixture lookup/filter/aggregation logic
  fixtures/          # manifest and deterministic data
  context/           # manifest and per-tool category JSON
  context_loader.py  # validation, canonical bytes, hashes, resource map
examples/
  registry_reference.py
  langgraph_context_flows.py
tests/
  contract/
  bookstore/
  reference/
docs/
  design/
  research/
```

Implement in small verifiable stages: fixture/model/domain contracts; context registration/resources; seven typed tools; resource templates/prompts; transport checks; small registry/BM25 reference; illustrative graph modes and offline report. Keep business filtering separate from protocol registration, and context publication separate from model request construction.

Update README with pinned install/run commands, reference usage, fixture date semantics, and a diagram of the client boundary. The existing console entry point becomes the server launcher during implementation. This specification does not modify dependencies or start/build the application.

## 14. Review status

The user explicitly authorized implementation without further clarification after reviewing the planning rounds. Technical defaults above form the implemented baseline; the older formal-review gate is superseded. Runtime commands and measured checks are documented in README and the offline report. No hosted model, dense retrieval, production agent, or skills extension is claimed.
