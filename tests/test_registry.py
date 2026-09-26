import json

import pytest
from mcp import Client

from modern_mcp.context_loader import ContextCatalog
from modern_mcp.registry import ContextError, ToolContextRegistry
from modern_mcp.retrieval import BM25
from modern_mcp.server import create_server

pytestmark = pytest.mark.anyio


async def test_sentinel_never_reaches_any_request_and_warm_cache():
    sentinel = "RETRIEVAL_ONLY_SENTINEL_9f731"
    catalog = ContextCatalog()
    original = catalog.metadata["get_books"]
    retrieval = original.retrieval.model_copy(
        update={"keywords": [*original.retrieval.keywords, sentinel]}
    )
    catalog.metadata["get_books"] = original.model_copy(update={"retrieval": retrieval})
    async with Client(create_server(catalog=catalog)) as client:
        registry = ToolContextRegistry(client, "sentinel-test")
        await registry.refresh()
        candidates = [name for name, _ in registry.retrieve(sentinel)]
        assert candidates == ["get_books"]
        selection = registry.selection_request("book query", candidates)
        prepared = await registry.hydrate(candidates)
        arguments = registry.argument_request("book query", prepared)
        result = await registry.invoke(prepared, "get_books", {"limit": 1})
        synthesis = await registry.synthesis_request(
            "book query", {"get_books": result}, prepared.snapshot
        )
        encoded = json.dumps([selection, arguments, synthesis])
        assert sentinel not in encoded and "_meta" not in encoded
        assert "retrieval" not in arguments
        assert len(arguments["tools"]) == 1
        assert {block["category"] for block in arguments["instructions"]} == {
            "reference",
            "execution",
            "domain",
        }
        assert [p["tool"] for p in synthesis["presentation_policies"]] == ["get_books"]
        reads = registry.resource_reads
        await registry.hydrate(candidates)
        await registry.synthesis_request("book query", {"get_books": result}, prepared.snapshot)
        assert registry.resource_reads == reads
        assert await registry.relative_window("last month") == ("2026-08-01", "2026-09-01")
        assert await registry.relative_window("last 30 days") == ("2026-08-28", "2026-09-27")
        with pytest.raises(ContextError, match="unselected"):
            await registry.invoke(prepared, "get_book_details", {"book_id": "B001"})
        with pytest.raises(ContextError, match="subset"):
            registry.validate_selection(candidates, ["compare_vendors"])


async def test_bad_context_hash_blocks_generation():
    catalog = ContextCatalog()
    ref = catalog.metadata["get_books"].domain_knowledge
    catalog.resources[ref.uri] += " "
    async with Client(create_server(catalog=catalog)) as client:
        registry = ToolContextRegistry(client, "broken-context")
        await registry.refresh()
        with pytest.raises(ContextError, match="hash"):
            await registry.hydrate(["get_books"])


async def test_refresh_invalidates_prepared_generation(client):
    class ChangingClient:
        changed = False

        async def list_tools(self, **kwargs):
            listing = await client.list_tools(**kwargs)
            if self.changed:
                tools = [
                    tool.model_copy(update={"description": tool.description + " updated"})
                    for tool in listing.tools
                ]
                listing = listing.model_copy(update={"tools": tools})
            return listing

        async def read_resource(self, *args, **kwargs):
            return await client.read_resource(*args, **kwargs)

    connection = ChangingClient()
    registry = ToolContextRegistry(connection, "refresh-test")
    await registry.refresh()
    prepared = await registry.hydrate(["get_books"])
    connection.changed = True
    await registry.refresh()
    with pytest.raises(ContextError, match="old registry"):
        registry.argument_request("query", prepared)
    assert registry.loaded_document_count == 0


def test_bm25_ties_no_match_and_distinct_query_terms():
    index = BM25({"b": "books title", "a": "books title"})
    assert [name for name, _ in index.rank("books", 2)] == ["a", "b"]
    assert index.rank("books books", 2) == index.rank("books", 2)
    assert index.rank("volcano eruption", 2) == []
    with pytest.raises(ValueError):
        index.rank("", 1)


async def test_altered_model_projection_is_rejected(client):
    from dataclasses import replace

    registry = ToolContextRegistry(client, "altered-projection")
    await registry.refresh()
    prepared = await registry.hydrate(["get_books"])
    altered = replace(prepared, instructions=prepared.instructions[:1])
    with pytest.raises(ContextError, match="altered"):
        registry.argument_request("query", altered)


async def test_held_out_retrieval_cases(client):
    from pathlib import Path

    registry = ToolContextRegistry(client, "corpus-test")
    await registry.refresh()
    cases = json.loads(
        (Path(__file__).parents[1] / "examples/retrieval_cases.json").read_text("utf-8")
    )
    assert len(cases) == 28
    for case in cases:
        names = {name for name, _ in registry.retrieve(case["query"], 3)}
        assert set(case["required"]).issubset(names), case["query"]
        if not case["required"]:
            assert not names, case["query"]


async def test_changed_fixture_result_cannot_mix_with_registry(client):
    registry = ToolContextRegistry(client, "fixture-version-test")
    await registry.refresh()
    prepared = await registry.hydrate(["get_book_details"])
    result = await registry.invoke(prepared, "get_book_details", {"book_id": "B001"})
    result["provenance"]["sha256"] = "0" * 64
    with pytest.raises(ContextError, match="different fixture"):
        await registry.synthesis_request("Details", {"get_book_details": result}, prepared.snapshot)
