"""Official MCPServer with strict flat arguments and locally backed resources."""

import argparse
import inspect
import os
import time
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field, ValidationError

from modern_mcp.bookstore import Bookstore, BookstoreError
from modern_mcp.context_loader import META_KEY, ToolContext, load_context_catalog
from modern_mcp.contracts import CONTRACTS, Contract
from modern_mcp.json_support import canonical_json, digest
from modern_mcp.models import CompareInput, VendorSummaryInput
from modern_mcp.result_cache import TTL, ResultCache


def error_result(code, message):
    return CallToolResult(
        content=[TextContent(type="text", text=f"{code}: {message}")], is_error=True
    )


class BookstoreServer(MCPServer):
    """Use public SDK hooks to publish and enforce the same strict input models.

    SDK function-argument models allow extra keys by default. The public list/call
    overrides enforce our `extra=forbid` contract without patching SDK internals.
    Typed return annotations still let the SDK validate structured outputs.
    """

    async def list_tools(self):
        return [
            tool.model_copy(
                update={"input_schema": CONTRACTS[tool.name].input_model.model_json_schema()}
            )
            for tool in await super().list_tools()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any], context=None):
        if name not in CONTRACTS:
            return error_result("UNKNOWN_TOOL", "Tool is not registered.")
        try:
            request = CONTRACTS[name].input_model.model_validate(arguments)
        except ValidationError as exc:
            fields = sorted({".".join(map(str, e["loc"])) or "arguments" for e in exc.errors()})
            return error_result("INVALID_ARGUMENT", "Check fields: " + ", ".join(fields)[:500])
        try:
            key = digest(
                {
                    "revision": self.cache_revision,
                    "tool": name,
                    "arguments": request.model_dump(mode="json"),
                }
            )
            cached = self.result_cache.get(key)
            if cached:
                data, created = cached
                CONTRACTS[name].output_model.model_validate(data)
                result = CallToolResult(
                    content=[TextContent(type="text", text=canonical_json(data))],
                    structured_content=data,
                )
                status = "hit"
            else:
                # ponytail: concurrent cold misses may duplicate reads; coalesce if costly.
                result = await super().call_tool(name, request.model_dump(), context)
                if result.is_error or result.structured_content is None:
                    return result
                created = self.result_cache.put(key, result.structured_content)
                status = "miss"
            return result.model_copy(
                update={
                    "meta": {
                        **(result.meta or {}),
                        "modern_mcp/cache": {
                            "status": status,
                            "ttl_seconds": TTL,
                            "age_seconds": round(time.time() - created, 3),
                        },
                    }
                }
            )
        except ToolError:
            return error_result("TOOL_FAILURE", "Tool execution failed.")


def _handler(store: Bookstore, contract: Contract):
    """Expose a model's flat fields through the SDK's public function registration."""

    def invoke(**kwargs):
        try:
            request = contract.input_model.model_validate(kwargs)
            return getattr(store, contract.name)(request)
        except BookstoreError as exc:
            # Return explicit errors; the SDK skips success-schema validation on errors.
            return error_result(exc.code, str(exc).split(": ", 1)[1])

    parameters = []
    for name, field in contract.input_model.model_fields.items():
        annotation = Annotated[field.rebuild_annotation(), Field(description=field.description)]
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=inspect.Parameter.empty if field.is_required() else field.default,
            )
        )
    invoke.__name__ = contract.name
    invoke.__doc__ = contract.description
    invoke.__signature__ = inspect.Signature(parameters, return_annotation=contract.output_model)
    return invoke


def create_server(
    store: Bookstore | None = None,
    catalog: tuple[dict[str, ToolContext], dict[str, str]] | None = None,
    cache_path=None,
):
    store = store or Bookstore()
    metadata, resources = catalog if catalog is not None else load_context_catalog()
    server = BookstoreServer(
        "Bookstore context experiment",
        version="0.1.0",
        log_level="WARNING",
        instructions=(
            "Read-only demo bookstore. "
            "Clients resolve tool context references before calling tools."
        ),
    )
    server.result_cache = ResultCache(
        cache_path or os.getenv("MCP_CACHE_PATH", "artifacts/mcp-cache.sqlite3")
    )
    server.cache_revision = digest(
        {
            "cache_format": 1,
            "fixture": store.manifest.sha256,
            "contracts": {
                name: {
                    "input": contract.input_model.model_json_schema(),
                    "output": contract.output_model.model_json_schema(),
                    "context": metadata[name].model_dump(mode="json"),
                }
                for name, contract in CONTRACTS.items()
            },
        }
    )
    for name, contract in CONTRACTS.items():
        server.add_tool(
            _handler(store, contract),
            name=name,
            description=contract.description,
            annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
            meta={META_KEY: metadata[name].model_dump(mode="json")},
            structured_output=True,
        )

    def resource_reader(text):
        def read() -> str:
            return text

        return read

    for uri, text in resources.items():
        parts = uri.split("/")
        server.resource(
            uri,
            name=f"{parts[-3]}/{parts[-2]}",
            description=f"Versioned {parts[-2]} context for {parts[-3]}.",
            mime_type="application/json",
        )(resource_reader(text))

    @server.resource("bookstore://reference", mime_type="application/json")
    def reference() -> str:
        return canonical_json(store.reference())

    @server.resource("bookstore://fixtures/bookstore-demo-v1", mime_type="application/json")
    def fixture_descriptor() -> str:
        return canonical_json(store.fixture_descriptor())

    @server.resource("bookstore://books/{book_id}", mime_type="application/json")
    def book_resource(book_id: str) -> str:
        try:
            request = CONTRACTS["get_book_details"].input_model.model_validate({"book_id": book_id})
            return canonical_json(store.get_book_details(request).model_dump(mode="json"))
        except (BookstoreError, ValidationError) as exc:
            raise ResourceNotFoundError("Book resource does not exist.") from exc

    def prompt_args(model, received_from, received_before, vendor_ids):
        try:
            values = [part.strip() for part in vendor_ids.split(",")]
            key = "vendor_ids" if model is CompareInput else "vendor_id"
            request = model.model_validate(
                {
                    key: values if key == "vendor_ids" else values[0],
                    "received_from": received_from,
                    "received_before": received_before,
                }
            )
            if key == "vendor_id" and len(values) != 1:
                raise ValueError("Exactly one vendor expected.")
            store.window(request.received_from, request.received_before)
            return request.model_dump(mode="json")
        except (ValidationError, ValueError) as exc:
            raise ValueError(
                "Use paired ISO dates and distinct canonical comma-separated vendor IDs."
            ) from exc

    @server.prompt(
        description="Review dated imports; load selected tool context before generating calls."
    )
    def review_imports(received_from: str, received_before: str, vendor_ids: str) -> str:
        args = prompt_args(
            CompareInput if "," in vendor_ids else VendorSummaryInput,
            received_from,
            received_before,
            vendor_ids,
        )
        return (
            "Review bookstore imports using get_books/list_stock_receipts as appropriate. "
            "Read bookstore://reference and hydrate selected execution/domain resources before "
            f"generating calls. Requested filters: {canonical_json(args)}. "
            "Load used tools' presentation policies before presenting results."
        )

    @server.prompt(
        description="Compare supplier volume over one common period, not supplier quality."
    )
    def compare_vendor_supply(received_from: str, received_before: str, vendor_ids: str) -> str:
        args = prompt_args(CompareInput, received_from, received_before, vendor_ids)
        return (
            "Compare supply using compare_vendors after loading its execution/domain resources "
            f"and bookstore://reference. Requested arguments: {canonical_json(args)}. "
            "Volume does not establish quality. Apply its presentation policy after results."
        )

    return server


def main():
    parser = argparse.ArgumentParser(description="Read-only bookstore MCP server")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = create_server()
    server.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=os.getenv("MCP_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*,[::1]:*").split(
                ","
            ),
            allowed_origins=os.getenv(
                "MCP_ALLOWED_ORIGINS", "http://127.0.0.1:*,http://localhost:*"
            ).split(","),
        ),
    )


if __name__ == "__main__":
    main()
