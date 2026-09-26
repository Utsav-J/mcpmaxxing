# Official MCP capabilities for the bookstore experiment

Research date: 2026-09-26. Scope: official `mcp` Python SDK and primary MCP specifications. No packages were installed and no implementation was created. Recommendations below are project design choices, not protocol requirements.

## A consequential version decision

The current published stable package is **mcp 2.2.0**, uploaded September 7, 2026. The most recent v1 maintenance release is **1.30.0**. PyPI distinguishes these from the earlier v2 release candidates and betas. [Official PyPI package and release history](https://pypi.org/project/mcp/)

The tagged v2.0.0 release explicitly declares v2 stable, supports protocol **2026-07-28** plus earlier revisions, and renames the official high-level `FastMCP` server to `MCPServer`. This is not the independent `fastmcp` package. [Official stable release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0)

The old `mcp.server.fastmcp` implementation belongs to v1; v2 moves it to `mcp.server.mcpserver` and exposes `from mcp.server import MCPServer`. The migration guide documents the import change; v2.0.1 adds an explanatory warning for people trying the old import. [Migration guide](https://py.sdk.modelcontextprotocol.io/migration/#fastmcp-renamed-to-mcpserver), [v2.0.1 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.1)

Therefore the user's exact official `FastMCP` requirement requires a deliberate `mcp<2` pin, while a newest-stable implementation uses official `MCPServer`. Both can support the proposed custom metadata experiment; they differ in API and protocol era. The official v1 docs demonstrate the requested import and recommend the upper bound. [Official v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/)

## Metadata and the model boundary

The v1.30.0 official source verifies `@server.tool(meta=...)` and `add_tool(meta=...)`; `list_tools()` serializes that dictionary as tool `_meta`. It also publishes input/output schemas and tool annotations. This is a supported public registration argument, so no monkey patch is necessary. [Tagged FastMCP source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py)

MCP `_meta` is an extensibility field with reserved protocol namespaces. Custom metadata should use a vendor-owned prefix and a versioned internal schema; the proposed four categories are application-defined, not four built-in MCP fields. [Protocol metadata rules](https://modelcontextprotocol.io/specification/2026-07-28/basic#meta)

**Recommendation:** Treat retrieval-only as an explicit client data-flow rule. Receiving metadata through MCP does not prove that an arbitrary host will keep it out of its model requests. Build a model-facing projection that allowlists name, concise description, input schema, and selected instructions; never pass raw `Tool` objects or `_meta` dictionaries wholesale. Include a sentinel leakage test over every model request. This follows from MCP permitting metadata exchange while leaving the interaction model to implementations. [Tool interaction model](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#user-interaction-model)

Tool-result `_meta` is distinct from tool-definition `_meta`; returning instructions only after execution is too late for parameter construction. Resource links likewise identify content that the client may read; they do not themselves load the content into the model. [Tool result resource links](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#resource-links)

## Schemas and descriptions

Input schemas describe parameter types and constraints, with JSON Schema 2020-12 as the default dialect. Output schemas contract structured results: servers must conform, and clients should validate. Structured results are distinct from schema-constrained LLM generation. The 2026 revision permits any JSON value as structured content, while object result envelopes remain useful for legacy compatibility. [Tool schema and result specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

The official SDK generates schemas from parameter and return annotations and supports Pydantic models and field descriptions. Its structured-output documentation describes validation and how ordinary results populate both text content and structured data. Actual model exposure remains a host integration decision. [Official SDK tools](https://py.sdk.modelcontextprotocol.io/servers/tools/), [Official SDK structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)

**Recommendation:** Keep a short, discriminative description visible for selected tools. Put invariant parameter syntax in field descriptions and validation; put contextual rules in execution instructions. Use typed response envelopes carrying results, applied filters, pagination, fixture date/timezone, provenance, and warnings. Do not rely on instructional prose as enforcement of required constraints.

## Discovery versus selecting tools for a model

Current `tools/list` has pagination and cache hints. Its available set must not vary by connection or as a side effect of other requests; authorization may legitimately change availability. The standard list request does not contain a BM25/dense query or top-K selection parameter. [Current tools discovery rules](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#capabilities)

**Recommendation:** Discover the authorized inventory into a client registry, rank locally, then expose a top-K projection to the model. This preserves protocol discovery semantics. Tool ranking is neither authorization nor permission to call an otherwise unavailable tool. Make ranking reproducible by pinning corpus/embedding versions and score fusion, exact similarity search for this small corpus, and stable tie-breaking.

In the 2026 protocol, list results carry `ttlMs` and `cacheScope`, and clients opt into list-change events via `subscriptions/listen`. A registry should invalidate tool inventory, context cache, and retrieval index together when definitions change. Version/hash context payloads so instructions cannot silently drift apart from schemas. Legacy revisions use their earlier initialization/session/notification model. [2026 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)

## Prompts, resources, and skills

Resources provide addressable context and resource templates. They are suitable for shared glossary, per-tool execution/domain/presentation documents, and a versioned registry manifest. A custom URI scheme is acceptable. Reading and injecting the selected resource remains client logic. [Resource specification](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)

Prompts are reusable user-controlled templates. They fit optional workflows such as a bookstore import audit or vendor comparison; they are not a protocol hook that automatically runs before each tool call. [Official SDK prompts](https://py.sdk.modelcontextprotocol.io/servers/prompts/)

Skills are now an **official optional extension**, `io.modelcontextprotocol/skills`, not merely an informal resource convention and not a mandatory baseline primitive. Its accepted SEP reached Final on September 13, 2026, and the stable extension is written against protocol 2026-07-28. Verify target-client extension support rather than assuming every MCP host supports it. [Official skills extension repository](https://github.com/modelcontextprotocol/ext-skills/blob/main/README.md)

The skills extension adds discovery/loading operations and serves skill files through resources. It can package a multi-tool workflow while tool metadata continues to hold concise per-tool context references. The extension specifies how skills are advertised and retrieved; it does not replace the client registry or make a model obey instructions automatically. [Official stable skills extension](https://github.com/modelcontextprotocol/ext-skills/blob/main/specification/stable/skills.mdx), [Official skills overview](https://modelcontextprotocol.io/extensions/skills/overview)

## Transport and experiment design implications

Official v1 FastMCP supports stdio, legacy SSE, and Streamable HTTP. The current v2 release serves legacy and 2026 clients over stdio and Streamable HTTP. The 2026 protocol removes handshake/session state and uses per-request protocol metadata, discovery, and explicit subscriptions. [Tagged v1 transport source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py), [Official v2 stable release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0)

**Recommendation:** Start with stdio for a local custom-client experiment, add Streamable HTTP as a second verified transport if deployment is part of scope. Do not choose legacy SSE as the default. Load selected execution/domain context before argument generation and presentation context before synthesis. If K tools are exposed at once, all their minimum execution rules must already be available to that generation step, unless the host uses a distinct tool-selection step followed by a second argument-generation step.

Suggested experiment axes: all tools/full instructions baseline; top-K/full instructions; top-K/progressive context; metadata leakage; schema compliance; tool confusion; date/identifier semantics; context cache invalidation; multi-tool presentation conflicts. Suggested acceptance evidence: retrieval recall@K, correct parameters, correct final presentation, model-input token counts, latency, and explicit zero leakage assertions.
