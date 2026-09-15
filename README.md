# ⚓ MRG Finance

Automated budget management, live price auditing, quotation comparisons, screenshot capture, and CampusLabs Engage submissions for the **Georgia Tech Marine Robotics Group**.

All team purchasing begins in the master shared workbook:
👉 **[FY27_Bills_Budget.xlsx on SharePoint](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)** *(sign in with your `@gatech.edu` account)*.

---

## 🚀 Quick Install

Install the `mrg-finance` CLI globally using [`uv`](https://docs.astral.sh/uv/):

```bash
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git

# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
```
Verify with `mrg-finance --help`. *(For developers: clone repo, then run `uv sync` and `uv run pytest`).*

---

## 📋 Core Purchasing Workflow

### Step 1: Request Funding (`Bills` sheet)
> *Do this when you want SGA to approve budget for future purchases.*

1. Open the **`Bills`** sheet on SharePoint.
2. Group items under a shared **`Bill Title`** (e.g. `Marine Robotics Group RobotX Testing Equipment Bill`).
3. Fill in: `Item Name`, `Vendor`, unit `Cost`, `Quantity`, product `Link`, `Budget Section` (`B03` for equipment/tools, `B06` for supplies), and `Person Requesting`.
4. **Do not edit `Bill Item ID` or `Total Cost`** — calculated automatically.
5. Submit the draft to SGA:
   ```bash
   mrg-finance bill-request --fresh
   ```
   *(Or submit manually on [Engage Budgeting](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting)).*
6. Once SGA approves the bill, record the official **`Bill No.`** on all item rows.

---

### Step 2: Order Items (`Ordering` sheet)
> *Do this when you are ready to purchase items with approved funding.*

1. Open the **`Ordering`** sheet.
2. Create an **`Order ID`**: `YYMMDD_vendor_gtusername` (e.g. `260811_amazon_awu335`) on every row in this cart.
3. **Copy the `Bill Item ID`** from `Bills` into Column B (`Bill Item ID`). Formulas will auto-pull the item details.
4. Fill in: `Quantity` (amount to buy now), `Purchaser`, and `Status` (`Pending`).

---

### Step 3: Submit the Purchase Request

Run the automated purchasing assistant:
```bash
mrg-finance purchase --fresh
```
This audits live vendor prices, captures cart screenshots, builds the Budget vs Quoted comparison report (`.xlsx`/`.csv`), opens your vendor cart, and fills the Engage request form.

---

> [!TIP]
> ### 💡 Aside: Manual / Local Usage (No `rclone` needed)
> You **do not need `rclone`** or online sync configured to use the tools. If you prefer manual or local workflows:
> - **Using the CLI with a local file**: Download `FY27_Bills_Budget.xlsx` from SharePoint into your working folder. **As long as you run `mrg-finance` in the same directory as `FY27_Bills_Budget.xlsx`, it will detect the spreadsheet automatically and work completely fine!** Simply omit the `--fresh` flag (e.g. `mrg-finance doctor`, `mrg-finance purchase`).
> - **Submitting manually without CLI**: Add items to your vendor cart and take a screenshot (`cart.png`). Open [Create Purchase Request in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest), fill in vendor, amount, funding account, and approved bill & line numbers, then attach `cart.png` and your price comparison. Finally, on the `Ordering` sheet, paste the submitted URL into **`Engage Request Link`** (Col V) and cart link into **`Share-A-Cart Link`** (Col U).

---

## 🛠️ Handy CLI Commands

All commands accept `--fresh` (`-f`) when `rclone` is configured to sync directly with SharePoint:

| Command | Description |
| :--- | :--- |
| `mrg-finance doctor [--fresh]` | Diagnostics: validates formulas, missing bill numbers, blank URLs, and non-positive costs. |
| `mrg-finance bill-request [--fresh]` | Automates Engage funding bill submission and screenshot attachments. |
| `mrg-finance purchase [--fresh]` | Price audits, cart generation, Budget vs Quoted reports, and Engage purchase submission. |
| `mrg-finance price-check [--bill <TITLE>] [--cart]` | Scrapes live vendor prices, reports price deltas, and generates 1-Click Amazon cart links. |
| `mrg-finance report --order <ORDER_ID>` | Compiles formatted Budget vs Quoted Excel (`.xlsx`) & `.csv` comparison reports. |
| `mrg-finance review [--bill <TITLE>]` | Opens local web review UI (`http://127.0.0.1:8321`) to inspect screenshots and prices. |
| `mrg-finance screenshots [--bill <TITLE>]` | Captures full-page vendor screenshots for items in a bill. |

---

## ☁️ Optional: Automated SharePoint Sync (`rclone`)

To enable `--fresh` automatic sync with Georgia Tech SharePoint:
1. Install `rclone` (`brew install rclone` on macOS, `winget install Rclone.Rclone` on Windows).
2. Run `rclone config` &rarr; New remote `onedrive` &rarr; Storage `onedrive` &rarr; Authenticate via GT login/Duo &rarr; Select `SharePoint site` (`https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`) &rarr; Select `Documents`.
3. Verify: `rclone ls "onedrive:OPS-1 Operations/FY27 Finances"`.

---

## 📚 Detailed Reference Guides

- [Spreadsheet & Manual Workflow Guide](docs/user/WORKFLOW_GUIDE.md) — Comprehensive schema, formulas, column reference, and manual Engage walkthrough.
- [CLI & Troubleshooting Guide](docs/user/CLI_GUIDE.md) — Full CLI flags, custom paths, and troubleshooting FAQs.
- [Developer & Web App Guide](docs/dev/DEVELOPMENT.md) — System architecture, simulation test suites, SIM PC deployment, and Graph API.
