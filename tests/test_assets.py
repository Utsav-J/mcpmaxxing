import json
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from modern_mcp.bookstore import Bookstore
from modern_mcp.context_loader import load_context_catalog
from modern_mcp.json_support import digest
from modern_mcp.models import Fixture
from scripts.generate_fixtures import build_fixture


def test_fixture_generation_matches_committed_asset():
    asset = json.loads(files("modern_mcp").joinpath("fixtures/bookstore.json").read_text("utf-8"))
    assert build_fixture() == asset


def test_negative_stock_and_bad_digest_are_rejected():
    raw = build_fixture()
    raw["sales"][0]["quantity"] = 1000
    with pytest.raises(ValueError, match="digest"):
        Bookstore(Fixture.model_validate(raw))
    raw["manifest"]["sha256"] = digest(
        {key: value for key, value in raw.items() if key != "manifest"}
    )
    with pytest.raises(ValueError, match="exceed"):
        Bookstore(Fixture.model_validate(raw))


@pytest.mark.parametrize("failure", ["missing", "escape", "category", "oversized"])
def test_context_authoring_failures_stop_startup(tmp_path, failure):
    root = tmp_path / "context"
    shutil.copytree(Path(str(files("modern_mcp").joinpath("context"))), root)
    manifest_path = root / "tool_contexts.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if failure == "missing":
        manifest["tools"]["get_books"]["domain_knowledge"]["file"] = "missing.json"
    elif failure == "escape":
        manifest["tools"]["get_books"]["domain_knowledge"]["file"] = "../outside.json"
    elif failure == "category":
        path = root / "get_books/domain.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["tool_name"] = "get_sales_trends"
        path.write_text(json.dumps(doc), encoding="utf-8")
    else:
        path = root / "get_books/domain.json"
        path.write_text(" " * 32769, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        load_context_catalog(root)
