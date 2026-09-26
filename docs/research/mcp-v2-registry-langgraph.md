# MCP v2 registry and LangGraph API verification

Verified 2026-09-26 against tagged official SDK v2.2.0 and official LangGraph documentation. This is a source-backed specification asset, not installed or executed application code.

## Version and server public surface

Use official `mcp==2.2.0`, `from mcp.server import MCPServer`, and current protocol 2026-07-28. v2.2.0 is a stable release; it supports earlier protocol clients too. [Tagged release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0), [v2 stable release and rename](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0)

Verified public registration signatures:

```python
server.tool(name=None, title=None, description=None,
            annotations=None, icons=None, meta=None,
            structured_output=None)
server.resource(uri, *, name=None, title=None, description=None,
                mime_type=None, icons=None, annotations=None,
                meta=None, security=None)
server.prompt(name=None, title=None, description=None, icons=None)
```

Tool `meta` becomes definition `_meta` in `tools/list`; Python attributes are `input_schema` and `output_schema`. The prompt decorator has no `meta` parameter. Resource URI variables must match function parameters; static resources have no ordinary parameters or injected Context. Use `server.run(transport="stdio")` or `server.run(transport="streamable-http", host="127.0.0.1", port=8000)`. HTTP transport options belong to `run`, not the constructor. [Tagged server source](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/server/mcpserver/server.py)

Type hints generate input schemas; `Annotated[..., Field(description=..., ...)]` adds field guidance and constraints, and `Literal` adds enums. `ToolAnnotations(read_only_hint=True, open_world_hint=False)` describes this closed dummy catalog. These are hints, not enforcement; destructive/idempotent hints only have meaning for non-read-only tools. [Official tools documentation](https://py.sdk.modelcontextprotocol.io/servers/tools/)

Return a Pydantic model for a typed object output; `structured_output=True` rejects unrepresentable return types at registration. SDK validation covers output values, and normal values populate content plus structured data. Python `structured_content` corresponds to wire `structuredContent`; the client's model projection decides whether/how to present either. [Structured output documentation](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)

## Client, resource loading, and cache

Minimal public client shape:

```python
from mcp import Client
from mcp.client.stdio import StdioServerParameters

target = StdioServerParameters(command="python", args=["server.py"])
# Or target = "http://127.0.0.1:8000/mcp"
async with Client(target) as client:
    listing = await client.list_tools()
    context = await client.read_resource("bookstore://context/example")
    result = await client.call_tool("example", {"book_id": "B001"})
```

`list_tools(cursor=..., cache_mode=...)` returns `ListToolsResult`; follow `next_cursor` until absent. `read_resource(uri, cache_mode=...)` and `call_tool(name, arguments)` return protocol result objects. `Client.listen(tools_list_changed=True, resources_list_changed=True, resource_subscriptions=[uri])` is an async context manager; it receives current-protocol change events and evicts SDK cache entries before consumers refetch. No replay is guaranteed after a dropped subscription: reconnect and refetch. [Tagged Client source](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/client/client.py)

The SDK cache has `CacheConfig`, an in-memory default store, and call modes `use`, `refresh`, `bypass`. TTL handling and event eviction belong to the response cache. Neither the cache nor resource loading inserts instructions into a model request. A separately derived retrieval index/context registry therefore needs its own version/hash checks and invalidation. [Tagged caching implementation](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/client/caching.py)

## Skills: standard exists; SDK support differs

The official optional Skills extension is stable against 2026-07-28, with `skills/list`, `skills/get`, optional `resources/directory/read`, and files read through resources. It is outside the baseline tools/resources/prompts API. [Stable extension specification](https://github.com/modelcontextprotocol/ext-skills/blob/main/specification/stable/skills.mdx)

Do **not** specify built-in `Skills(...)`, `client.list_skills()`, or `client.get_skill()` for mcp 2.2.0. Official SDK issue #3486 is open and requests those APIs because support is absent. The generic extension mechanism exists but is not proof of a shipped Skills implementation. Baseline resource-backed context is immediately compatible; Skills support is an optional future/custom extension experiment with explicit host support. [Official SDK support issue](https://github.com/modelcontextprotocol/python-sdk/issues/3486), [Generic extension documentation](https://py.sdk.modelcontextprotocol.io/advanced/extensions/)

## Minimal LangGraph boundary

Official current APIs provide `StateGraph`, `START`, `END`, `add_node`, `add_edge`, `add_conditional_edges`, `compile`, and compiled `invoke`/`ainvoke`. Nodes consume state and return updates; a `context_schema` with injected `Runtime` can hold dependencies such as the client registry. These APIs need no model provider. [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api), [Runtime reference](https://reference.langchain.com/python/langgraph/runtime/Runtime)

Illustrative topology, with project functions intentionally unspecified:

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(ExperimentState, context_schema=Dependencies)
graph.add_node("retrieve", retrieve_candidates)
graph.add_node("load_context", load_execution_and_domain)
graph.add_node("build_request", build_allowlisted_model_request)
graph.add_node("inspect_request", inspect_without_calling_a_model)
graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "load_context")
graph.add_edge("load_context", "build_request")
graph.add_edge("build_request", "inspect_request")
graph.add_edge("inspect_request", END)
reference = graph.compile()
```

Edges ensure context loading finishes before constructing the prospective model request. Keep retrieval corpus/raw MCP metadata in dependencies or private registry storage; build the request from allowlisted selected tool names, descriptions, schemas, and loaded execution/domain instructions. Offline inspection can prove ordering, projection, deterministic ranking, and sentinel absence; it cannot prove a real model's tool-call quality or token savings without measuring actual requests.

For a future model-backed adapter, LangChain chat models support `bind_tools(selected_tools)` and `invoke`/`ainvoke`; `.bind_tools()` declares callable schemas and does not execute the tools. Call only after selected context is loaded, then validate tool name/arguments against the same registry generation before `client.call_tool`. After results, load/compose presentation policies before a separate synthesis request. [Official model/tool-calling documentation](https://docs.langchain.com/oss/python/langchain/models)

Use explicit nodes for this experiment. A generic execution node or prebuilt agent does not by itself guarantee pre-generation context loading, retrieval privacy, allowed-tool enforcement, or presentation-policy composition. No hosted model, embedding service, production checkpointer, or LangChain MCP adapter is required for the specified offline reference.
