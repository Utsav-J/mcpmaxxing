"""Read-only fixture operations, independent of MCP and model integration."""

import base64
import json
from collections import defaultdict
from datetime import date, timedelta
from importlib.resources import files

from modern_mcp.json_support import canonical_json, digest
from modern_mcp.models import (
    GENRES,
    AppliedFilters,
    BookDetails,
    BooksResult,
    CatalogRow,
    CompareInput,
    Comparison,
    ComparisonResult,
    DetailsResult,
    Fixture,
    GenreTotals,
    GetBooksInput,
    Page,
    Provenance,
    ReceiptPage,
    ReceiptRow,
    ReceiptsInput,
    ReceiptsResult,
    SalesInput,
    SalesPoint,
    SalesResult,
    SalesTrends,
    StockInput,
    StockResult,
    StockRow,
    VendorResult,
    VendorSummary,
    VendorSummaryInput,
    VendorTotals,
)


class BookstoreError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class Bookstore:
    def __init__(self, fixture: Fixture | None = None):
        raw = json.loads(files("modern_mcp").joinpath("fixtures/bookstore.json").read_text("utf-8"))
        self.fixture = fixture or Fixture.model_validate(raw)
        self.manifest = self.fixture.manifest
        data = self.fixture.model_dump(mode="json", exclude={"manifest"})
        if digest(data) != self.manifest.sha256:
            raise ValueError("Fixture content digest mismatch.")
        self.books = {book.book_id: book for book in self.fixture.books}
        if len(self.books) != 100 or len(self.fixture.books) != 100:
            raise ValueError("Fixture must contain exactly 100 unique books.")
        if set(self.fixture.vendors) != {f"VENDOR-{c}" for c in "ABCD"}:
            raise ValueError("Fixture must contain the four documented vendors.")
        self.before = self.manifest.as_of_date + timedelta(days=1)
        self.receipts = tuple(
            sorted(self.fixture.receipts, key=lambda r: (r.received_date, r.receipt_id))
        )
        self.sales = tuple(sorted(self.fixture.sales, key=lambda s: (s.sold_date, s.sale_id)))
        if len(self.receipts) != 300 or len(self.sales) != 200:
            raise ValueError("Fixture requires 300 receipts and 200 sales.")
        self.receipts_by_book = defaultdict(list)
        self.sold_by_book = defaultdict(int)
        events = []
        for r in self.receipts:
            self._book(r.book_id)
            self.window(r.received_date, r.received_date + timedelta(days=1))
            self.receipts_by_book[r.book_id].append(r)
            events.append((r.received_date, 0, r.book_id, r.quantity))
        for s in self.sales:
            self._book(s.book_id)
            self.window(s.sold_date, s.sold_date + timedelta(days=1))
            self.sold_by_book[s.book_id] += s.quantity
            events.append((s.sold_date, 1, s.book_id, -s.quantity))
        for rows, key in ((self.receipts, "receipt_id"), (self.sales, "sale_id")):
            if len({getattr(row, key) for row in rows}) != len(rows):
                raise ValueError(f"Duplicate {key}.")
        self.stock = defaultdict(int)
        for _, _, book_id, quantity in sorted(events):
            self.stock[book_id] += quantity
            if self.stock[book_id] < 0:
                raise ValueError("Fixture sales exceed received stock.")

    def _book(self, book_id):
        if book_id not in self.books:
            raise BookstoreError("UNKNOWN_ID", "Book ID does not exist in this catalog.")
        return self.books[book_id]

    def _validate_books(self, book_ids):
        for book_id in book_ids or []:
            self._book(book_id)

    def window(self, start, before):
        if (start is None) != (before is None):
            raise BookstoreError("INVALID_ARGUMENT", "Provide both date bounds or neither.")
        start = start or self.manifest.coverage_start
        before = before or self.before
        if start >= before:
            raise BookstoreError("INVALID_ARGUMENT", "Start must precede exclusive end.")
        if start < self.manifest.coverage_start or before > self.before:
            raise BookstoreError("UNSUPPORTED_WINDOW", "Requested dates exceed fixture coverage.")
        return start, before

    def provenance(self, start=None, before=None, source=None):
        return Provenance(
            dataset_id=self.manifest.dataset_id,
            revision=self.manifest.revision,
            sha256=self.manifest.sha256,
            as_of_date=self.manifest.as_of_date,
            timezone=self.manifest.timezone,
            source_uri=source or "bookstore://fixtures/bookstore-demo-v1",
            coverage_start=start or self.manifest.coverage_start,
            coverage_before=before or self.before,
        )

    def reference(self):
        return {
            "manifest": self.manifest.model_dump(mode="json"),
            "coverage_before": self.before.isoformat(),
            "vendors": self.fixture.vendors,
            "genres": list(GENRES),
            "calendar_rules": (
                "Start inclusive; end exclusive. Last month is the previous calendar month."
            ),
            "stock_rule": (
                "Received units minus sold units; no reservations, returns, or backorders."
            ),
        }

    def fixture_descriptor(self):
        return {**self.reference(), "counts": {"books": 100, "receipts": 300, "sales": 200}}

    def _receipt_matches(self, start, before, vendor_ids=None, book_ids=None, genre=None):
        self._validate_books(book_ids)
        return [
            r
            for r in self.receipts
            if start <= r.received_date < before
            and (vendor_ids is None or r.vendor_id in vendor_ids)
            and (book_ids is None or r.book_id in book_ids)
            and (genre is None or self.books[r.book_id].genre == genre)
        ]

    def _page(self, name, rows, request, filters):
        binding = digest(
            {
                "dataset": self.manifest.sha256,
                "tool": name,
                "filters": filters.model_dump(mode="json"),
                "limit": request.limit,
            }
        )
        offset = 0
        if request.cursor is not None:
            try:
                raw = base64.b64decode(request.cursor, altchars=b"-_", validate=True)
                token = json.loads(raw)
                offset = token["offset"]
                if (
                    set(token) != {"binding", "offset"}
                    or token["binding"] != binding
                    or type(offset) is not int
                    or not 0 < offset < len(rows)
                    or offset % request.limit
                ):
                    raise ValueError("Invalid cursor binding or offset.")
            except (ValueError, KeyError, TypeError) as exc:
                raise BookstoreError(
                    "INVALID_CURSOR", "Cursor does not belong to this page query."
                ) from exc
        end = offset + request.limit
        next_cursor = None
        if end < len(rows):
            next_cursor = base64.urlsafe_b64encode(
                canonical_json({"binding": binding, "offset": end}).encode()
            ).decode()
        return {
            "items": rows[offset:end],
            "total_count": len(rows),
            "next_cursor": next_cursor,
            "applied_filters": filters,
        }

    def get_books(self, q: GetBooksInput) -> BooksResult:
        start, before = self.window(q.received_from, q.received_before)
        filtered = q.vendor_ids is not None or q.received_from is not None
        received = defaultdict(int)
        for r in self._receipt_matches(start, before, q.vendor_ids, genre=q.genre):
            received[r.book_id] += r.quantity
        rows = [
            CatalogRow(
                **book.model_dump(),
                matched_received_units=received[book.book_id] if filtered else None,
            )
            for book in sorted(self.books.values(), key=lambda b: b.book_id)
            if (q.genre is None or book.genre == q.genre)
            and (not filtered or book.book_id in received)
        ]
        filters = AppliedFilters(
            genre=q.genre,
            vendor_ids=sorted(q.vendor_ids) if q.vendor_ids else None,
            received_from=start if filtered else None,
            received_before=before if filtered else None,
        )
        return BooksResult(
            data=Page[CatalogRow](**self._page("get_books", rows, q, filters)),
            provenance=self.provenance(start, before),
        )

    def get_book_details(self, q) -> DetailsResult:
        book = self._book(q.book_id)
        receipts = self.receipts_by_book[q.book_id]
        data = BookDetails(
            **book.model_dump(),
            applied_filters=AppliedFilters(book_ids=[q.book_id]),
            vendor_ids=sorted({r.vendor_id for r in receipts}),
            total_received_units=sum(r.quantity for r in receipts),
            total_sold_units=self.sold_by_book[q.book_id],
            stock_units=self.stock[q.book_id],
        )
        return DetailsResult(
            data=data, provenance=self.provenance(source=f"bookstore://books/{q.book_id}")
        )

    def list_stock_receipts(self, q: ReceiptsInput) -> ReceiptsResult:
        start, before = self.window(q.received_from, q.received_before)
        receipts = self._receipt_matches(start, before, q.vendor_ids, q.book_ids, q.genre)
        rows = [ReceiptRow(**r.model_dump(), title=self.books[r.book_id].title) for r in receipts]
        filters = AppliedFilters(
            genre=q.genre,
            vendor_ids=sorted(q.vendor_ids) if q.vendor_ids else None,
            book_ids=sorted(q.book_ids) if q.book_ids else None,
            received_from=start,
            received_before=before,
        )
        data = ReceiptPage(
            **self._page("list_stock_receipts", rows, q, filters),
            receipt_count=len(rows),
            received_units=sum(r.quantity for r in receipts),
            unique_book_count=len({r.book_id for r in receipts}),
        )
        return ReceiptsResult(data=data, provenance=self.provenance(start, before))

    @staticmethod
    def stock_status(units):
        return "out_of_stock" if units == 0 else "low_stock" if units <= 5 else "in_stock"

    def get_stock_availability(self, q: StockInput) -> StockResult:
        self._validate_books(q.book_ids)
        rows = [
            StockRow(
                book_id=b.book_id,
                title=b.title,
                genre=b.genre,
                stock_units=self.stock[b.book_id],
                stock_status=self.stock_status(self.stock[b.book_id]),
            )
            for b in sorted(self.books.values(), key=lambda b: b.book_id)
            if (q.book_ids is None or b.book_id in q.book_ids)
            and (q.genre is None or b.genre == q.genre)
            and (
                q.stock_status == "all"
                or self.stock_status(self.stock[b.book_id]) == q.stock_status
            )
        ]
        filters = AppliedFilters(
            book_ids=sorted(q.book_ids) if q.book_ids else None,
            genre=q.genre,
            stock_status=q.stock_status,
        )
        return StockResult(
            data=Page[StockRow](**self._page("get_stock_availability", rows, q, filters)),
            provenance=self.provenance(),
        )

    def _totals(self, rows) -> dict[str, int]:
        return {
            "receipt_count": len(rows),
            "received_units": sum(r.quantity for r in rows),
            "unique_book_count": len({r.book_id for r in rows}),
        }

    def get_vendor_summary(self, q: VendorSummaryInput) -> VendorResult:
        start, before = self.window(q.received_from, q.received_before)
        rows = self._receipt_matches(start, before, [q.vendor_id])
        breakdown = [
            GenreTotals(
                genre=g, **self._totals([r for r in rows if self.books[r.book_id].genre == g])
            )
            for g in GENRES
        ]
        data = VendorSummary(
            vendor_id=q.vendor_id,
            vendor_name=self.fixture.vendors[q.vendor_id],
            **self._totals(rows),
            genre_breakdown=breakdown,
            applied_filters=AppliedFilters(
                vendor_ids=[q.vendor_id], received_from=start, received_before=before
            ),
        )
        return VendorResult(data=data, provenance=self.provenance(start, before))

    def compare_vendors(self, q: CompareInput) -> ComparisonResult:
        start, before = self.window(q.received_from, q.received_before)
        items = [
            VendorTotals(
                vendor_id=v,
                vendor_name=self.fixture.vendors[v],
                **self._totals(self._receipt_matches(start, before, [v])),
            )
            for v in sorted(q.vendor_ids)
        ]
        data = Comparison(
            items=items,
            applied_filters=AppliedFilters(
                vendor_ids=sorted(q.vendor_ids), received_from=start, received_before=before
            ),
            metric_definitions={
                "receipt_count": "Receipt rows, not shipment invoices.",
                "unique_book_count": "Distinct books within each vendor.",
                "received_units": "Delivered units, not remaining stock.",
            },
        )
        return ComparisonResult(data=data, provenance=self.provenance(start, before))

    def get_sales_trends(self, q: SalesInput) -> SalesResult:
        start, before = self.window(q.sold_from, q.sold_before)
        sold = defaultdict(int)
        for s in self.sales:
            if start <= s.sold_date < before and (
                q.genre is None or self.books[s.book_id].genre == q.genre
            ):
                sold[s.sold_date] += s.quantity
        points = []
        current = start
        while current < before:
            if q.interval == "day":
                end = current + timedelta(days=1)
            elif q.interval == "week":
                end = current + timedelta(days=7 - current.weekday())
            else:
                end = date(current.year + current.month // 12, current.month % 12 + 1, 1)
            end = min(end, before)
            points.append(
                SalesPoint(
                    period_start=current,
                    period_before=end,
                    sold_units=sum(units for day, units in sold.items() if current <= day < end),
                )
            )
            current = end
        data = SalesTrends(
            points=points,
            total_sold_units=sum(sold.values()),
            interval=q.interval,
            applied_filters=AppliedFilters(
                sold_from=start, sold_before=before, interval=q.interval, genre=q.genre
            ),
        )
        return SalesResult(data=data, provenance=self.provenance(start, before))
