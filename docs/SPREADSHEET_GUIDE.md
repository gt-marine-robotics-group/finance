# Spreadsheet reference

[Start with the spreadsheet workflow in the README](../README.md#1-fill-in-the-shared-excel-sheet). This page is a reference for fields, formulas, and troubleshooting; SharePoint holds the master workbook.

## Tables and identifiers

| Sheet / Excel table | Meaning |
| --- | --- |
| `Bills` / `BillsT` | Proposed and approved bill items. Items in the same request share a `Bill Title` and, once assigned, a `Bill No.`. |
| `Ordering` / `OrderT` | Purchase items. Rows in the same order share an `Order ID`. |
| `Test` / `TestTable` | Optional backlog before items are assigned to a bill. |

These identifiers have different jobs:

| Identifier | Where it comes from | How to use it |
| --- | --- | --- |
| `Bill No.` | The relevant Engage budget request. | Record the actual request number on all of the bill's item rows. A number alone does not mean the bill is approved. |
| `Bill Item ID` | A formula in `Bills`. | Copy the displayed value into `Ordering` to link to that item. Do not construct an ID yourself or assume a particular format. |
| `Order ID` | The person preparing an order. | Use `YYMMDD_vendor_gtusername`, repeated on all rows in that order. |
| Engage line number | The item's location in the approved Engage bill. | Verify in Engage before using it on a purchase request. It is not the Excel row number. |

## Editable and calculated fields

Use column **names** to identify fields. Do not paste entire rows over an existing table: that can replace formulas with plain text or numbers.

### Bills

| Fields | Editing rule |
| --- | --- |
| `Bill Title`, `Item Name`, `Vendor`, `Description`, `Budget Section`, `Quantity`, `Cost`, `Link`, `Person Requesting` | Enter the proposed item details. Keep approved budget figures intact; record later price quotes in a separate comparison report. |
| `Bill No.`, `Status` | Update to reflect the actual Engage request and its stage. |
| `Bill Item ID` (A), `Total Cost` (K) | Formula columns. Do not overwrite. |
| Any other cell containing a formula | Preserve the formula, including summary or remaining-allocation fields. |

`Cost` is a unit or pack price; `Quantity` counts those same units or packs. Do not enter an extended total as the unit cost.

### Ordering

`OrderT` spans columns A–V. Row 1 contains summary totals, row 2 contains headers, and data starts at row 3.

| Columns / fields | Editing rule |
| --- | --- |
| A: `Order ID (YYMMDD_vendor_gburdell3)` | Enter the order's shared ID. |
| B: `Bill Item ID` | Copy the referenced item's ID from `Bills`. |
| H: `Quantity` | Enter the quantity to purchase. |
| `Purchaser`, `Status`, instructions and other non-formula input fields | Fill in the applicable tracking details. |
| C–G: `Bill No.`, `Bill Title`, `Item Name`, `Vendor`, `Cost` | Calculated from the source item. Do not overwrite. |
| I–J: `Total Cost`, `Allocation`; O: `Budget Section` | Calculated fields. Do not overwrite or replace with a current quote. |
| U: `Share-A-Cart Link`; V: `Engage Request Link` | Enter the order-level URL on **every row** with the same Order ID. |

The order quantity may differ from the bill quantity. Check remaining funding and previous orders before purchasing; the displayed allocation is not, by itself, approval to spend again.

## When a calculated field is wrong

1. Check the `Bill Item ID` in `Ordering` against the displayed ID in `Bills`. Remove accidental spaces and make sure the source item still exists.
2. Select the affected cell and check Excel's formula bar. If a formula has been replaced, undo your edit or ask the finance officer to restore the formula from a correct neighboring row or version history.
3. Recalculate and save in Excel. Python tools read saved formula results and do not calculate Excel formulas themselves.
4. If the input details are wrong, correct the source item with the finance officer. Do not patch a calculated `Ordering` cell by typing over it.

Use existing empty table rows. If there are no suitable rows with formulas, ask the workbook maintainer to extend the table and its formulas. Keep totals, separator rows, table names, and headers intact.

## What the CLI diagnostic checks

`mrg-finance doctor` checks workbook readability, the presence of the Bills sheet, duplicate bill-item IDs, missing item names or bill numbers, nonpositive costs, nonstandard nonempty links, and order references it can compare with bill IDs.

It does not verify funding approval, remaining spending authority, vendor availability, every formula, or live Engage line numbers. It also does not flag every missing product link. Review the source rows even when the diagnostic reports no issues.

For code that reads or writes the workbook, see [agents.md](agents.md) and [Development](DEVELOPMENT.md).
