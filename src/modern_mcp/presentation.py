"""Deterministic presentation fixtures for offline tests, not an LLM renderer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HostCapabilities:
    charts: bool = False
    resource_links: bool = False


def display_plan(result, policy, host=None, requested_format=None):
    host = host or HostCapabilities()
    if requested_format not in (None, "scalar", "detail", "table", "chart", "text"):
        raise ValueError("Unsupported requested display format.")
    data = result["data"]
    rows = data.get("points", data.get("items"))
    count = len(rows) if rows is not None else 1
    chosen = requested_format or policy["default_format"]
    if requested_format is None:
        if count == 1:
            chosen = (
                "scalar" if policy["default_format"] == "scalar" or "points" in data else "detail"
            )
        elif count == 0:
            chosen = "text"
        elif chosen in ("scalar", "detail"):
            chosen = "table"
    if chosen == "chart" and not host.charts:
        chosen = "table" if count > 1 else "text"
    uri = result["provenance"]["source_uri"]
    return {
        "format": chosen,
        "source": {"label": "Source", "uri": uri, "clickable": host.resource_links},
        "snapshot": result["provenance"]["as_of_date"],
        "period": data["applied_filters"],
        "page_notice": f"Showing {count} of {data['total_count']} matched rows."
        if "total_count" in data
        else None,
        "axis_labels": {"x": "Date", "y": "Sold units"}
        if "points" in data and chosen == "chart"
        else None,
        "required_facts": policy["required_facts"],
    }
