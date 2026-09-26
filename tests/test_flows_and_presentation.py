import pytest

pytest.importorskip("langgraph")

from examples.langgraph_context_flows import run_flow
from modern_mcp.presentation import HostCapabilities, display_plan
from modern_mcp.registry import ContextError, ToolContextRegistry

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("mode", ["hydrate_candidates", "select_then_hydrate"])
async def test_real_graph_order_and_used_policy_only(client, mode):
    registry = ToolContextRegistry(client, mode)
    await registry.refresh()
    state = await run_flow(
        registry,
        mode,
        "Catalog books imported last month",
        [{"name": "get_books", "arguments": {"limit": 1}}],
    )
    trace = state["trace"]
    assert (
        trace.index("load_execution_and_domain")
        < trace.index("generate_arguments")
        < trace.index("validate_and_invoke")
    )
    assert trace[-1] == "load_presentation_and_synthesize"
    assert [policy["tool"] for policy in state["requests"][-1]["presentation_policies"]] == [
        "get_books"
    ]
    if mode == "select_then_hydrate":
        assert trace.index("select_names") < trace.index("load_execution_and_domain")
        assert registry.loaded_document_count == 3
    assert "retrieval" not in state["requests"][0]


@pytest.mark.parametrize("mode", ["hydrate_candidates", "select_then_hydrate"])
async def test_no_match_and_declined_tool_do_not_invoke(client, mode):
    registry = ToolContextRegistry(client, mode)
    await registry.refresh()
    initial_reads = registry.resource_reads
    state = await run_flow(registry, mode, "Volcano seismic eruption", [])
    assert state["trace"] == ["retrieve", "no_call"]
    assert registry.resource_reads == initial_reads
    state = await run_flow(registry, mode, "Catalog books", [])
    assert "validate_and_invoke" not in state["trace"]
    assert "load_presentation_and_synthesize" not in state["trace"]


async def test_unselected_scripted_call_is_rejected(client):
    registry = ToolContextRegistry(client, "rejection-test")
    await registry.refresh()
    with pytest.raises(ContextError):
        await run_flow(
            registry,
            "select_then_hydrate",
            "monthly sales trend",
            [{"name": "get_book_details", "arguments": {"book_id": "B001"}}],
            k=1,
        )


async def test_scalar_table_links_chart_and_fallback(client):
    registry = ToolContextRegistry(client, "display-test")
    await registry.refresh()
    prepared = await registry.hydrate(["get_stock_availability", "get_sales_trends"])
    stock = await registry.invoke(prepared, "get_stock_availability", {"book_ids": ["B003"]})
    policy = (await registry.load("get_stock_availability", "presentation")).body.model_dump()
    plan = display_plan(stock, policy)
    assert plan["format"] == "scalar" and plan["snapshot"] == "2026-09-26"
    assert plan["source"]["clickable"] is False
    assert (
        display_plan(stock, policy, HostCapabilities(resource_links=True))["source"]["clickable"]
        is True
    )
    assert display_plan(stock, policy, requested_format="table")["format"] == "table"
    sales = await registry.invoke(prepared, "get_sales_trends", {})
    policy = (await registry.load("get_sales_trends", "presentation")).body.model_dump()
    assert display_plan(sales, policy)["format"] == "table"
    chart = display_plan(sales, policy, HostCapabilities(charts=True))
    assert chart["format"] == "chart" and chart["axis_labels"] == {"x": "Date", "y": "Sold units"}


async def test_multiple_used_tool_policies_stay_separate(client):
    registry = ToolContextRegistry(client, "mixed-policy-test")
    await registry.refresh()
    prepared = await registry.hydrate(["get_book_details", "get_stock_availability"])
    results = {
        "get_book_details": await registry.invoke(
            prepared, "get_book_details", {"book_id": "B001"}
        ),
        "get_stock_availability": await registry.invoke(
            prepared, "get_stock_availability", {"book_ids": ["B003"]}
        ),
    }
    request = await registry.synthesis_request("Details and stock", results, prepared.snapshot)
    policies = {policy["tool"]: policy["body"] for policy in request["presentation_policies"]}
    assert set(policies) == set(results)
    assert (
        display_plan(results["get_book_details"], policies["get_book_details"])["format"]
        == "detail"
    )
    assert (
        display_plan(results["get_stock_availability"], policies["get_stock_availability"])[
            "format"
        ]
        == "scalar"
    )
