# Verify current MCP metadata APIs and LangGraph context ordering

Id: 01
Parent: ../map.md
Label: wayfinder:research
Type: research
Mode: AFK
Status: resolved
Assignee: /root/mcp_capabilities
Blocked by: none

## Question

Which public APIs in the current stable official `mcp` SDK register tool metadata, resources, prompts, typed input/output schemas, annotations, and local stdio/Streamable HTTP clients, and which minimal official LangGraph APIs illustrate loading context before generating tool calls?

Validate against v2, not the old `FastMCP` API. Verify package/protocol version, optional skills-extension support versus unsupported assumptions, context/resource cache behavior, and whether no-model examples can demonstrate request construction without claiming LLM behavior. Link primary sources and a small research asset; do not implement the application.

## Answer

[Verified v2 registry and LangGraph APIs](../../../docs/research/mcp-v2-registry-langgraph.md). Official mcp 2.2.0 supports metadata registration, typed schemas, resources, prompts, response caching, and explicit change subscriptions. Skills is a stable optional protocol extension but has no verified built-in v2.2.0 SDK wrapper; baseline context uses resources. Explicit LangGraph edges can demonstrate context loading before constructing an allowlisted request without claiming real LLM behavior. No packages installed or application code implemented.
