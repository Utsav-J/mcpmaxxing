# Choose a reproducible local tool-retrieval baseline

Id: 04
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: none

## Question

What local BM25/dense/hybrid comparison is in scope, and may setup download a pinned embedding model once?

2026-09-26 user decision: BM25 only for now; dense retrieval is deferred, with no model download or hosted embedding API. Top-K defaults and detailed failure/query semantics still need specification. Dense/hybrid implementation and benchmarking are outside this first specification.

Define top-K default/bounds, query source, deterministic score/rank outputs, no-match behavior, follow-up query handling, and how retrieval stays separate from model prompts and authorization. The reference client should remain small; do not design a general agent platform.

## Comments

Proposed mechanics are now concrete in [specification section 9](../spec.md): default K=3, positive-IDF BM25 with fixed normalization, positive-score gate, stable tie-breaking, no model expansion, and no dense/hybrid dependencies. User's BM25-only choice is settled; this ticket remains open for formal review of these mechanics.

## Answer

The user authorized implementation, superseding the formal review gate. [BM25](../../../src/modern_mcp/retrieval.py) implements the documented formula, tokenization, positive-score gate, bounds, and tie-breaking. The 28 authored cases are evaluated in the offline report and tested; no dense/hosted dependency is present.
