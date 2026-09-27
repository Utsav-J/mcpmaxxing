import json

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from modern_mcp.bookstore import Bookstore
from modern_mcp.context_loader import META_KEY
from modern_mcp.contracts import CONTRACTS
from modern_mcp.server import create_server

pytestmark = pytest.mark.anyio

CALLS = {
    "get_books": {"limit": 2},
    "get_book_details": {"book_id": "B001"},
    "list_stock_receipts": {"book_ids": ["B001"]},
    "get_stock_availability": {"book_ids": ["B003"]},
    "get_vendor_summary": {"vendor_id": "VENDOR-A"},
    "get_sales_trends": {"interval": "week"},
    "compare_vendors": {"vendor_ids": ["VENDOR-A", "VENDOR-B"]},
}


@pytest.mark.parametrize("name", CALLS)
async def test_explicit_tools_forward_filters_and_pagination(name, tmp_path):
    store = Bookstore()
    contract = CONTRACTS[name]
    values = {
        "limit": 1,
        "genre": "fiction",
        "vendor_ids": ["VENDOR-A", "VENDOR-B"],
        "book_ids": ["B001"],
        "received_from": "2026-08-01",
        "received_before": "2026-09-01",
        "sold_from": "2026-08-01",
        "sold_before": "2026-09-01",
        "stock_status": "in_stock",
        "interval": "week",
        "book_id": "B001",
        "vendor_id": "VENDOR-A",
    }
    arguments = {
        key: value for key, value in values.items() if key in contract.input_model.model_fields
    }
    server = create_server(store, cache_path=tmp_path / "cache.sqlite3")
    expected = getattr(store, name)(contract.input_model.model_validate(arguments))
    actual = await server.call_tool(name, arguments)
    assert not actual.is_error
    assert actual.structured_content == expected.model_dump(mode="json")
    cursor = actual.structured_content["data"].get("next_cursor")
    if cursor:
        arguments["cursor"] = cursor
        expected = getattr(store, name)(contract.input_model.model_validate(arguments))
        actual = await server.call_tool(name, arguments)
        assert not actual.is_error
        assert actual.structured_content == expected.model_dump(mode="json")


async def test_discovery_typed_calls_contexts_and_resources(client):
    import hashlib

    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == set(CONTRACTS)
    for tool in tools:
        assert tool.input_schema["additionalProperties"] is False
        assert tool.annotations.read_only_hint is True
        result = await client.call_tool(tool.name, CALLS[tool.name])
        assert not result.is_error
        Draft202012Validator(tool.output_schema, format_checker=FormatChecker()).validate(
            result.structured_content
        )
        meta = tool.meta[META_KEY]
        assert set(meta) == {
            "schema_version",
            "retrieval",
            "execution_instructions",
            "domain_knowledge",
            "presentation_policy",
        }
        for category in ("execution_instructions", "domain_knowledge", "presentation_policy"):
            ref = meta[category]
            resource = (await client.read_resource(ref["uri"])).contents[0]
            assert resource.mime_type == "application/json"
            assert hashlib.sha256(resource.text.encode()).hexdigest() == ref["sha256"]
            doc = json.loads(resource.text)
            assert doc["tool_name"] == tool.name
            assert len(resource.text.encode()) <= 32768
    assert (
        json.loads((await client.read_resource("bookstore://reference")).contents[0].text)[
            "manifest"
        ]["as_of_date"]
        == "2026-09-26"
    )
    assert (
        json.loads((await client.read_resource("bookstore://books/B001")).contents[0].text)["data"][
            "stock_units"
        ]
        == 17
    )
    assert len((await client.list_resource_templates()).resource_templates) == 1


@pytest.mark.parametrize(
    "tool,args,code",
    [
        ("get_books", {"surprise": "ignored?"}, "INVALID_ARGUMENT"),
        ("get_books", {"limit": True}, "INVALID_ARGUMENT"),
        ("get_books", {"limit": "20"}, "INVALID_ARGUMENT"),
        ("get_books", {"limit": 51}, "INVALID_ARGUMENT"),
        ("get_books", {"vendor_ids": []}, "INVALID_ARGUMENT"),
        ("get_books", {"vendor_ids": ["VENDOR-A", "VENDOR-A"]}, "INVALID_ARGUMENT"),
        (
            "get_books",
            {"received_from": 1785542400, "received_before": "2026-09-01"},
            "INVALID_ARGUMENT",
        ),
        (
            "get_books",
            {"received_from": "2026-08-01T00:00:00", "received_before": "2026-09-01"},
            "INVALID_ARGUMENT",
        ),
        ("get_books", {"received_from": "2026-08-01"}, "INVALID_ARGUMENT"),
        (
            "get_books",
            {"received_from": "2026-08-01", "received_before": "2027-01-01"},
            "UNSUPPORTED_WINDOW",
        ),
        ("get_book_details", {"book_id": "B999"}, "UNKNOWN_ID"),
        ("get_stock_availability", {"book_ids": ["B999"]}, "UNKNOWN_ID"),
        ("get_stock_availability", {"as_of": "2026-08-01"}, "INVALID_ARGUMENT"),
        ("compare_vendors", {"vendor_ids": ["VENDOR-A"]}, "INVALID_ARGUMENT"),
        ("get_sales_trends", {"metric": "revenue"}, "INVALID_ARGUMENT"),
    ],
)
async def test_errors_are_bounded_and_not_success_schema(client, tool, args, code):
    result = await client.call_tool(tool, args)
    assert result.is_error
    text = result.content[0].text
    assert code in text
    assert len(text) < 600
    assert "Traceback" not in text and "Python Stuff" not in text
    assert result.structured_content is None


async def test_prompts_are_templates_not_execution(client):
    prompts = (await client.list_prompts()).prompts
    assert {prompt.name for prompt in prompts} == {"review_imports", "compare_vendor_supply"}
    for prompt in prompts:
        rendered = await client.get_prompt(
            prompt.name,
            {
                "received_from": "2026-08-01",
                "received_before": "2026-09-01",
                "vendor_ids": "VENDOR-A,VENDOR-C",
            },
        )
        text = rendered.messages[0].content.text
        assert "resources" in text and "2026-08-01" in text
        assert META_KEY not in text
