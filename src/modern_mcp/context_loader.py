"""Validated local authoring files become immutable MCP resource documents."""

import hashlib
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import Field

from modern_mcp.contracts import CONTRACTS
from modern_mcp.json_support import canonical_json
from modern_mcp.models import Model

META_KEY = "modern_mcp/tool_context"
MAX_CONTEXT_BYTES = 32 * 1024
CATEGORIES = {
    "execution_instructions": "execution",
    "domain_knowledge": "domain",
    "presentation_policy": "presentation",
}


class Retrieval(Model):
    summary: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)
    example_queries: list[str] = Field(min_length=1)


class FileReference(Model):
    file: str


class AuthoringEntry(Model):
    retrieval: Retrieval
    execution_instructions: FileReference
    domain_knowledge: FileReference
    presentation_policy: FileReference


class AuthoringManifest(Model):
    schema_version: Literal[1]
    tools: dict[str, AuthoringEntry]


class ResourceReference(Model):
    uri: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mime_type: Literal["application/json"] = "application/json"


class ToolContext(Model):
    schema_version: Literal[1]
    retrieval: Retrieval
    execution_instructions: ResourceReference
    domain_knowledge: ResourceReference
    presentation_policy: ResourceReference


class ParameterRule(Model):
    parameter: str
    rules: list[str]
    examples: list[str]


class ExecutionBody(Model):
    purpose: str
    when_to_use: list[str]
    when_not_to_use: list[str]
    parameter_rules: list[ParameterRule]
    preconditions: list[str]


class DomainBody(Model):
    terms: dict[str, str]
    business_rules: list[str]
    examples: list[str]
    limitations: list[str]


class PresentationBody(Model):
    default_format: Literal["scalar", "detail", "table", "chart"]
    format_rules: list[str]
    required_facts: list[str]
    tone: str
    citation_rules: list[str]
    fallback_format: Literal["text"]
    user_format_precedence: bool


class ContextDocument(Model):
    schema_version: Literal[1]
    tool_name: str
    category: Literal["execution", "domain", "presentation"]
    body: ExecutionBody | DomainBody | PresentationBody

    def validate_identity(self, tool_name, category):
        expected_body = {
            "execution": ExecutionBody,
            "domain": DomainBody,
            "presentation": PresentationBody,
        }[category]
        if (
            self.tool_name != tool_name
            or self.category != category
            or not isinstance(self.body, expected_body)
        ):
            raise ValueError("Context document identity/body mismatch.")


class ContextCatalog:
    def __init__(self, root: Path | None = None):
        root = (root or Path(str(files("modern_mcp").joinpath("context")))).resolve()
        manifest = AuthoringManifest.model_validate_json((root / "tool_contexts.json").read_bytes())
        if set(manifest.tools) != set(CONTRACTS):
            raise ValueError("Context manifest must match the registered tools exactly.")
        self.metadata = {}
        self.resources = {}
        for name, entry in manifest.tools.items():
            references = {}
            for key, category in CATEGORIES.items():
                relative = Path(getattr(entry, key).file)
                target = (root / relative).resolve()
                if relative.is_absolute() or not target.is_relative_to(root):
                    raise ValueError("Context file escapes the packaged directory.")
                if target.stat().st_size > MAX_CONTEXT_BYTES:
                    raise ValueError("Context document exceeds 32 KiB.")
                document = ContextDocument.model_validate_json(target.read_bytes())
                document.validate_identity(name, category)
                text = canonical_json(document.model_dump(mode="json"))
                if len(text.encode()) > MAX_CONTEXT_BYTES:
                    raise ValueError("Canonical context exceeds 32 KiB.")
                sha = hashlib.sha256(text.encode()).hexdigest()
                uri = f"bookstore://context/v1/{name}/{category}/{sha}"
                self.resources[uri] = text
                references[key] = ResourceReference(uri=uri, sha256=sha)
            self.metadata[name] = ToolContext(
                schema_version=1, retrieval=entry.retrieval, **references
            )
