"""Public endpoint metadata caches; deliberately independent of server code."""

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

TTL = 300


class Cache:
    def __init__(self, path, namespace, observe=lambda event: None):
        self.path, self.namespace, self.observe = Path(path), namespace, observe
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS entries (namespace TEXT, key TEXT, body TEXT, "
                "created REAL, PRIMARY KEY(namespace, key))"
            )
            db.commit()

    def get(self, key):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT body, created FROM entries WHERE namespace = ? AND key = ?",
                (self.namespace, key),
            ).fetchone()
        hit = bool(row and row[1] <= time.time() < row[1] + TTL)
        self.observe(
            {
                "stage": "cache",
                "visibility": "host_only",
                "key": key,
                "status": "hit" if hit else "miss",
                "ttl_seconds": TTL,
            }
        )
        return json.loads(row[0]) if hit else None

    def put(self, key, value):
        created = time.time()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DELETE FROM entries WHERE created <= ?", (created - TTL,))
            db.execute(
                "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?)",
                (self.namespace, key, json.dumps(value, ensure_ascii=False), created),
            )
            db.commit()
