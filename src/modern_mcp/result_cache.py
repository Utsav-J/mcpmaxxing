"""Persistent five-minute business-result cache for this read-only MCP."""

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from modern_mcp.json_support import canonical_json

TTL = 300


class ResultCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, body TEXT, created REAL)"
            )
            db.commit()

    def get(self, key):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT body, created FROM results WHERE key = ?", (key,)).fetchone()
        if row and row[1] <= time.time() < row[1] + TTL:
            return json.loads(row[0]), row[1]
        return None

    def put(self, key, data):
        created = time.time()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DELETE FROM results WHERE created <= ?", (created - TTL,))
            db.execute(
                "INSERT OR REPLACE INTO results VALUES (?, ?, ?)",
                (key, canonical_json(data), created),
            )
            db.commit()
        return created
