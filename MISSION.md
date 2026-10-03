# Mission: Build a typed MCP server

## Why
Build an MCP server like this repository’s read-only bookstore service, and understand how a host discovers tool definitions, chooses a tool, sends arguments, and receives a validated result. The goal is to be able to extend or build a small server confidently without assuming MCP itself runs the model or enforces host-side policies.

## Success looks like
- Explain the request path from MCP initialization and `tools/list` through `tools/call` to the server handler and result.
- Define a useful tool contract with a clear name, description, constrained input schema, validation, and predictable output.
- Implement and test a small typed MCP tool using the patterns in this repository.

## Constraints
- Learn by grounding explanations and exercises in this repository’s Python MCP server and agent example.
- Prefer short, hands-on lessons with immediate feedback and primary-source references.

## Out of scope
- Building a production deployment or a full-featured agent framework before the basic tool lifecycle is clear.
