# Define bookstore tool boundaries and fixture semantics

Id: 03
Parent: ../map.md
Label: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: none

## Question

Which read-only tools provide distinct enough parameter, domain, and presentation behavior to test the experiment, and what are their exact input/output and fixture contracts?

User-approved tool surface: `get_books`, `get_book_details`, `list_stock_receipts`, `get_stock_availability`, `get_vendor_summary`, `get_sales_trends`, and `compare_vendors`. `get_books` returns catalog records, optionally matched through receipts; `list_stock_receipts` returns actual receipt events/quantities. The catalog has exactly 100 books; repeated deliveries of a book are distinct receipt events. Exact date, inventory, and sales semantics remain open.

Resolve date-window inclusivity, fixed as-of date/timezone for relative queries, multiple-vendor filters and genre semantics, ID versus human-name lookup, stable pagination/order, summary arithmetic, sales fixture provenance, empty results, invalid filters, and detail size. Define a distinct execution rule, domain rule, and presentation policy for each tool. Separate 100 data rows from tool-catalog size: data volume and retrieval discrimination are different experiments.

## Candidate distinctions to review

The seven tool names are approved. Their detailed contracts below remain proposals.

- `get_books`: bounded catalog list; execution instructions distinguish catalog rows from receipts and explain filter combination; domain knowledge explains unique book identity versus repeat deliveries; presentation shows a compact book list with applied filters and pagination notice.
- `get_book_details`: exact book ID; execution instructions prohibit guessing an ID and clarify not-found behavior; domain knowledge separates edition/ISBN from local book ID; presentation gives a concise titled detail view with labeled facts.
- `list_stock_receipts`: receipt-date window and optional vendor/book filters; execution instructions specify date boundaries and ordering; domain knowledge defines delivered quantities and repeat receipt events; presentation uses chronological receipt rows and labels any quantity totals distinctly from unique-book counts.
- `get_stock_availability`: book selection and explicit as-of snapshot; execution instructions distinguish current snapshot from unsupported historical queries; domain knowledge defines on-hand versus available units, with exact inventory accounting still to decide; presentation emphasizes low/unavailable stock and the snapshot date.
- `get_vendor_summary`: one vendor and date window; execution instructions define vendor IDs and aggregation window; domain knowledge separates receipt count, unique books, and units; presentation gives labeled vendor totals with the period and provenance.
- `get_sales_trends`: time window, grouping interval, and optional genre; execution instructions describe supported interval and metric choices; domain knowledge defines sales units and any revenue currency/refund rules before arithmetic is specified; presentation prefers a trend chart where the host supports it, otherwise a small chronological table, and labels axes/units.
- `compare_vendors`: explicit vendor selection and common date window; execution instructions require comparable periods and supported comparison metrics; domain knowledge warns that delivered quantities alone do not establish vendor quality; presentation aligns comparable metrics and limits conclusions to the returned evidence.

All tools must have purposeful, discriminative descriptions. Distinct policies must serve the returned data rather than introduce artificial formatting differences solely for the experiment.

## Comments

2026-09-26 — User accepted fixed fixture date 2026-09-26, Asia/Kolkata calendar interpretation, inclusive-start/exclusive-end windows, and previous-calendar-month meaning for "last month". User accepted received-minus-sold inventory and simple sales fixtures. Presentation must support scalar/short text, tables, hyperlinks to real references, and charts where supported.

## Answer

The [review-ready specification](../spec.md), sections 3–6, defines the seven approved read-only tools and exact fixture/input/output behavior. Catalog rows are distinct books, receipt rows are delivery events for a book, inventory is received minus sold, and relative periods use the accepted fixed calendar. Typed schemas, bounded outputs, same-receipt filter matching, pagination, and explicit unit/count distinctions make these contracts implementable. Concrete fixture counts, IDs, genres, units-only sales, and limits are documented author-selected defaults rather than attributed to the user.
