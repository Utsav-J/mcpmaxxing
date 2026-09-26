# Tool Context Registry

A bookstore experiment in selecting relevant tools and loading their supporting context only when needed.

## Language

**Retrieval metadata**:
Information used to find relevant tools. It is consumed by retrieval and never supplied to the agent's model.

**Execution instructions**:
Rules the model needs before deciding whether and how to call a tool, including parameter interpretation and formatting.

**Domain knowledge**:
Documentation, terminology, examples, and business rules needed to interpret a tool's domain correctly.

**Presentation policy**:
Rules for presenting a tool's results to the user, including format, tone, and citations.

**Tool context registry**:
The client's structured collection of tool definitions and their associated retrieval metadata, execution instructions, domain knowledge, and presentation policies.

**Book**:
A catalog item identified by a book ID. Repeated deliveries do not create additional catalog books.

**Stock receipt**:
A vendor delivery recorded with a receipt date and quantities of books received. In this experiment, importing books means receiving stock from vendors.
_Avoid_: Catalog import, new catalog record

**Vendor**:
A supplier from whom the bookstore receives stock.

**Sale**:
A recorded sale of a quantity of one book. Sales reduce the bookstore's stock.

**Stock**:
The units received minus the units sold. This experiment has no reservations, returns, or backorders, so available units equal on-hand units.

**Receipt window**:
A period selecting stock receipts by receipt date, including its start and excluding its end.

**Last month**:
The calendar month immediately before the reference date's month, rather than a rolling thirty-day period.
