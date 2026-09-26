import pytest

from modern_mcp.bookstore import BookstoreError
from modern_mcp.models import (
    BookDetailsInput,
    CompareInput,
    GetBooksInput,
    ReceiptsInput,
    SalesInput,
    StockInput,
    VendorSummaryInput,
)


def test_golden_book_stock_and_unsupplied_catalog(store):
    detail = store.get_book_details(BookDetailsInput(book_id="B001")).data
    assert (detail.total_received_units, detail.total_sold_units, detail.stock_units) == (20, 3, 17)
    assert detail.vendor_ids == ["VENDOR-A", "VENDOR-B"]
    stock = store.get_stock_availability(StockInput(book_ids=["B002", "B003", "B100"])).data.items
    assert [(row.book_id, row.stock_units, row.stock_status) for row in stock] == [
        ("B002", 0, "out_of_stock"),
        ("B003", 3, "low_stock"),
        ("B100", 0, "out_of_stock"),
    ]
    assert store.get_books(GetBooksInput()).data.total_count == 100


def test_same_receipt_matches_vendor_and_date_and_bounds(store):
    q = dict(received_from="2026-08-01", received_before="2026-09-01", genre="fiction")
    rows_a = store.get_books(GetBooksInput(**q, vendor_ids=["VENDOR-A"], limit=50)).data.items
    rows_b = store.get_books(GetBooksInput(**q, vendor_ids=["VENDOR-B"], limit=50)).data.items
    assert "B001" not in [row.book_id for row in rows_a]
    assert next(row for row in rows_b if row.book_id == "B001").matched_received_units == 5
    receipts = store.list_stock_receipts(ReceiptsInput(**q, book_ids=["B001"])).data
    assert [(row.received_date.isoformat(), row.quantity) for row in receipts.items] == [
        ("2026-08-01", 5)
    ]
    assert (receipts.receipt_count, receipts.received_units, receipts.unique_book_count) == (
        1,
        5,
        1,
    )


def test_all_pages_no_gaps_and_filter_binding(store):
    cursor, ids = None, []
    while True:
        page = store.get_books(GetBooksInput(limit=7, cursor=cursor)).data
        ids.extend(row.book_id for row in page.items)
        assert page.total_count == 100
        cursor = page.next_cursor
        if not cursor:
            break
    assert ids == [f"B{i:03}" for i in range(1, 101)]
    cursor = store.get_books(GetBooksInput(limit=7)).data.next_cursor
    with pytest.raises(BookstoreError, match="INVALID_CURSOR"):
        store.get_books(GetBooksInput(limit=8, cursor=cursor))
    with pytest.raises(BookstoreError, match="INVALID_CURSOR"):
        store.get_books(GetBooksInput(limit=7, genre="history", cursor=cursor))


@pytest.mark.parametrize("cursor", ["", "not base64!", "e30=", "bnVsbA==", "W10="])
def test_malformed_cursor_is_explicit_error(store, cursor):
    with pytest.raises(BookstoreError, match="INVALID_CURSOR"):
        store.get_books(GetBooksInput(cursor=cursor))


def test_totals_are_full_match_not_first_page(store):
    page = store.list_stock_receipts(ReceiptsInput(limit=1)).data
    assert len(page.items) == 1
    assert page.total_count == page.receipt_count == 300
    assert page.unique_book_count == 99
    assert page.received_units == 3411
    summary = store.get_vendor_summary(VendorSummaryInput(vendor_id="VENDOR-A")).data
    assert sum(g.received_units for g in summary.genre_breakdown) == summary.received_units
    assert sum(g.receipt_count for g in summary.genre_breakdown) == summary.receipt_count


def test_sales_empty_buckets_clipping_and_conservation(store):
    april = store.get_sales_trends(
        SalesInput(sold_from="2026-04-01", sold_before="2026-05-01", interval="day")
    ).data
    assert len(april.points) == 30
    assert all(point.sold_units == 0 for point in april.points)
    august = store.get_sales_trends(
        SalesInput(sold_from="2026-08-01", sold_before="2026-09-01", interval="week")
    ).data
    assert august.points[0].period_start.isoformat() == "2026-08-01"
    assert august.points[0].period_before.isoformat() == "2026-08-03"
    assert august.points[-1].period_before.isoformat() == "2026-09-01"
    assert sum(point.sold_units for point in august.points) == august.total_sold_units == 195
    assert len(store.get_sales_trends(SalesInput(interval="day")).data.points) == 210


def test_zero_supply_rows_and_successful_empty_result(store):
    comparison = store.compare_vendors(
        CompareInput(
            vendor_ids=["VENDOR-C", "VENDOR-A"],
            received_from="2026-04-01",
            received_before="2026-05-01",
        )
    ).data
    assert [row.vendor_id for row in comparison.items] == ["VENDOR-A", "VENDOR-C"]
    assert all(row.received_units == 0 for row in comparison.items)
    assert (
        store.get_books(
            GetBooksInput(received_from="2026-04-01", received_before="2026-05-01")
        ).data.total_count
        == 0
    )


@pytest.mark.parametrize(
    "bounds,code",
    [
        ({"received_from": "2026-08-01"}, "INVALID_ARGUMENT"),
        ({"received_from": "2026-08-01", "received_before": "2026-08-01"}, "INVALID_ARGUMENT"),
        ({"received_from": "2026-02-01", "received_before": "2026-08-01"}, "UNSUPPORTED_WINDOW"),
    ],
)
def test_unsupported_windows(store, bounds, code):
    with pytest.raises(BookstoreError, match=code):
        store.get_books(GetBooksInput(**bounds))
