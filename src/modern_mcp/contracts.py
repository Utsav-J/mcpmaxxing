"""The public tool identities and business schemas."""

from dataclasses import dataclass

from modern_mcp import models as m


@dataclass(frozen=True)
class Contract:
    name: str
    description: str
    input_model: type[m.Input]
    output_model: type[m.Model]


CONTRACTS = {
    c.name: c
    for c in (
        Contract(
            "get_books",
            "List catalog books, optionally filtered by genre and stock receipts "
            "from vendors during a date window.",
            m.GetBooksInput,
            m.BooksResult,
        ),
        Contract(
            "get_book_details",
            "Get catalog facts and lifetime fixture stock totals for one exact book ID.",
            m.BookDetailsInput,
            m.DetailsResult,
        ),
        Contract(
            "list_stock_receipts",
            "List dated vendor stock-receipt rows and received quantities, "
            "optionally filtered by books or genre.",
            m.ReceiptsInput,
            m.ReceiptsResult,
        ),
        Contract(
            "get_stock_availability",
            "Show available stock units at the fixture's current snapshot, "
            "optionally restricted to books, genre, or stock status.",
            m.StockInput,
            m.StockResult,
        ),
        Contract(
            "get_vendor_summary",
            "Summarize receipt rows, unique books, and units supplied "
            "by one vendor during a receipt-date window.",
            m.VendorSummaryInput,
            m.VendorResult,
        ),
        Contract(
            "get_sales_trends",
            "Summarize sold book units by calendar interval over a sale-date "
            "window, optionally filtered by genre.",
            m.SalesInput,
            m.SalesResult,
        ),
        Contract(
            "get_sales",
            "List individual sale records with book details and date-derived fields, "
            "optionally filtered by date, book, genre, and quantity.",
            m.SalesRecordsInput,
            m.SalesRecordsResult,
        ),
        Contract(
            "compare_vendors",
            "Compare receipt volume for two to four vendors over the same receipt-date window.",
            m.CompareInput,
            m.ComparisonResult,
        ),
    )
}
