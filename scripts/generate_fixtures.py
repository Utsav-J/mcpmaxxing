"""Regenerate the committed demo fixture, without network access or randomness."""

import hashlib
import json
from pathlib import Path


def build_fixture() -> dict:
    genres = ["fiction", "science-fiction", "fantasy", "history", "science", "business"]
    vendors = {f"VENDOR-{letter}": f"Vendor {letter}" for letter in "ABCD"}
    books = [
        {
            "book_id": f"B{i:03}",
            "title": f"{genres[(i - 1) % 6].title()} Book {i:03}",
            "author": f"Author {(i - 1) % 20 + 1:02}",
            "genre": genres[(i - 1) % 6],
        }
        for i in range(1, 101)
    ]
    receipts, sales = [], []

    def receive(book, vendor, day, units):
        receipts.append(
            {
                "receipt_id": f"R{len(receipts) + 1:04}",
                "book_id": book,
                "vendor_id": vendor,
                "received_date": day,
                "quantity": units,
            }
        )

    def sell(book, day, units):
        sales.append(
            {
                "sale_id": f"S{len(sales) + 1:04}",
                "book_id": book,
                "sold_date": day,
                "quantity": units,
            }
        )

    receive("B001", "VENDOR-A", "2026-07-31", 8)
    receive("B001", "VENDOR-B", "2026-08-01", 5)
    receive("B001", "VENDOR-A", "2026-09-01", 7)
    sell("B001", "2026-08-02", 3)
    receive("B002", "VENDOR-A", "2026-03-01", 5)
    sell("B002", "2026-03-02", 5)
    receive("B003", "VENDOR-A", "2026-03-01", 5)
    sell("B003", "2026-03-02", 2)
    for i in range(4, 100):
        book = f"B{i:03}"
        for slot, (day, units) in enumerate(
            [("2026-03-01", 20), ("2026-06-01", 10), ("2026-08-15", 5)]
        ):
            receive(book, list(vendors)[(i + slot) % 4], day, units)
        sell(book, "2026-03-02", 5)
        sell(book, "2026-08-20", 2)
    for i in range(10, 17):
        receive(f"B{i:03}", "VENDOR-D", "2026-08-31", 3)
    for i in range(10, 15):
        sell(f"B{i:03}", "2026-09-26", 1)
    assert len(books) == 100 and len(receipts) == 300 and len(sales) == 200
    data = {"vendors": vendors, "books": books, "receipts": receipts, "sales": sales}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "manifest": {
            "dataset_id": "bookstore-demo-v1",
            "revision": "1",
            "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "coverage_start": "2026-03-01",
            "as_of_date": "2026-09-26",
            "timezone": "Asia/Kolkata",
        },
        **data,
    }


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "src/modern_mcp/fixtures/bookstore.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_fixture(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
