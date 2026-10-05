# Purchase requests

Run `mrg-finance purchase --fresh --order <Order ID>` after the source bills have been approved and their bill numbers recorded in the master workbook. Omit `--fresh` to use your local copy. Pending rows are grouped by Order ID; use a separate order for each vendor.

The CLI shows the workbook path, approved allocation, current quote, shipping, tax, change from allocation, payee details, and absolute paths to all evidence. Review the generated comparison spreadsheet before filling Engage. The CLI prepares the form; you submit it manually.

## Choose a cart

```bash
# Build an Amazon cart in a temporary Chrome session
mrg-finance purchase --order <Order ID>

# Sign into your personal account and create Share-A-Cart from the real cart
mrg-finance purchase --order <Order ID> --cart-source personal
```

Personal mode opens a dedicated Chrome profile at `.mrg-finance-browser/` in your current directory. Sign into Amazon in that window, build the order, and install Share-A-Cart there if necessary. The profile remembers the account and extensions. It does not reuse an already open Chrome session. The profile is ignored by Git.

Include only the order's items in the active Amazon cart. The CLI checks the ASINs and quantities against the workbook, then uses the actual cart unit prices. Missing items, unrelated items, quantity limits, unreadable prices, and subtotal discrepancies stop the workflow. If a seller limits the quantity, correct the Ordering sheet or choose a substitute before rerunning. The CLI does not silently reduce workbook quantities.

In automated Amazon mode, link creation through Share-A-Cart's undocumented website endpoint is best effort. If it fails, create a link with the extension. Personal mode always asks for a link made from the actual vendor cart; it does not synthesize a cart from spreadsheet quantities.

[DigiKey is supported by Share-A-Cart](https://share-a-cart.com/supported/digikey) through its Everything extension. Both the sender and recipient need the extension for DigiKey. Build the DigiKey cart in the open browser, confirm each quoted unit price and the cart quantities, and paste the extension-generated link. The CLI does not call the Amazon cart endpoint for DigiKey. Other vendors use the same manual cart verification flow; their sharing method depends on vendor support.

## Screenshots and CAPTCHAs

Screenshot capture waits for the rendered page and tries a full-page Chrome capture, with a viewport fallback. CAPTCHA or access-denied pages produce a terminal notification and diagnostic PNG/JSON under `screenshots/<Order ID>/challenges/`. These files are separate from quote attachments. Solve challenges in the visible browser and retry, or skip and stop the purchase. A challenge is never accepted as `cart.png`.

For bill product screenshots:

```bash
mrg-finance screenshots --bill "<Bill Title>"
mrg-finance screenshots --bill "<Bill Title>" --interactive
```

Default screenshot mode runs headlessly and records challenges for attention. `--interactive` shows Chrome and pauses for manual CAPTCHA solving. Review `screenshots/<Bill Title>/screenshot_audit.csv` in your spreadsheet. The side-by-side review server and `review` command have been removed; `--no-review` remains an ignored compatibility flag.

## Reconcile the amount

The Engage request amount is the verified merchandise subtotal plus the shipping and tax shown by the vendor. Enter those fees and the final vendor total when prompted. All totals must agree to the cent; failed scraping never substitutes the approved allocation as a live quote.

The CLI creates one request for that full amount. It no longer submits the allocation as a primary request and adds a separate overflow request. Price increases are displayed as a variance; confirm that the order has sufficient approved funding before continuing. Approved unit costs remain the baseline in the comparison report.

Immediately before uploading attachments, the CLI refreshes Amazon and checks that every item, quantity, unit price, and subtotal still agrees with the reviewed cart. For other vendors it asks you to reconfirm the quantities and subtotal. Shipping/tax and the final vendor total require manual confirmation because Amazon's cart subtotal does not include all checkout charges. The CLI then reads the actual Engage Amount field and requires it to equal the verified vendor total. If prices changed, rerun to rebuild the quote, report, and shared cart.

## Engage fields and payee

After GT sign-in and Duo MFA, the CLI looks up each item's line number and section on the approved Engage bill. If a lookup fails, enter the verified Engage line and section. Excel Bill Item IDs are not used as Engage line numbers. Shipping and tax also require funding references.

Select the Category/Account and SGA Bill funding option in Engage when prompted, so conditional questions are visible. The CLI matches controls through labels, ARIA references, or a local question container and checks that values were retained:

| Field | Content |
| --- | --- |
| Subject | `Marine Robotics Group <Vendor> Purchase Request <Date>` |
| Requested Amount | Full verified vendor total, including shipping/tax |
| Description | Share-A-Cart link |
| What is the Budget/Bill # and Request Line #? | Verified bill, section, and Engage line references |
| SGA Bill | Quoted dollar amount for each bill/line/section, including allocated fees |
| Payee | Vendor name and available official contact information |

Amazon and DigiKey payee defaults are based on [Amazon's official contact address](https://shipping.amazon.com/privacy-notice) and [DigiKey's contact information](https://www.digikey.com/en/help/browser-support). Review the payee against your seller/invoice, especially for marketplace purchases. Other vendors are checked on their official homepage and contact pages for structured organization/address data. Missing required contact information or ambiguous form controls stop the upload for manual review; no details are moved into Description. Payee selection has no extra CLI options.

On a form error, inspect `engage_form_error.png` and `engage_fields.json` in the order's evidence folder. These diagnostics identify visible controls without exporting entered form values.

## Reports and submission

Evidence is stored under `screenshots/<Order ID>/`:

- `cart.png`: freshly verified vendor cart.
- `Budget_vs_Quoted_Detail_<Order ID>.xlsx`: approved versus quoted prices and verified bill references, plus a Cart Reconciliation tab recording fees, vendor total, Engage amount, and payee source.
- `Budget_vs_Quoted_Detail_<Order ID>.csv`: merchandise comparison for spreadsheet review.

The screenshot and Excel report are uploaded only after the field and total checks pass. Review the form, complete any remaining required fields, sign, and submit in Engage. Paste the resulting Engage URL if it cannot be detected. The CLI writes cart and request links to every matching Ordering row and reports whether SharePoint synchronization succeeded.

To regenerate an offline comparison without opening Engage, run `mrg-finance report --order <Order ID>`. Offline reports may use allocation fallbacks; they do not count as verified purchase quotes.
