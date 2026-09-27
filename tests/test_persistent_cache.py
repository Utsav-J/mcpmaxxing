"""A restart keeps results; defaults share keys; expiry and invalid input cannot hit."""

import pytest

from examples.agent.cache import Cache
from modern_mcp.server import create_server

pytestmark = pytest.mark.anyio


async def test_result_cache_restart_defaults_validation_and_expiry(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("modern_mcp.result_cache.time.time", lambda: clock[0])
    path = tmp_path / "results.sqlite3"
    first = await create_server(cache_path=path).call_tool("get_books", {})
    assert first.meta["modern_mcp/cache"]["status"] == "miss"
    restarted = create_server(cache_path=path)
    second = await restarted.call_tool("get_books", {"limit": 20})
    assert second.meta["modern_mcp/cache"]["status"] == "hit"
    assert second.structured_content == first.structured_content
    invalid = await restarted.call_tool("get_books", {"unexpected": True})
    assert invalid.is_error and not invalid.meta
    clock[0] += 300
    expired = await restarted.call_tool("get_books", {})
    assert expired.meta["modern_mcp/cache"]["status"] == "miss"
    restarted.cache_revision = "changed"
    changed = await restarted.call_tool("get_books", {})
    assert changed.meta["modern_mcp/cache"]["status"] == "miss"


def test_metadata_cache_persistence_expiry_and_namespace(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("examples.agent.cache.time.time", lambda: clock[0])
    path = tmp_path / "metadata.sqlite3"
    Cache(path, "one").put("catalog", {"tools": ["a"]})
    restarted = Cache(path, "one")
    assert restarted.get("catalog") == {"tools": ["a"]}
    assert Cache(path, "two").get("catalog") is None
    clock[0] += 300
    assert restarted.get("catalog") is None
