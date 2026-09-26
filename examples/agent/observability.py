"""Flushed local Markdown + JSONL traces; no telemetry service or callback package."""

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter


def markdown(event):
    body = json.dumps(event, ensure_ascii=False, indent=2)
    return (
        f"## {event['sequence']}. {event['stage']} — {event['visibility']}\n\n"
        f"```json\n{body}\n```\n\n"
    )


class Trace:
    def __init__(self, directory, run_id):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.run_id, self.sequence, self.started = run_id, 0, perf_counter()
        self.markdown_path = directory / f"{run_id}.md"
        self.jsonl_path = directory / f"{run_id}.jsonl"

    def __enter__(self):
        self.md = self.markdown_path.open("x", encoding="utf-8")
        try:
            self.jsonl = self.jsonl_path.open("x", encoding="utf-8")
        except BaseException:
            self.md.close()
            raise
        self.md.write(f"# Agent context trace: {self.run_id}\n\n")
        return self

    def emit(self, event):
        self.sequence += 1
        event = {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": round((perf_counter() - self.started) * 1000, 2),
            **event,
        }
        # Snapshots must not retain references to graph state that later mutates.
        event = json.loads(
            json.dumps(
                event,
                ensure_ascii=False,
                default=lambda value: asdict(value) if is_dataclass(value) else str(value),
            )
        )
        self.jsonl.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.md.write(markdown(event))
        self.jsonl.flush()
        self.md.flush()
        return event

    def __exit__(self, *_):
        self.md.close()
        self.jsonl.close()
