# Engage form reference

Follow the [README workflow](../README.md#1-fill-in-the-shared-excel-sheet) to prepare the workbook. This page provides submission details for people filling in Engage manually or completing fields left by the CLI.

The field names below reflect the forms targeted by this repository. Follow the required fields shown in the live form if the wording changes.

## Budget request details

Open [MRG Budgeting](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting), sign in with your GT account and Duo, and create or open the intended draft.

| Form area | What to enter or verify |
| --- | --- |
| Request header | Organization: Marine Robotics Group; the intended fiscal year; the same title used in `Bills`. |
| Budget section | The item's `Budget Section`, such as B03 or B06. Confirm the category with the finance officer if unsure. |
| Item | Name, purpose/description, quantity, and unit cost from `Bills`. |
| Quote attachment | A product screenshot showing the item, price, and unit or pack size. |
| Final review | Each intended item appears once; quantities, evidence, and total match the workbook. |

Save each item, complete any remaining required questions, and submit. Record the actual request number and status on every item row in that bill. Update the status again when the approval decision arrives.

The bill CLI needs an existing draft: if there is no `Bill No.` in the workbook, it prompts for the draft's full edit-page URL. Copy it from your browser; do not guess the number.

## Purchase request details

Open [Create Purchase Request](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest).

| Field | What to enter |
| --- | --- |
| Subject | For example, `Marine Robotics Group Amazon Purchase Request 2026-09-10`. Use the actual vendor and date. |
| Requested amount | The amount being requested, reconciled with the cart and comparison report. Resolve shipping, tax, or price differences with the finance officer. |
| Description | Order context and the Share-A-Cart link, if available. |
| Category / Account | The category and funding account confirmed for this purchase. |
| Budget/Bill # and Request Line # | Each item's verified reference in the approved Engage bill, for example `Bill 344042, Line 34`. |
| SGA bill breakdown | The requested amount per line, bill number, and budget section. For example, `$49.95, Line 34, Bill 344042, B06 - Non-Inventoried Items`. |
| Signature | Your full name, as requested by the form. |

Example numbers are illustrative. Check line references against the approved bill in Engage; never substitute an Excel row number. If automation used the Description box as a fallback, copy the information into the required fields and check that the cart link is still present.

### Cart evidence

Build the cart on the vendor's website with the exact products, variants, and quantities. Capture all items and the total in readable screenshots. For use with the CLI, save the cart image as `screenshots/<Order ID>/cart.png` in your working folder.

A cart link and a cart screenshot serve different purposes. Keep the screenshot even if a Share-A-Cart link is available. Verify that a shared link reproduces the intended items and quantities before passing it on.

### Budget vs Quoted comparison

Create a separate workbook for the comparison, even when the quoted prices match the budget. Include these columns:

| Column | Meaning |
| --- | --- |
| Item / bill / section / line | Product and its verified reference in the approved Engage bill. |
| Approved unit cost / quantity / total | The approved basis for the items being requested. |
| Quoted unit cost / quantity / total | The current vendor quote for those items. |
| Difference | Quoted total minus approved total; a positive value means an overrun. |

For each side, extended total = unit cost × quantity. Sum item totals once, and identify shipping or tax separately. Make the report and request amount agree with the funding arrangement confirmed by the finance officer.

The optional [report command](CLI_GUIDE.md#other-commands) creates this workbook, but you must verify its prices and line references before attaching it. If scraping fails, a report can contain budget prices as fallback values.

### Attach and finish

Attach the cart screenshot and Budget vs Quoted workbook, then complete any other documents or fields requested by the live form. Review, sign, and click Submit.

After the confirmation page appears, copy its URL into `Engage Request Link` on every `Ordering` row for the order. Put any cart link into `Share-A-Cart Link` on those same rows. Update the order status, wait for approval, and coordinate the actual purchase with the finance officer.
