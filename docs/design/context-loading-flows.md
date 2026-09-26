# Two context-loading flows for the reference client

Status: both flows implemented as offline examples; no production agent or model provider.
Source decision: [Specify context loading and the illustrative LangGraph flow](../../.scratch/bookstore-context/issues/05-context-loading-and-langgraph-sample.md).
Both flows use the same [publication contract](tool-context-contract.md), registry snapshot, BM25 candidates, and input/output validation.

Runnable example: [LangGraph context flows](../../examples/langgraph_context_flows.py).

## Flow A: hydrate candidates before generating calls

```text
query
  -> BM25 top-K (client-only retrieval metadata)
  -> load execution + domain resources for every candidate
  -> construct request with only candidate definitions + loaded context
  -> generate arguments / optionally decline to call
  -> validate names, arguments, and snapshot
  -> invoke approved read-only tools
  -> validate/project results
  -> load presentation policies for tools actually used
  -> construct synthesis request
```

The prospective argument-generating model sees enough context to choose among all candidates and populate their arguments. Context-loading cost grows with K and document size. Some loaded context may belong to a tool the model never calls.

## Flow B: provisionally choose names, then hydrate

```text
query
  -> the same BM25 top-K
  -> construct selection request with candidate names + descriptions only
  -> select a subset of names (no arguments; no tool execution)
  -> validate selection against candidates
  -> load execution + domain resources for the selected subset
  -> construct argument request with selected definitions + loaded context
  -> generate arguments / optionally decline to call
  -> validate names, arguments, and snapshot
  -> invoke approved read-only tools
  -> validate/project results
  -> load presentation policies for tools actually used
  -> construct synthesis request
```

Selection is provisional: after seeing execution/domain instructions, the argument stage may decline the selected tool. Do not dispatch merely because a name was selected. Choosing a name first has less domain context and adds a model round trip in a future model-backed adapter; smaller hydrated context does not establish better end-to-end results.

A name outside the current candidate set is rejected. A proposed call outside the hydrated set is rejected. The minimal example returns an explicit selection/context error or no-call outcome rather than silently expanding the tool set. A future full agent could implement reretrieval, but that is outside this reference's required scope.

## LangGraph topology sketch

This factory illustrates ordering with the current public `StateGraph` API. The later sample supplies state schemas and node implementations; the code here does not pretend to be a complete agent. [Verified LangGraph API and model boundary](../research/mcp-v2-registry-langgraph.md).

```python
from langgraph.graph import END, START, StateGraph


def build_reference_graph(state_schema, dependencies_schema, nodes, mode):
    common_tail = [
        "build_argument_request",
        "argument_adapter",
        "validate_calls",
        "invoke_tools",
        "validate_results",
        "load_presentation",
        "build_synthesis_request",
        "synthesis_adapter",
    ]
    if mode == "hydrate_candidates":
        sequence = ["retrieve", "hydrate_candidates"] + common_tail
    elif mode == "select_then_hydrate":
        sequence = [
            "retrieve",
            "build_selection_request",
            "selection_adapter",
            "validate_selection",
            "hydrate_selection",
        ] + common_tail
    else:
        raise ValueError("Unsupported context-loading mode")

    graph = StateGraph(state_schema, context_schema=dependencies_schema)
    previous = START
    for name in sequence:
        graph.add_node(name, nodes[name])
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()
```

In the offline reference, adapters inspect constructed requests and/or return clearly labeled scripted outputs. A future model adapter uses the same explicit boundary. The no-candidate/no-call path must short-circuit invocation and presentation hydration for unused tools; the implementation can use conditional edges or nodes with explicit no-op handling. Mandatory-context errors stop the graph. These requirements are not demonstrated merely by compiling the happy-path topology.

## State boundaries

Dependencies hold the private registry, retrieval corpus, MCP client, and context cache. Shared graph state contains only the query, opaque snapshot identity, selected tool names, projected messages/definitions, validated call data, and projected results needed downstream. Avoid carrying raw MCP definitions or retrieval fields in a message-oriented state that an adapter could forward wholesale.

Only purpose-built request constructors populate model-facing data. Both argument requests include execution/domain context before tool-call generation. Synthesis construction uses actual result data and policies for tools actually used. The review-ready specification proposes that explicit user format requests override default formats while factual units, scope, date bounds, provenance, and page completeness remain required; policies differ across tools according to their output shape.

Model-facing messages are scoped to the current request. Do not accumulate every previously loaded tool's instructions in a permanent conversation-level system prompt. The sample labels category/tool context clearly so two tools' parameter rules cannot be confused.

## Offline comparison

Use the same query corpus, registry generation, K, and resource bodies for both modes. Report per scenario:

- retrieved candidates and expected tool-set coverage;
- scripted selected/called names, explicitly labeled as fixture choices;
- loaded context documents and UTF-8 byte counts;
- constructed request sizes for each stage and total across stages;
- number of prospective model stages, including selection and synthesis;
- cold versus warm context reads;
- mandatory-context checks and retrieval-only leakage checks.

Do not call bytes or characters tokens. Exact token reporting requires a stated tokenizer/model. Do not claim tool-choice accuracy, parameter quality, instruction compliance, or lower latency from an offline scripted adapter. A later model-backed experiment can compare those using the same inputs and a stated model/settings, but it is not required here.
