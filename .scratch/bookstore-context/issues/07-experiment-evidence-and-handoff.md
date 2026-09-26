# Define acceptance evidence and the implementation handoff

Id: 07
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 02, 03, 04, 05, 06

## Question

What evidence makes the eventual experiment complete without hosted models, and what should the final implementation-ready specification require?

Define annotated natural-language query cases, tool-set recall at K, argument/date/schema cases, retrieval-only sentinel leakage checks across every model request construction, missing-context behavior, deterministic pagination, version/cache consistency, and bounded result delivery. Compare all-tool/full-context and top-K/dynamic-context request construction using an explicit token-count method or honest size proxy. Do not call byte counts model tokens.

Specify meaningful baselines, measurable targets, and which presentation rules can be tested mechanically. Human/mock-generated outputs do not establish LLM compliance or quality. Time and data-volume measurements must state environment and scope; 100 books are not a scale benchmark. Decide deliverable structure for MCP server, fixtures, metadata/resources/prompts, reference registry, illustrative LangGraph integration, and documentation.

## Candidate specification structure

- Confirmed scope, terminology, chosen SDK/protocol versions, and non-goals.
- Wire-level per-tool context contract, versioning, and shared/per-tool resource documents.
- Bookstore fixture invariants and exact input/output contracts for each approved tool.
- Tool descriptions, read-only annotations, explicit validation and error semantics.
- Roles of resources, resource templates, prompts, and any optional skills-extension experiment.
- Client registry discovery/refresh and local retrieval contract.
- Model-facing projection and context-loading stages, illustrated with minimal LangGraph code.
- Acceptance cases and offline evidence, with model-dependent claims explicitly deferred.
- Implementation sequence and final open-question check.

The final approved spec is recorded only after the decision tickets are resolved. A review-ready draft may assemble their proposals beforehand. This outline does not authorize implementation during the wayfinder effort.

## Comments

The [review-ready specification](../spec.md), sections 12–14, proposes contract tests, at least 28 labeled retrieval cases, offline flow comparison, presentation cases, explicit evidence limits, and an implementation sequence. No application code or model-backed experiment has been built. This ticket remains open for final review after its blockers are resolved.

## Answer

The user authorized implementation. [Tests](../../../tests), [offline experiment](../../../examples/offline_experiment.py), and [README](../../../README.md) provide reproducible verification and run commands. At completion, 53 tests passed, lint/format checks passed, the wheel contained all 23 JSON assets, and the authored corpus had recall@3=1.0 with three negative cases returning no candidates. These results do not establish model quality, token savings, or production scale.
