# Assign roles to descriptions, schemas, resources, prompts, skills, and transports

Id: 06
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 01, 02

## Question

Which current MCP features belong in the core experiment, and which deserve a small optional extension demonstration?

Resolve concise discriminative tool descriptions and schema-enforced constraints versus instruction prose; typed structured results and provenance; resource templates/shared glossary; optional user-invoked prompts for workflows; the optional skills extension and its actual SDK/client support. Define read-only tool annotations without treating them as enforced security boundaries.

Recommendation to discuss after API research: stdio as the reproducible local transport, a Streamable HTTP smoke path if useful, versioned context resources as the core primitive, prompts for optional workflows, and skills only with verified support/fallback. Registry refresh must honor the selected protocol era's discovery/cache/change mechanisms. No dependence on a generic host magically understanding custom metadata.

## Comments

[Specification sections 2, 5, 7, and 8](../spec.md) contain a concrete proposal: official current SDK, stdio plus loopback Streamable HTTP, typed structured results, versioned instruction resources, reference/fixture/book resources, two optional prompt templates, and skills-extension implementation deferred. Source research verifies API support. This ticket remains open for formal review of feature scope.

## Answer

The user authorized implementation. [Official SDK server](../../../src/modern_mcp/server.py) publishes seven typed tools, 21 context documents, reference/fixture/book resources, and two prompts. Stdio and loopback HTTP pass actual transport tests. Custom metadata semantics remain explicitly client-managed. Skills implementation remains deferred, as documented.
