"""Public business contracts; these models also supply the MCP input/output schemas."""

import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Genre = Literal["fiction", "science-fiction", "fantasy", "history", "science", "business"]
GENRES = ("fiction", "science-fiction", "fantasy", "history", "science", "business")
BookId = Annotated[str, Field(pattern=r"^B\d{3}$", description="Exact local book ID, e.g. B001.")]
VendorId = Literal["VENDOR-A", "VENDOR-B", "VENDOR-C", "VENDOR-D"]
VendorIds = Annotated[list[VendorId], Field(min_length=1, max_length=4)]
BookIds = Annotated[list[BookId], Field(min_length=1, max_length=100)]
StockStatus = Literal["out_of_stock", "low_stock", "in_stock"]
Interval = Literal["day", "week", "month"]


def iso_date(value: object) -> object:
    if isinstance(value, date) and type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Dates must be ISO YYYY-MM-DD strings.")
    return value


IsoDate = Annotated[date, BeforeValidator(iso_date)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Input(Model):
    @model_validator(mode="after")
    def distinct_ids(self) -> Self:
        for name in ("book_ids", "vendor_ids"):
            values = getattr(self, name, None)
            if values is not None and len(values) != len(set(values)):
                raise ValueError(f"{name} must contain distinct IDs.")
        return self


class ReceiptWindow(Input):
    received_from: IsoDate | None = Field(
        None, description="Inclusive receipt date; paired with end."
    )
    received_before: IsoDate | None = Field(
        None, description="Exclusive receipt date; paired with start."
    )


class Pagination(Input):
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = Field(
        20, description="Page size, 1–50."
    )
    cursor: str | None = Field(
        None, max_length=2048, description="Opaque cursor from the same query."
    )


class GetBooksInput(ReceiptWindow, Pagination):
    genre: Genre | None = Field(None, description="One canonical genre; null means all genres.")
    vendor_ids: VendorIds | None = Field(
        None, description="Vendor IDs matched on the SAME receipt."
    )


class BookDetailsInput(Input):
    book_id: BookId


class ReceiptsInput(GetBooksInput):
    book_ids: BookIds | None = Field(None, description="Exact catalog IDs; OR within this list.")


class StockInput(Pagination):
    book_ids: BookIds | None = Field(None, description="Known catalog IDs, or null for all.")
    genre: Genre | None = None
    stock_status: Literal["all", "out_of_stock", "low_stock", "in_stock"] = Field(
        "all", description="Snapshot status: 0 units, 1–5 units, or more than 5 units."
    )


class VendorSummaryInput(ReceiptWindow):
    vendor_id: VendorId


class SalesInput(Input):
    sold_from: IsoDate | None = Field(None, description="Inclusive SALE date; paired with end.")
    sold_before: IsoDate | None = Field(None, description="Exclusive SALE date; paired with start.")
    interval: Interval = Field("month", description="Calendar grouping; weeks start Monday.")
    genre: Genre | None = None


class CompareInput(ReceiptWindow):
    vendor_ids: Annotated[list[VendorId], Field(min_length=2, max_length=4)]


class Book(Model):
    book_id: BookId
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    genre: Genre


class Receipt(Model):
    receipt_id: str
    book_id: BookId
    vendor_id: VendorId
    received_date: IsoDate
    quantity: int = Field(strict=True, gt=0)


class Sale(Model):
    sale_id: str
    book_id: BookId
    sold_date: IsoDate
    quantity: int = Field(strict=True, gt=0)


class FixtureManifest(Model):
    dataset_id: str
    revision: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    coverage_start: IsoDate
    as_of_date: IsoDate
    timezone: Literal["Asia/Kolkata"]


class Fixture(Model):
    manifest: FixtureManifest
    vendors: dict[str, str]
    books: list[Book]
    receipts: list[Receipt]
    sales: list[Sale]


class Provenance(Model):
    dataset_id: str
    revision: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of_date: date
    timezone: str
    source_uri: str
    coverage_start: date
    coverage_before: date


class AppliedFilters(Model):
    genre: Genre | None = None
    vendor_ids: list[VendorId] | None = None
    book_ids: list[BookId] | None = None
    received_from: date | None = None
    received_before: date | None = None
    sold_from: date | None = None
    sold_before: date | None = None
    stock_status: str | None = None
    interval: Interval | None = None


class Payload(Model):
    applied_filters: AppliedFilters
    warnings: list[str] = Field(default_factory=list)


class Page[T](Payload):
    items: list[T]
    total_count: int
    next_cursor: str | None


class CatalogRow(Book):
    matched_received_units: int | None


class BookDetails(Book, Payload):
    vendor_ids: list[VendorId]
    total_received_units: int
    total_sold_units: int
    stock_units: int


class ReceiptRow(Receipt):
    title: str


class ReceiptPage(Page[ReceiptRow]):
    receipt_count: int
    received_units: int
    unique_book_count: int


class StockRow(Model):
    book_id: BookId
    title: str
    genre: Genre
    stock_units: int
    stock_status: StockStatus


class SupplyTotals(Model):
    receipt_count: int
    unique_book_count: int
    received_units: int


class GenreTotals(SupplyTotals):
    genre: Genre


class VendorTotals(SupplyTotals):
    vendor_id: VendorId
    vendor_name: str


class VendorSummary(VendorTotals, Payload):
    genre_breakdown: list[GenreTotals]


class Comparison(Payload):
    items: list[VendorTotals]
    metric_definitions: dict[str, str]


class SalesPoint(Model):
    period_start: date
    period_before: date
    sold_units: int


class SalesTrends(Payload):
    points: list[SalesPoint] = Field(max_length=210)
    total_sold_units: int
    interval: Interval
    units: Literal["sold units"] = "sold units"


class Result[T](Model):
    data: T
    provenance: Provenance


BooksResult = Result[Page[CatalogRow]]
DetailsResult = Result[BookDetails]
ReceiptsResult = Result[ReceiptPage]
StockResult = Result[Page[StockRow]]
VendorResult = Result[VendorSummary]
SalesResult = Result[SalesTrends]
ComparisonResult = Result[Comparison]
