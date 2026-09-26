# Choose the per-tool context publication contract

Id: 02
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 01

## Question

Are the four categories fully inline in tool-definition metadata, or is retrieval inline while execution/domain/presentation context is represented by typed versioned resource references? What does each payload contain, and how are schema/context versions kept consistent?

User requirement: all tools have all four categories, retrieval metadata is never sent to the model, and execution/domain context is available before calling a tool. Recommendation pending user response: retrieval inline; three instruction categories with resource URI, revision/content hash, media type, and explicit load stage. Distinguish client-visible metadata from model-visible instruction text. Avoid duplicated canonical document content across metadata and resources.

The final contract must define a custom non-reserved metadata namespace, validation, context-load failure behavior, and a client projection that cannot accidentally forward raw `_meta`.

## Comments

2026-09-26 — User selected inline retrieval metadata and local references for the three instruction categories, with JSON or YAML chosen by the implementation/spec author. Use JSON for this baseline: standard-library parsing and one data format for metadata and resource documents; no performance superiority over YAML is claimed.

## Answer

Use [Local tool context publication contract](../../../docs/design/tool-context-contract.md): inline retrieval under a custom non-reserved metadata key; three typed instruction references; JSON documents packaged locally and accessed by clients through immutable MCP resource URIs. Startup validation, canonical-byte content hashes, registry snapshot consistency, mandatory-context failure behavior, and explicit model-facing allowlists define the boundary. Local file paths remain private to the server.
