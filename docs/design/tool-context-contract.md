# Local tool context publication contract

Status: implemented storage and reference-client contract.
Source decision: [Choose the per-tool context publication contract](../../.scratch/bookstore-context/issues/02-context-publication-contract.md).

## Purpose and boundary

Every business tool advertises four categories in its definition metadata: retrieval metadata, execution instructions, domain knowledge, and presentation policy. Retrieval is inline and client-only. The other categories are references to JSON documents packaged locally with the server and served through MCP resources.

Local means no remote content service is required. It does not mean the MCP client must share the server's filesystem. The client uses `read_resource(uri)` over the existing MCP connection; it never receives or opens the server's absolute paths.

The official SDK supports `MCPServer.tool(meta=...)` and resource registration. These resource references and the category schema are this application's convention, not automatically executed protocol hooks. [Verified public SDK APIs](../research/mcp-v2-registry-langgraph.md).

## Local files and single source of truth

Use JSON, with UTF-8 encoding and standard-library parsing. JSON is chosen to avoid an additional YAML parser and use the same data model as protocol metadata; this is not a claim that JSON will benchmark faster in this small fixture.

Planned packaged files:

```text
src/modern_mcp/context/
  tool_contexts.json
  get_books/execution.json
  get_books/domain.json
  get_books/presentation.json
  ... equivalent category files for each of the seven tools ...
```

`tool_contexts.json` is the authoring manifest. It holds inline retrieval metadata and relative file references for the other categories. It does not duplicate their document bodies. Startup validates the manifest, all referenced documents, category/tool identity, the exact registered tool set, and schema-supported version numbers before serving.

File references must resolve to allowlisted packaged files within the context directory. Resource requests are resolved through the startup-built URI map, never by converting arbitrary caller URI fragments into filesystem paths. Authors may reuse glossary text through the authoring/build layer, but the client receives one self-contained resolved category document; it must not recursively discover hidden file dependencies to make an ordinary call.

## Authoring manifest example

This is a proposed manifest entry, not an application file created by this planning effort:

```json
{
  "schema_version": 1,
  "tools": {
    "get_books": {
      "retrieval": {
        "summary": "Find catalog books, including books received from specified vendors during a period.",
        "keywords": ["books", "catalog", "genre", "imported", "received", "vendor"],
        "example_queries": [
          "Show science fiction books imported last month from vendor A",
          "List the books in the catalog"
        ]
      },
      "execution_instructions": {"file": "get_books/execution.json"},
      "domain_knowledge": {"file": "get_books/domain.json"},
      "presentation_policy": {"file": "get_books/presentation.json"}
    }
  }
}
```

The actual manifest has all seven tools. Retrieval fields are positive matching material; do not place negative examples in the indexed document, where they could increase the wrong tool's BM25 score. When-not-to-call guidance belongs in execution instructions. Evaluation queries are separate assets, including cases not copied from these example queries.

## MCP tool-definition metadata

Use the custom, non-reserved key `modern_mcp/tool_context` under definition `_meta`. Its object contains:

- `schema_version`: integer application contract version, initially 1.
- `retrieval`: the inline retrieval object from the manifest.
- `execution_instructions`, `domain_knowledge`, `presentation_policy`: typed resource references containing `uri`, `sha256`, and `mime_type` (`application/json`).

For a category document, canonical bytes are UTF-8 JSON with sorted object keys, compact separators, and no non-finite numeric values. Lists preserve their order. Compute SHA-256 over these bytes and serve those exact bytes. Use a resource URI of the form `bookstore://context/v1/{tool_name}/{category}/{sha256}`. The hash makes the reference immutable for the lifetime of its advertised definition and is a consistency check, not proof of authenticity.

Example category names in URIs are `execution`, `domain`, and `presentation`. Do not send authoring file paths in `_meta`.

The client takes a snapshot containing schemas, exact context references, and the public fixture reference. Its identity includes definitions, description text, context hashes, and fixture/reference data, excluding transient cache hints. Results carry a fixture digest checked against the registry. A dispatch uses the same snapshot that built its model-facing definitions and loaded its context. After refresh, old requests are rebuilt rather than mixing versions.

## Category document shape

Every document contains `schema_version`, `tool_name`, `category`, and a category-specific `body` object. Reject unknown category names, mismatched tool names, unsupported versions, malformed bodies, and unknown keys according to the declared schema.

Execution body:

- `purpose` and `when_to_use`: short tool-selection guidance.
- `when_not_to_use`: exclusions or pointers to other tool names.
- `parameter_rules`: parameter name plus rules and examples.
- `preconditions`: conditions to check before calling.

Domain body:

- `terms`: named domain terms and definitions.
- `business_rules`: rules needed to interpret parameters and results correctly.
- `examples`: concrete domain examples with interpretation.
- `limitations`: boundaries of the dummy fixture and supported analysis.

Presentation body:

- `default_format`: the appropriate default for this tool's returned data.
- `format_rules`: conditional choices for a single value/short answer, several rows, a time series, and real source hyperlinks with plain-reference fallback. A condition is documented policy text, not executable code.
- `required_facts`: units, period, scope, pagination status, and provenance as applicable.
- `tone`: concise and factual.
- `citation_rules`: how to refer to actual returned provenance; never invent an external source.
- `fallback_format`: behavior when the host cannot render the preferred format.

The review-ready [specification](../../.scratch/bookstore-context/spec.md) contains bookstore rules and presentation defaults. Policies choose between scalar/short text, details, tables, charts, and genuine source references according to the actual result and host capabilities. The document schema allows structured policy text; it does not imply that an LLM will obey it automatically.

## Registry hydration and model projection

The reference client:

1. Lists all authorized tool definitions, following discovery pagination.
2. Validates the custom metadata and retains schemas, retrieval documents, and category references privately.
3. Builds BM25 from retrieval fields only and ranks the query deterministically.
4. Reads the required category resources for the chosen flow, verifies their hashes and identity, and extracts their body text into an explicitly constructed instruction message.
5. Builds model-facing definitions from an allowlist: tool name, concise description, and input schema. Output schemas stay available to the response validator; a future provider adapter may expose them only where the provider supports that.
6. Keeps raw discovery objects, `_meta`, retrieval terms/examples/scores, local paths, and full registry contents out of selection, argument-generation, and synthesis requests.

Instruction documents must not carry copied retrieval blocks. A word such as "vendor" can legitimately occur in both categories; retrieval privacy is about which data structures reach the model, not a ban on ordinary shared domain vocabulary. Use a unique retrieval-only sentinel plus request-object inspection to verify this boundary.

Core loading requirement: execution instructions and necessary domain knowledge must reach the argument-generating model request, not merely a pre-dispatch hook after arguments already exist. Both experiment flows use this same hydration/projection boundary.

## Failure and refresh requirements

Missing, invalid, oversized, or hash-mismatched execution/domain documents prevent argument generation and dispatch for the affected tool. Never substitute an empty instruction block and continue. The small sample may surface a typed context error rather than implement a retry framework.

Result projection also strips tool-result `_meta` and any internal registry fields. Business output data is untrusted data, not an instruction source. Presentation loading failures prevent claiming policy-compliant synthesis; do not silently use arbitrary defaults as though the policy was loaded.

Context files are static in the baseline server process. Changing them requires restarting/rebuilding definitions, which produces new hashes. A reconnect refetches discovery; a supported current-protocol list-change subscription or explicit refresh invalidates the derived registry, retrieval index, and context references together. Cache immutable documents by server identity, URI, and hash. SDK response caching alone does not refresh a separate derived registry.

## Acceptance evidence

- All seven definitions have inline retrieval and exactly three valid instruction references.
- Every advertised URI resolves through MCP, with the expected identity, media type, and canonical-byte hash.
- A client in a different working directory builds the registry without opening server files directly.
- A malformed or missing mandatory context resource blocks dispatch.
- Requests built for both sample flows and final synthesis contain no raw metadata or retrieval-only sentinel.
- A changed context document yields a new reference; a request built against an older snapshot is rebuilt or rejected if the client has refreshed.
