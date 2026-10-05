# MRG Finance video recording runbook

This walkthrough follows the current v0.2.11 CLI. Record an 8–12 minute main video covering installation, a funding bill, and a purchase against an approved bill. Put developer tests, offline usage, and the full rclone setup in separate chapters or companion videos.

## Before recording

Prepare these two examples:

- **Funding example:** a small real bill with two or three items in the Bills sheet, with product links, quantities, costs, and budget sections. Have its existing editable Engage budget-request draft ready. The CLI uses `Bill No.` to open that draft, or asks for its Engage edit URL when the number is blank.
- **Purchase example:** a separate pending order referencing an already approved bill, with the official bill number and quantities recorded in Ordering. Use one vendor per Order ID. Have the actual Engage line numbers and funding references for any shipping/tax ready.

Explain the approval gap on camera: submitting a new funding bill does not immediately make it available for purchasing. Switch to the already approved example for the purchase segment.

Rehearse once before recording. The new purchase flow has passed offline simulations and a synthetic Chrome form test; the authenticated Engage form still needs a real-order smoke test. Check that its Category/Account, SGA questions, payee fields, and attachment controls appear as expected.

Use an authorized real request when demonstrating Engage. `bill-request` saves line items and attachments into the live draft. `purchase` builds carts, writes cart links to the workbook, and uploads evidence before you manually submit. There is no CLI dry-run mode. Omitting `--fresh` skips the initial download; screenshot and purchase flows can still attempt SharePoint uploads when rclone is configured.

Keep terminal text readable at 16–18 pt. Show Terminal and the workbook/browser together, then zoom into the current task. Pause or crop GT/Amazon sign-in and MFA; keep account menus, addresses, payment details, and notification popups out of the recording. Record short clips so waiting for pages and authentication can be cut out.

Do not delete your working repository, virtual environment, or rclone configuration for the main video. A separate recording directory or computer user account gives you a clean setup without losing your normal environment.

## 1. Installation — about one minute

Have uv, Google Chrome, Git, and access to the finance workbook ready. If uv itself is part of the lesson, record its installation as a short separate clip using the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

For a published version, the end-user command is:

```bash
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
mrg-finance --help
```

If the executable is not on PATH, run `uv tool update-shell` and reopen the terminal. See [uv's tools guide](https://docs.astral.sh/uv/guides/tools/).

**For recording the current local changes:** they are still uncommitted at the time this guide was written. A new clone or GitHub installation will not include those changes until they are published. Install from the current checkout instead:

```bash
uv tool install --force .
mrg-finance --help
mrg-finance purchase --help
```

Show `--cart-source {automated,personal}` in purchase help to establish that you are using the updated tool. Use `uv tool list` to show the installed version.

**Say:** “uv installs the CLI in its own environment. The workbook contains our purchasing data, and the CLI helps prepare the evidence and Engage forms.”

Do not describe a local-checkout installation as the GitHub one-liner. Choose the clip matching the code you actually installed.

## 2. Workbook and diagnostics — about one minute

Place `FY27_Bills_Budget.xlsx` in the recording's working directory. Show the Bills and Ordering tabs and explain:

- Bills holds the funding items and approved costs.
- Ordering selects Bill Item IDs and the quantities being purchased now.
- Bill Item IDs are spreadsheet identifiers; Engage has its own line numbers.
- Formulas should remain intact. Enter only the editable fields.

For a custom file path, set it explicitly rather than depending on auto-discovery:

```bash
export FINANCE_XLSX_PATH="/absolute/path/to/FY27_Bills_Budget.xlsx"
mrg-finance doctor
```

In PowerShell, use `$env:FINANCE_XLSX_PATH = "C:\path\FY27_Bills_Budget.xlsx"`.

The environment override takes priority in the CLI; otherwise it checks the current directory, the fixed `~/mrg/finance/` location, and the configured macOS OneDrive location. An arbitrary cloned repository directory is not automatically a fallback when you run from somewhere else.

Show warnings such as missing bill numbers, nonpositive costs, duplicate IDs, or unresolved Ordering references. A missing official bill number can be expected for a new funding draft. Do not call this proof that every formula is correct or that a vendor URL is reachable; doctor checks workbook data and basic URL formatting.

**Say:** “Doctor catches common workbook problems before we prepare a request.”

## 3. Funding bill — about two to three minutes

Replace every quoted placeholder below with a bill title or Order ID that exists in your workbook.

First show the small funding example in Bills. Capture its product evidence:

```bash
mrg-finance screenshots --bill "<FUNDING_BILL_TITLE>" --interactive
```

Show one product page, the saved screenshot, and `screenshots/<Bill Title>/screenshot_audit.csv` in Excel. Keep the spreadsheet cost consistent with the intended funding request. The audit records scraped prices; it does not overwrite the approved/requested workbook costs.

If a CAPTCHA appears naturally, show the notification and the separate `challenges/` diagnostic folder, then solve it in Chrome and retry. Do not rely on a CAPTCHA occurring during the live recording. A previous diagnostic clip can illustrate this feature if labeled as a separate example.

Then run:

```bash
mrg-finance bill-request --bill "<FUNDING_BILL_TITLE>"
```

Show these steps:

1. Select the prepared draft through its bill number, or paste its Engage edit URL when prompted. This command fills an existing draft; it does not create the initial draft shell.
2. Review the screenshot audit. Existing screenshots can be reused; capture missing evidence if prompted.
3. Review the per-section item list and total, then confirm Proceed.
4. Cut around GT credentials and Duo MFA.
5. Show the automation entering one line's name, description, quantity, cost, and screenshot, then saving it.
6. Show the final added/skipped/failed counts and review the resulting draft in Engage. The CLI's completion message reports line-item entry, not SGA approval.
7. Complete the draft's final submission in Engage when appropriate for the real request. Later, record the official approved bill number in the workbook.

**Say:** “Bill-request puts our funding items and quote evidence into the Engage draft. Approval happens afterward; for the purchase demonstration, I'll switch to an already approved bill.”

## 4. Purchase — about four to five minutes

Show the prepared pending order in Ordering. Use personal mode as the main demonstration because it shows the real account's cart and Share-A-Cart contents:

```bash
mrg-finance purchase --order "<APPROVED_ORDER_ID>" --cart-source personal
```

Explain the alternative briefly: omitting `--cart-source personal` attempts automated Amazon cart building. Both modes verify the real cart before proceeding.

Record these moments in order:

1. **Select and prepare:** show the pending order, allocation, workbook path, and evidence directory. Confirm the order and cart-preparation prompts.
2. **Personal browser:** sign into Amazon in the Chrome window opened by the CLI. This is a dedicated profile under `.mrg-finance-browser/` in the working directory, not your already open browser. Install Share-A-Cart there before the main take if needed. Cut around sign-in.
3. **Actual cart:** build the order using only its listed items. Check seller limits and quantities. Return to the cart page and press Enter in the terminal when ready. The CLI compares the active cart's ASINs and quantities with Ordering and reads its prices/subtotal.
4. **Charges:** enter shipping and tax as shown by the vendor, then enter the final total. Do not treat “not yet calculated” as zero. This total must match merchandise plus shipping and tax to the cent.
5. **Sharing:** create a Share-A-Cart link with the extension from that actual cart and paste it into the terminal.
6. **Quote review:** show approved versus cart unit prices, the total including fees, the variance from allocation, and vendor payee details. Confirm sufficient funding and continue to Engage.
7. **Bill references:** after GT authentication, show the approved-bill lookup. If a match fails, enter the verified Engage line and section. Provide funding references for shipping/tax if prompted.
8. **Spreadsheet:** open the generated comparison workbook from the printed path. Show the line-item budget, quote, variance, section, and bill/line references. Close the report before pressing Enter to continue; the CLI updates it again during upload.
9. **Engage questions:** when prompted, select the funding Category/Account and SGA Bill option in Engage to reveal the custom questions, then return to Terminal and press Enter.
10. **Final check:** show the CLI rechecking the cart and asking you to reconfirm the vendor total immediately before uploading.
11. **Filled form:** zoom into the fields below and the two uploaded attachments. After upload, reopen the report if you want to show its Cart Reconciliation tab, which is added at this stage.
12. **Finish:** review/sign/submit the real request manually in Engage, return to Terminal, and confirm the submitted URL. Show the cart and request links recorded in Ordering and the SharePoint sync result. If you only recorded form preparation, stop the clip before submission and label it “prepared draft”; do not claim a submitted request.

| Show in Engage | What the viewer should see |
| --- | --- |
| Requested Amount | Verified full vendor total, including shipping/tax |
| Description | Share-A-Cart link |
| Budget/Bill # and Request Line # | Verified Engage bill/line/section references |
| SGA Bill | Quoted amount per funding line, plus allocated fees |
| Payee | Vendor name and available official contact details |
| Attachments | `cart.png` and the comparison `.xlsx` |

**Say:** “An approved price is our baseline, but the purchase request uses the current vendor total. We verify the actual cart, keep the comparison spreadsheet, and check the amount again before uploading to Engage.”

If quantities or prices change, show the stop message and explain that the order/quote needs correction and rerunning. Do not present a seller quantity limit as something Share-A-Cart can override.

## 5. Optional feature clips

Choose one or two for the main video; put the rest in separate chapters.

| Feature | Command or shot | Accurate explanation |
| --- | --- | --- |
| Price audit | `mrg-finance price-check --bill "<BILL_TITLE>"` | Headless Chrome price comparison and an Amazon add-to-cart URL. Missing prices fall back to allocations in the summary, so this is an estimate, not a verified purchase quote. |
| Standalone report | `mrg-finance report --order "<ORDER_ID>"` | Formatted line-item comparison with subtotal/grand-total formulas; prices may fall back to the baseline. Do not promise executive KPI cards that this generator does not create. |
| CAPTCHA handling | `mrg-finance screenshots --bill "<BILL_TITLE>" --interactive` | Visible Chrome, retry after manual solving, and diagnostic screenshots kept separate from evidence. |
| DigiKey | Show a real DigiKey cart and extension-generated link | [Share-A-Cart supports DigiKey](https://share-a-cart.com/supported/digikey). Both parties need the Everything extension; DigiKey quote prices and quantities are manually confirmed by this CLI. |
| Cloud refresh | `mrg-finance doctor --fresh` | Downloads before checking the workbook; the detailed rclone setup belongs in a separate clip. |

Run a standalone `report` demonstration **before** purchase, or use a different order. It writes the same report filenames and can overwrite a purchase's verified report with a freshly scraped or fallback report. Likewise, the price-check add-to-cart link can add extra items to a browser cart; keep it separate from the cart you will verify in purchase.

## Main-video timeline

These are edited-screen-time targets. Record authentication, page loads, and full automation separately and shorten the waits in editing.

| Time | Segment |
| --- | --- |
| 0:00–0:20 | What the tool does: funding bill → approval → purchase |
| 0:20–1:20 | Installation and CLI help |
| 1:20–2:10 | Workbook fields and doctor |
| 2:10–4:40 | Product screenshots and funding bill draft |
| 4:40–9:10 | Personal cart, verified quote, report, Engage fields and attachments |
| 9:10–9:40 | Submitted-request link and workbook logging |
| 9:40–10:20 | One optional feature and where to find the guides |

For a four-minute overview, use short clips from these recordings. Treat it as a feature overview rather than a complete follow-along tutorial.

## Companion clip: developer installation and tests

After the current changes are published:

```bash
git clone https://github.com/gt-marine-robotics-group/finance.git
cd finance
uv sync
uv run mrg-finance --help
uv run pytest -q
```

Before publication, use the existing updated checkout. At the time of writing, the normal test run reports **53 passed, 1 skipped**. The skipped test is an opt-in local Chrome DOM test. Timing varies. Describe these as offline simulations/regression checks, not actual Engage submissions.

Once dependencies are installed and cached, `uv run --offline pytest -q` avoids dependency downloads. Global CLI installation alone does not give you the repository's test files; run tests from a checkout.

## Companion clip: manual and offline usage

Show downloading the workbook from SharePoint and running commands without `--fresh`. rclone is optional for loading a local workbook. For a recording copy, use a separate directory and set `FINANCE_XLSX_PATH` to that file; only use read-only diagnostics/reports during an offline rehearsal.

Offline workflow: edit the workbook → run doctor → review a baseline report → reconnect to obtain verified prices and prepare Engage. Standalone report generation attempts live price requests and falls back if unavailable; don't promise instantaneous offline runs. Installing dependencies from scratch needs internet or a prepared cache. Live screenshots, cart verification, vendor discovery, and Engage require internet.

There is no `review` command or side-by-side review server in v0.2.11. Review the workbook, screenshot audit CSV, and generated comparison workbook instead.

## Companion clip: rclone connection

Use the [official OneDrive/SharePoint setup documentation](https://rclone.org/onedrive/). Run `rclone config`, create a remote named `onedrive` (the CLI expects that name), select OneDrive storage, leave client credentials blank for the usual setup, authenticate with your GT account, and select the SharePoint site and Documents library. Prompt wording and available site-selection choices can vary with rclone version and tenant permissions; show the choices actually displayed rather than promising identical numbered prompts.

Site: `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`

```bash
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
rclone copy --ignore-checksum --ignore-size --update "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx" .
mrg-finance doctor --fresh
```

Pause recording before the configuration summary, which can contain tokens. Use a separate recording configuration/account if you need to film a fresh login; keep the working remote intact.

See [Purchase requests](PURCHASE_GUIDE.md), [Bill requests](BILL_REQUEST_GUIDE.md), and [CLI usage](CLI_GUIDE.md) for the full command references.
