# MRG Finance

**Start with Excel. The command-line tool is optional.**

A **budget request** (or **bill**) asks SGA to approve funding. A **purchase request** uses approved funding to arrange an order. Neither submits an order to a vendor.

## 1. Fill in the shared Excel sheet

Open [FY27_Bills_Budget.xlsx on SharePoint](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap) with your GT account. Edit in your browser and wait for changes to save. Ask the finance officer for access if needed.

| | Request funding | Prepare an approved purchase |
| --- | --- | --- |
| Sheet | `Bills` | `Ordering` |
| One row per… | Product you want funded. | Product you want to order. |
| Group rows with… | The same `Bill Title`. | The same `Order ID`, e.g. `260910_amazon_gburdell3` = date, vendor, your GT username. Use a separate order for each vendor. |
| You fill in… | `Bill Title`, `Item Name`, `Vendor`, `Description`, `Budget Section`, `Quantity`, `Cost`, `Link`, `Person Requesting`. | `Order ID`, `Bill Item ID` copied exactly from `Bills`, `Quantity`, `Purchaser`, `Status`. |
| Excel fills in… | `Bill Item ID` and `Total Cost`. | Bill number/title, item name, vendor, cost, total cost, allocation, and budget section. **Do not type into these fields.** |

Use empty rows inside the existing tables. In `Ordering`, headings are on row 2 and data starts on row 3. Enter the price of **one unit or pack** in `Cost`: quantity 3 × cost $12.50 = total $37.50. Ask the finance officer which budget section to use if unsure.

For funding, save a product screenshot showing the item, price, and pack size. For purchases, confirm approval and remaining funding, build the vendor cart, and check quantities and current prices. Resolve price differences with the finance officer; keep the approved budget figures intact.

**After submission:** record the actual `Bill No.` and status on the bill's rows. For an order, put the submitted URL in `Engage Request Link` (V) and any cart link in `Share-A-Cart Link` (U) on **every row with that Order ID**. Update status as approval, ordering, and delivery progress.

### Submit manually — no installation needed

| Request | Where to go | What to do |
| --- | --- | --- |
| Budget / bill | [MRG Budgeting in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting) | Create/open a draft with the same bill title and correct fiscal year. Add each item under its budget section with quantity, unit cost, and quote screenshot. Check the total, then submit. |
| Purchase | [Create Purchase Request in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest) | Enter the order amount, funding account/category, and approved bill/line references. Attach the cart screenshot and a separate Budget vs Quoted spreadsheet, complete the required fields, sign, and submit. |

Sign in with GT credentials and Duo. An Engage line number must be checked on the approved bill; it is not an Excel row number. After purchase-request approval, coordinate actual ordering with the finance officer.

<details>
<summary>What goes in the screenshots and price comparison?</summary>

Save evidence in the shared finance folder under `screenshots/<Bill Title>/<Item Name>.png` for product quotes and `screenshots/<Order ID>/cart.png` for carts. Replace the placeholders with the actual title, item, or order ID. Screenshots should show the correct variant, pack size, price, and quantities.

Make a separate Budget vs Quoted workbook with one row per item: item name, approved Engage bill/section/line, approved unit price and quantity, current quoted unit price and quantity, both totals, and their difference. Include it even when prices match. Identify shipping and tax separately and confirm how they will be funded. A cart link does not replace the screenshot.

If a calculated Excel field is blank or wrong, check the copied `Bill Item ID`, then recalculate and save in Excel. Do not type over the formula; ask the finance officer to help restore it or extend the table when needed.

For complete field rules, see the [Spreadsheet Guide](docs/SPREADSHEET_GUIDE.md) and [Engage Form Reference](docs/MANUAL_WORKFLOW.md).

</details>

## 2. Optional: install the command-line tool

The CLI prepares screenshots, reports, and Engage forms. **You still review and click Submit yourself.** Use Terminal on macOS/Linux or PowerShell on Windows.

<details>
<summary>First-time installation and SharePoint connection</summary>

You need [Git](https://git-scm.com/downloads) and access to this GitHub repository. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), which manages Python and the tool.

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Reopen your terminal, then run:

```text
uv tool install --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
uv tool update-shell
```

Reopen the terminal again and run `mrg-finance --help`. You should see the available commands.

Install [rclone](https://rclone.org/install/) to connect shared files, then run `rclone config`. Create a remote named `onedrive`, choose **Microsoft OneDrive**, leave client credentials at their defaults, and sign in with GT/Duo. Choose **SharePoint site**, enter `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`, and select **Documents**. Select menu entries by name, since their numbers can change. [Official connection reference](https://rclone.org/onedrive/).

Check the connection:

```text
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
```

You should see `FY27_Bills_Budget.xlsx`. If it is missing, ask the finance officer to check your access and library selection.

</details>

Create a local folder for finance work and download the shared workbook into it, keeping the name `FY27_Bills_Budget.xlsx`. Run commands from this folder each time.

<details>
<summary>How to open the working folder in your terminal</summary>

Type `cd ` followed by the full path to your folder in quotes. For example:

```text
cd "/full/path/to/your/finance-folder"
```

Then point the helpers at your downloaded workbook. Repeat this in each new terminal session.

macOS / Linux:

```bash
export FINANCE_XLSX_PATH="$PWD/FY27_Bills_Budget.xlsx"
```

Windows PowerShell:

```powershell
$env:FINANCE_XLSX_PATH = Join-Path (Get-Location).Path "FY27_Bills_Budget.xlsx"
```

Run `mrg-finance doctor` and check that its `Target file` is your intended workbook.

</details>

## 3. Run a budget or purchase request

Save your shared-sheet edits first. `--fresh` attempts to download the latest shared files; read the sync result before continuing.

```text
mrg-finance doctor --fresh
```

Fix reported data errors, then choose a request:

| Task | Command | What you do |
| --- | --- | --- |
| Budget / bill | `mrg-finance bill-request --fresh` | Create/open an Engage draft first. Select your bill in the terminal; have the draft's edit URL ready if `Bill No.` is blank. Follow the screenshot and GT/Duo prompts, review any option to clear draft items, then check and submit in Engage. |
| Purchase | `mrg-finance purchase --fresh` | Select your order. Follow the price and GT/Duo prompts. Check the cart, bill/line references, amount, account/category, and both attachments. Complete any missing fields, sign, and submit in Engage. |
| Comparison report only | `mrg-finance report --fresh` | Select your order. Open the generated file at the printed path and verify quoted prices and Engage references before attaching it. |

If the cart or form automation fails, finish those steps manually using the workflow above. In a purchase run, **press Enter in the terminal only after submitting in Engage**, then verify or paste the confirmation URL when prompted. Check SharePoint afterward to confirm the links reached all order rows.

<details>
<summary>Common problems and extra options</summary>

- **Command not found:** reopen the terminal after installation. For `mrg-finance`, run `uv tool update-shell` and reopen again.
- **Sync fails or old data appears:** confirm Excel has saved and check `rclone ls` using the command above. For expired login, run `rclone config reconnect onedrive:`. A failed sync can leave the tool using an older copy; verify the workbook before continuing.
- **Missing or wrong calculated values:** check the source ID and save/recalculate in Excel. Python reads saved results; it does not calculate Excel formulas.
- **Vendor page blocks screenshots or prices:** capture the evidence in your normal browser. Check the report against the actual quote; failed scraping may fall back to budget prices.
- **Missing form fields or attachments:** fill them manually. If details were placed in Description, copy them to the required fields and check the cart link is still present.
- **Choose a request directly:** add `--bill "Exact Bill Title"` to `bill-request`, or `--order "260910_amazon_gburdell3"` to `purchase`.
- **More commands:** `mrg-finance --help` lists screenshot, review, and price-check tools. The review page can save price edits to the workbook; check changes before saving.
- **Update:** rerun the installation command with `--force --refresh` after `uv tool install`.
- **Detailed guides:** For advanced rclone setup and extra commands, see [CLI Guide](docs/CLI_GUIDE.md). For common error fixes, see [Troubleshooting](docs/TROUBLESHOOTING.md).

</details>

Maintaining the software? See [Development](docs/DEVELOPMENT.md). Coding agents: read [agents.md](docs/agents.md).
