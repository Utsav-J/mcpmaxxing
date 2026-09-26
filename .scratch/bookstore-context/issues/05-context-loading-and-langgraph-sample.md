# Specify context loading and the illustrative LangGraph flow

Id: 05
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 01, 02, 04

## Question

Should the sample load minimum execution/domain context for every top-K tool before generating calls, or select names first, load their context, then generate arguments? How does presentation policy enter final synthesis, including results from multiple tools?

2026-09-26 user decision: include BOTH flows for comparison: hydrate execution/domain context for all top-K candidates before generating calls; and provisionally choose tool names first, hydrate execution/domain context for that subset, then generate arguments. Presentation loading/composition and failure paths still need specification. User request is a reference registry and illustrative LangGraph code, not a functioning LLM agent.

The final sample must show separate client-only retrieval state and model-facing messages/tool definitions; registry discovery, context hydration, model-call construction, output validation, safe result projection, and presentation loading. It must forbid invocation with missing or mismatched required context, prevent unselected tool dispatch, and show an explicit injectable model boundary without requiring an API key. No claim that late pre-dispatch instructions can repair arguments already generated without them.

## Comments

Draft asset: [Two context-loading flows](../../../docs/design/context-loading-flows.md). Contains an illustrative LangGraph topology, the shared privacy/hydration boundary, and an honest offline comparison contract. Both flows are user-approved; exact presentation precedence remains pending.

2026-09-26 — User clarified support for scalar/short text, tables, hyperlinks, and charts. [Specification sections 10–11](../spec.md) now specify both flows and propose loading used tools' presentation policies before synthesis, with user format preferences overriding defaults while factual requirements remain. This ticket remains open for formal review of the complete flow contract.

## Answer

The user authorized implementation. [Both LangGraph flows](../../../examples/langgraph_context_flows.py) and the [registry](../../../src/modern_mcp/registry.py) implement the documented ordering, name/subset gates, context integrity checks, snapshot consistency, result validation, and used-tool presentation hydration. Offline adapters are clearly labeled; no model quality claim or production agent is implied.
