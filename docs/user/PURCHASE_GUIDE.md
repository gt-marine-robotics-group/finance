# Purchase requests

Run `mrg-finance purchase --fresh --order <Order ID>` after the source bills have been approved and their bill numbers recorded in the master workbook. Omit `--fresh` to use your local copy. Pending rows are grouped by Order ID; use a separate order for each vendor.

The CLI shows the workbook path, approved allocation, current quote, shipping, tax, change from allocation, payee details, and absolute paths to all evidence. Review the generated comparison spreadsheet before filling Engage. The CLI prepares the form; you submit it manually.

## Choose a cart

```bash
# Use the default automated source (Amazon cart building is automatic)
mrg-finance purchase --order <Order ID>

# Use your personal account explicitly
mrg-finance purchase --order <Order ID> --cart-source personal

# Explicitly select the default source
mrg-finance purchase --order <Order ID> --cart-source automated
```

There is no cart-source selection prompt. Omitting `--cart-source` uses `automated`. Amazon attempts automatic cart building. For a DigiKey order, run the usual `mrg-finance purchase --order <Order ID>`: the CLI attempts product additions to an empty cart and keeps a persistent vendor Chrome profile. Complete any bot verification in that Chrome window, then press Enter to retry. Existing carts are retained to avoid duplicate additions; correct them to contain only the order's items. Unconfirmed additions prompt for manual completion in the same browser. The CLI automatically reads DigiKey cart products, quantities, unit prices, item totals, and its displayed subtotal. When its shipping/tax/total breakdown reconciles, those values are read too. If automatic reading fails, Chrome stays open for retry; type `manual` only if you want to enter the quote yourself. A readable cart with the wrong products or quantities must be corrected before proceeding. Other vendors use manual preparation. `--cart-source personal` skips automatic product additions.

Both cart modes use the same dedicated profile for each vendor. On macOS, Amazon uses `~/Library/Application Support/mrg-finance/chrome/amazon/` and DigiKey uses the sibling `digikey/` directory. Sign into the vendor in that window and install Share-A-Cart once there if needed. The profile retains the account and extensions even when you run from a different folder; it does not reuse your ordinary Chrome session. Existing `.mrg-finance-browser/` Amazon/personal and `digikey/` profiles are copied on first use, leaving the originals as backups. Close any old cart Chrome window before that migration. Automated Amazon reuses matching existing products and adds only absent products. Conflicting or unreadable carts pause additions for correction and verification instead of adding duplicates.

Include only the order's items in the active Amazon cart. The CLI checks the ASINs and quantities against the workbook, then uses the actual cart unit prices. Missing items, unrelated items, quantity limits, unreadable prices, and subtotal discrepancies stop the workflow. If a seller limits the quantity, correct the Ordering sheet or choose a substitute before rerunning. The CLI does not silently reduce workbook quantities.

Automated Amazon mode confirms the selected quantity, closes its dropdown, and moves focus away before clicking Add to Cart. It scrolls the button into view and retries blocked or replaced buttons. It declines optional protection-plan coverage only when a visible coverage dialog has one clearly labeled decline control, such as **No Thanks**. It waits for the dialog to close and the item to be confirmed. If a click stays blocked or the coverage choice is unclear, it saves a diagnostic under `cart_diagnostics/` and keeps the browser open for manual completion. Check whether the item was already added before adding it again; the complete cart must still pass item and quantity verification. DigiKey quantity entry uses the main Add to Cart area's control, excluding related-product quantity fields.

In automated Amazon mode, link creation through Share-A-Cart's undocumented website endpoint is best effort. If it fails, create a link with the extension. Personal mode always asks for a link made from the actual vendor cart; it does not synthesize a cart from spreadsheet quantities.

[DigiKey is supported by Share-A-Cart](https://share-a-cart.com/supported/digikey) through its Chrome extension. The sender needs the extension to create the link; the recipient needs it to load the items into DigiKey. Confirm the actual DigiKey cart, then create and paste its extension-generated link. The CLI does not call the Amazon cart endpoint for DigiKey. Other vendors use the same manual cart verification flow; their sharing method depends on vendor support.

If the extension is missing, leave the CLI waiting at the shared-link prompt. In the **vendor/cart Chrome window**, open a new tab and visit the [official Share-A-Cart Chrome listing](https://chromewebstore.google.com/detail/share-a-cart-%E2%80%93-easily-sha/hcjohblbkdgcoikaedjndgbcgcfoojmj). Choose **Add to Chrome**, then **Add extension**. Find/pin Share-A-Cart through the puzzle-piece menu, return to the cart tab, reload if needed, and select **Create Cart ID**. Paste its link/code into the terminal. Chrome does not allow extension installation in an incognito window; the separate Engage window is incognito. Installing in your ordinary Chrome profile does not install it in the CLI profile. Amazon and DigiKey cart profiles remember the extension across runs and working directories, including automated Amazon mode.

Amazon and DigiKey require a valid Share-A-Cart URL/code; blank or unrelated links prompt again, and `cancel` stops preparation. The CLI saves the accepted link into **Share-A-Cart Link** on every matching Ordering row in the printed workbook, then reads it back before preparing Engage. It also writes `screenshots/<Order ID>/share_a_cart.json` as a recovery copy. If saving fails, the browser stays open while you close Excel or fix the workbook and retry. Cancelling a failed save stops before Engage. OneDrive uploads local workbook changes when its client is connected; this local save is not proof of a completed cloud sync.

## Replace a product or change vendor

The current **Ordering Link** takes precedence over the original bill's link. The purchase vendor is detected from that URL, so a DigiKey replacement uses the DigiKey cart, sharing instructions, payee, and Engage subject even if the Order ID contains `amazon` or a vendor lookup still shows Amazon.

To switch before opening a cart, answer `y` at **Change product links before building the cart?**, select the item number, and paste its replacement HTTPS product URL. Press Enter at the item-number prompt when done.

The CLI checks all product-page prices against the approved **Bills Cost** before attempting any cart additions. If a price exceeds that baseline, **Enter substitute product URL** offers a replacement; press Enter to keep the current product. A different current Cost in Ordering does not replace the approved bill baseline. If the page is blocked or its price cannot be read, **Enter current unit price, or paste a replacement product URL** lets you replace it immediately or provide the vendor's displayed price. An unreadable price is never treated as approval to proceed at the budgeted price. The final cart is still verified, and a changed over-budget unit price prompts again.

Accepted replacements are saved immediately to the matching **Link** cells in Ordering in the workbook path printed by the CLI. The selected order's **Vendor** cells are updated, existing hyperlink targets are replaced, and its old Share-A-Cart link is cleared. Approved bill data, bill references, quantities, and allocation remain the comparison baseline. Close Excel before running the purchase so its open copy does not overwrite these saved changes. OneDrive syncs the edited file when it is in your synced folder and the client is connected.

The old cart browser closes and preparation restarts with the new product links. The new cart must pass verification before fees, sharing, reporting, or Engage preparation. A vendor change applies to the entire order: all its product links must identify the same vendor. Otherwise replace the remaining links or split the order in Ordering. If the workbook changes during a replacement save, the CLI reloads it and retries up to three times, preserving unrelated edits. If selected rows/columns changed during the run, the CLI stops the save and asks you to rerun with the latest workbook. Repeated changes also stop the save: close Excel, wait for OneDrive sync to finish, then rerun and paste the replacement again.

## Screenshots and CAPTCHAs

Screenshot capture waits for the rendered page and tries a full-page Chrome capture, with a viewport fallback. CAPTCHA, Cloudflare verification, or access-denied pages produce a terminal notification and diagnostic PNG/JSON under `screenshots/<Order ID>/challenges/`. These files are separate from quote attachments. Solve challenges in the visible browser and press Enter to retry, or type `cancel` to stop the purchase. If verification keeps failing, stop; the CLI cannot guarantee that a protected site will admit its automated browser. A challenge is never accepted as `cart.png`.

For bill product screenshots:

```bash
mrg-finance screenshots --bill "<Bill Title>"
mrg-finance screenshots --bill "<Bill Title>" --interactive
```

Default screenshot mode runs headlessly and records challenges for attention. `--interactive` shows Chrome and pauses for manual CAPTCHA solving. Screenshot commands and bill-request captures retain their profile under `.mrg-finance-browser/evidence/` in the working directory. A saved session may reduce repeat prompts, but a vendor can require verification again. Review `screenshots/<Bill Title>/screenshot_audit.csv` in your spreadsheet. The side-by-side review server and `review` command have been removed; `--no-review` remains an ignored compatibility flag.

Capture allows up to five seconds for a vendor's non-interactive browser check to finish naturally. Persistent challenges need manual solving. Each successful screenshot gets an `.evidence.json` sidecar with its source URL and image hash. Bill requests require this checked evidence for linked products before opening Engage and recheck it immediately before attachment upload. Legacy images without this record, changed URLs/files, and failed or cancelled captures must be recaptured. Failure markers prevent an older synced proof from being reused; keep the sidecars with the images. Detection covers known challenge text/widgets, so also review the screenshots visually.

## Reconcile the amount

The Engage request amount is the verified merchandise subtotal plus applicable shipping and tax. For DigiKey orders placed by Georgia Tech accountants, the CLI applies the institutional **free shipping** arrangement: requested shipping is $0 even if the public cart shows an estimate such as $8.49. It preserves the vendor’s displayed shipping/total and records the shipping basis separately in the comparison workbook. For example, $500 merchandise + $8.49 public-cart shipping becomes a $500 request when tax is $0. Tax and merchandise prices are not waived. DigiKey reads the vendor breakdown automatically when it reconciles; failed scraping never substitutes the approved allocation as a live quote. This shipping rule is for GT accountant fulfillment, not a personal checkout charge.

If you explicitly select manual quote entry for DigiKey, or use an unsupported vendor, enter the price for **one unit** of each product from the actual cart. The CLI displays quantity × unit price for every item, then asks for the cart's **items-only subtotal**, excluding shipping and tax. For example, five units at $100 each have a $500 item subtotal. If the $508 vendor total includes $8 shipping, enter $500 here and $8 at the later shipping prompt. Only do this when the vendor shows that breakdown. A subtotal mismatch keeps Chrome open: press Enter to correct the subtotal, type `prices` to correct the unit prices, or type `cancel` to stop. Changing prices requires another funding/replacement review when applicable.

When charge entry is required, shipping and tax accept Enter for zero when the vendor shows no charge. The final total requires an explicit amount; the displayed **expected** amount is a calculation to compare with the vendor, not a default. Blank or malformed amounts re-prompt without closing the browser. If the final total differs from subtotal plus fees, correct the shipping/tax and total in the same session, or type `cancel` if merchandise prices changed. Amount prompts accept `cancel` to stop. Before upload, a changed verified amount still stops the request and requires a refreshed quote.

The CLI creates one request for that full amount. It no longer submits the allocation as a primary request and adds a separate overflow request. Price increases are displayed as a variance; confirm that the order has sufficient approved funding before continuing. Approved unit costs remain the baseline in the comparison report.

Immediately before uploading attachments, the CLI refreshes automatically read Amazon and DigiKey carts and checks every item, quantity, unit price, and subtotal against the reviewed quote. DigiKey merchandise and tax are rechecked automatically when available; its public shipping estimate is recorded separately under the GT free-shipping arrangement. Changed payable quotes stop the upload. Manually entered and unsupported carts require reconfirmation. Amazon shipping/tax and the final checkout total still require confirmation because its cart subtotal does not include all checkout charges. The CLI then reads the actual Engage Amount field and requires it to equal the verified payable amount, including the recorded GT shipping adjustment for DigiKey. If prices changed, rerun to rebuild the quote, report, and shared cart.

## Engage fields and payee

After GT sign-in and Duo MFA, the CLI looks up each item's line number and section on the approved Engage budget or bill. The live request title identifies annual budget funding, with the workbook title as a fallback. If a lookup fails, enter the verified Engage line and section. Excel Bill Item IDs are not used as Engage line numbers. Nonzero shipping and tax also require funding references. A blank reference re-prompts with both Chrome windows open; type `cancel` to stop. DigiKey’s waived shipping skips this prompt.

Select the Category/Account and the prompted SGA Budget or SGA Bill funding option in Engage. The CLI checks the selected checkbox and fills its own write-in answer; an unchecked funding option is left untouched. An order funded by both sources can fill both selected options. The CLI matches controls through labels, ARIA references, or a local question container and checks that values were retained:

Multiple item references use semicolons in single-line answers and line breaks in text areas. The CLI does not send Enter keys into single-line fields, which could submit an incomplete form. Controls are re-found during filling and before reading the requested amount, so form updates do not reuse stale element references. Brief control replacement is retried automatically; persistent errors still pause in the same Chrome window.

| Field | Content |
| --- | --- |
| Subject | `Marine Robotics Group <Vendor> Purchase Request <Date>` |
| Requested Amount | Full verified vendor total, including shipping/tax |
| Description | Share-A-Cart link |
| What is the Budget/Bill # and Request Line #? | Verified Budget or Bill number, section, and Engage line references |
| SGA Budget / SGA Bill | Quoted amounts and verified references in the matching selected funding option |
| Payee | Vendor name across native First/Last Name fields, separate Street/City/State/ZIP fields, and available vendor email; combined payee fields are also supported |

Amazon and DigiKey payee defaults are based on [Amazon's official contact address](https://shipping.amazon.com/privacy-notice) and [DigiKey's contact information](https://www.digikey.com/en/help/browser-support). Review the payee against your seller/invoice, especially for marketplace purchases. Other vendors are checked on their official homepage and contact pages for structured organization/address data. Missing required contact information or ambiguous form controls stop the upload for manual review; no details are moved into Description. Payee selection has no extra CLI options. The separate Payee Email question receives the verified vendor email (DigiKey: `orders@digikey.com`) and the CLI checks that it was retained. A known email is not silently skipped when field lookup fails; the form remains open for retry. If no verified vendor email is available, existing manual email input is preserved.

Missing fields, incorrect funding selections, and amount-verification errors pause with both Chrome windows open. Correct the current page and press Enter to retry the failed step; subject, shared-cart link, and browser sessions are retained. Type `cancel` to stop explicitly. Other unexpected form-stage errors wait for you to inspect or finish the form before ending the run. Inspect `engage_form_error.png` and `engage_fields.json` in the order's evidence folder. These diagnostics identify visible controls without exporting entered form values.

## Reports and submission

The verified cart quote automatically fills the comparison workbook and CSV before GT credentials are requested. A Cart Reconciliation tab includes merchandise, shipping, tax, displayed total, and whether the vendor labels charges as estimated. The preview shows each item's spreadsheet budget section; Engage line numbers remain pending until lookup. Verified Engage sections replace spreadsheet sections in the completed report. Close the workbook before continuing so these references can be updated. Quote prices are written to this comparison workbook; the approved workbook remains the budget baseline. Product and shared-cart links still save to Ordering.

At **Continue to Engage with this verified amount? [Y/n]**, Enter opens/fills Engage and completes the funding references; `n` stops with the comparison workbook saved. Final request submission remains manual.

For approved-bill references, the CLI opens the bill, expands **Menu**, selects **Budget**, and waits for numbered items. It reads each section’s displayed line number, which differs from the Excel Bill Item ID. If lookup fails, Chrome remains open; open Menu → Budget and press Enter to retry, or type `manual` to enter verified references. Manual entry accepts `B03 Line 1` in one answer, or `1` followed by `B03`. Typing errors are retried without closing the browser. Lookup diagnostics are saved under `screenshots/<Order ID>/engage_diagnostics/`.

Evidence is stored under `screenshots/<Order ID>/`:

- `cart.png`: freshly verified vendor cart.
- `Budget_vs_Quoted_Detail_<Order ID>.xlsx`: approved versus quoted prices and verified bill references, plus a Cart Reconciliation tab recording fees, vendor total, Engage amount, and payee source.
- `Budget_vs_Quoted_Detail_<Order ID>.csv`: merchandise comparison for spreadsheet review.

The screenshot and Excel report are uploaded only after the field and total checks pass. Review the form, complete any remaining required fields, sign, and submit in Engage. Paste the resulting Engage URL if it cannot be detected. The CLI writes cart and request links to every matching Ordering row and reports whether SharePoint synchronization succeeded.

To regenerate an offline comparison without opening Engage, run `mrg-finance report --order <Order ID>`. Offline reports may use allocation fallbacks; they do not count as verified purchase quotes.

Standalone reports take the category from the linked Bills row's **Budget Section**, with Ordering as a fallback. They do not invent an Engage line number from the Excel Bill Item ID or report row position: an unavailable line is labeled **Unverified line** until a purchase lookup supplies it.
