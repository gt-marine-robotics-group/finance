# ⚓ Georgia Tech MRG Finance & Purchasing System

Automated bill request submission, purchase request automation, live price auditing, and budget spreadsheet management for the **Georgia Tech Marine Robotics Group**.

---

## 🌟 Primary Priority Functions

### 1️⃣ Priority 1: Submit Bill Requests (`mrg bill-request` / `automation.py`)
- **Purpose**: Submits new draft budget bills to Georgia Tech CampusLabs Engage for SGA approval.
- **Features**: Groups line items by budget section, verifies screenshot evidence for every item, and pre-fills the Engage bill form automatically.

### 2️⃣ Priority 2: Submit Purchase Requests (`mrg purchase` / `automation_purchase.py`)
- **Purpose**: Submits purchase requests to CampusLabs Engage for approved items ready to be ordered.
- **Features**: Groups order items by vendor, checks live prices vs approved budget allocations, auto-adds items to Amazon carts, captures `cart.png` evidence, resolves exact live section & line numbers on Engage, and pre-fills the purchase request form.

---

---

### 🛠️ Supporting Feature: Spreadsheet Item Management & Web GUI
- **Purpose**: Easily add, edit, and review items in `FY27_Bills_Budget.xlsx`.
- **GUI Tools**:
  - **Side-by-Side Inspector (`http://localhost:8321`)**: Visually compare baseline bill screenshots against current live scraped prices.
  - **Web Dashboard (`http://localhost:5000`)**: Full Flask web interface to paste product URLs, auto-scrape vendor details, and manage orders.

---

## 🗺️ Complete Repository Architecture & Code Map

<details>
<summary><b>🤖 Layer 1: Core Automation Engine (CampusLabs Engage Forms & Price Scraping)</b></summary>

- **`automation.py`**: Priority 1 SGA Bill Request automation script. Navigates CampusLabs Engage Angular SPA (`...#/edit/{bill_no}`), creates/edits bills, populates budget sections, uploads screenshot evidence, and verifies created items.
- **`automation_purchase.py`**: Priority 2 Purchase Request automation script. Groups order items by vendor, checks live prices vs approved allocations, pre-fills Subject (`Marine Robotics Group Vendor Purchase Request YYYY-MM-DD`), Amount, SGA Bill Box (price/line/bill/section), and Budget/Bill Line # fields, with Description box fallback.
- **`engage_bill_lookup.py`**: Engage DOM scraper module. Navigates to Engage bill pages, clicks the "Budget" tab, traverses section anchors (`h4.groupTitle`), and extracts section names and 1-based section line numbers.
- **`engage_tools.py`**: Shared Selenium browser helper functions for GT SSO login (`USERNAME`/`PASSWORD`), 3-minute Duo MFA verification, and hidden file upload input handling.
- **`price_scraper.py`**: Multi-vendor live price scraper and parser. Extracts unit prices from JSON-LD schema, OpenGraph meta tags, Amazon buyboxes, McMaster-Carr, DigiKey, Mouser, Adafruit, SparkFun, and Pololu.
- **`automation_screenshots.py`**: Headless Chrome full-page screenshot capture engine. Resolves baseline bill screenshots vs scraped order screenshots and generates `review.html` for side-by-side inspection.

</details>

<details>
<summary><b>🌐 Layer 2: Web Application Dashboard & Review GUI</b></summary>

- **`mrg.py`**: Unified CLI entrypoint supporting subcommands `mrg purchase`, `mrg bill-request`, `mrg review`, `mrg price-check`, `mrg screenshots`, and `mrg doctor`.
- **`review_server.py`**: Micro HTTP server on port 8321. Serves `review.html` and handles `/save-prices` POST requests to update `FY27_Bills_Budget.xlsx` using openpyxl without opening Excel popups.
- **`review.html`**: Interactive side-by-side screenshot and price review page with keyboard shortcuts (`←`/`A`, `→`/`D`, `1`, `2`, `Enter`), dark mode styling, and direct Excel saving.
- **`web-app/app.py`**: Flask web application entrypoint registering blueprint routes (`auth`, `dashboard`, `bills`, `orders`, `items`, `screenshots`).
- **`web-app/xlsx_manager.py`**: Core Excel database engine. Manages `FY27_Bills_Budget.xlsx` via openpyxl and Microsoft Graph API, preserving cell formulas (`IFERROR`, `SUM`), row formatting, and O(1) in-memory caching.
- **`web-app/screenshot_worker.py`**: Async background thread worker that monitors item creation queue and automatically generates product screenshots.
- **`web-app/routes/`**: Modular Flask blueprints:
  - **`auth.py`**: GT username SSO login session management.
  - **`dashboard.py`**: Bill dashboard, total cost calculation, and quick-add bar.
  - **`bills.py`**: Bill review page, inline line item editing, and screenshot triggers.
  - **`orders.py`**: Order creation, vendor grouping, order quantity editing, and side-by-side order review.
  - **`items.py`**: Quick-add URL parser and queue item management.
  - **`screenshots.py`**: Static image serving and screenshot asset routes.

</details>

<details>
<summary><b>🛡️ Layer 3: Spreadsheet Resilience & Pre-Flight Diagnostics</b></summary>

- **`spreadsheet_utils.py`**: Robust Excel loading, dynamic header row detection (rows 0-10), fuzzy column alias resolution (`COLUMN_ALIASES`), float ID sanitization (`376851.0` ➔ `"376851"`), and `validate_budget_spreadsheet()` health checker.
- **`FY27_Bills_Budget.xlsx`**: Master budget spreadsheet containing `Bills` sheet (approved SGA allocations) and `Ordering` sheet (OrderT order groups).
- **`screenshots/`**: Evidence screenshot directory structured by bill title (`screenshots/<Bill Title>/<Item Name>.png`) and order ID (`screenshots/<Order ID>/<Item Name>.png`).

</details>

<details>
<summary><b>📖 Layer 4: Configuration, Tests & Documentation</b></summary>

- **`pyproject.toml`**: Setuptools build metadata and global CLI script entrypoints (`mrg = "mrg:main"`, `mrg-finance = "mrg:main"`).
- **`USAGE_GUIDE.md`**: Comprehensive student usage guide, 5-minute setup, 1-step `pipx` global CLI installation, and developer code map.
- **`DEVELOPMENT.md`**: Developer architecture guide, Flask blueprint structure, and technical reference.
- **`tests/`**: Pytest automated test suite:
  - **`test_app_routes.py`**: Flask web app endpoint & blueprint unit tests.
  - **`test_engage_bill_lookup.py`**: Engage DOM parser and line number unit tests.
  - **`test_price_scraper.py`**: Multi-vendor price parsing unit tests.
  - **`test_xlsx_manager.py`**: Excel formula preservation and cell PATCHing unit tests.

</details>

---

## 🛠️ Prerequisites & System Setup

Follow this step-by-step setup guide to configure your environment, install the CLI, and connect to SharePoint cloud sync.

### 1. Python & UV Package Manager

Ensure you have **Python 3.10+** installed. We recommend [`uv`](https://github.com/astral-sh/uv) for fast, reliable package and environment management.

- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Or via Homebrew: brew install uv
  ```
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

---

### 2. Clone Repository & Install CLI

#### Option A: 1-Step Global CLI Installation (Use Anywhere!)

##### ⚡ Via `pipx` (Standard Python CLI Installer):
```bash
pipx install git+https://github.com/gt-marine-robotics-group/finance.git
```

##### 🚀 Via `uv tool` (Ultra-Fast Modern Alternative):
```bash
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
```

> **💡 What is the difference between `pipx` and `uv tool`?**
> - **Global Terminal Access**: Both tools install `mrg-finance` inside an isolated Python virtual environment and link the `mrg-finance` executable globally so it runs from **any terminal directory**.
> - **`pipx install`**: The traditional standard tool for installing Python CLI applications (`brew install pipx`). It uses standard `pip` underneath.
> - **`uv tool install`**: The modern alternative powered by Astral's `uv` (written in Rust). It completes package installation in **milliseconds** (10-50x faster than pipx) and handles dependency resolution ultra-fast.

#### Option B: Local Editable Clone
```bash
# 1. Clone the repository
git clone git@github.com:gt-marine-robotics-group/finance.git
cd finance

# 2. Create virtual environment & activate
uv venv
source .venv/bin/activate    # On Windows: .\.venv\Scripts\Activate.ps1

# 3. Install dependencies and CLI tool in editable mode
uv pip install -e .
```

After installation, the CLI is available globally as `mrg-finance`.

---

### 3. Browser & Selenium Setup

The system uses Chrome and Selenium for automated web scraping and CampusLabs Engage form submission.

- **macOS**: Install Google Chrome (`brew install --cask google-chrome`).
- **Linux**: Install Chromium/Chrome (`sudo apt install chromium-browser`).
- **Windows**: Install Google Chrome.

---

### 4. ☁️ SharePoint & Cloud Sync Setup (`rclone`)

Item screenshots and master budget files are synced directly with the team's shared **GT OneDrive / SharePoint** folder (`OPS-1 Operations/FY27 Finances`).

#### Step 1: Install `rclone`
- **macOS**: `brew install rclone`
- **Linux**: `sudo apt install rclone`
- **Windows**: `winget install rclone.rclone`

#### Step 2: Configure GT OneDrive Remote
Run `rclone config` in your terminal and follow this exact key sequence:

1. Type **`n`** *(New remote)*
2. Name: Type **`onedrive`** *(Must be exactly `onedrive` in lowercase)*
3. Storage: Type **`42`** *(Microsoft OneDrive)*
4. `client_id` & `client_secret`: Press **Enter** *(Leave blank)*
5. `region`: Press **Enter** *(Default global)*
6. `Edit advanced config?`: Type **`n`**
7. `Use web browser to authenticate?`: Type **`y`**
8. **Browser Authentication**: Log in with your **Georgia Tech SSO (`<username>@gatech.edu`) + Duo MFA**.
9. `config_type`: Type **`3`** *(SharePoint site name or URL)*
10. `config_site_url`: Type **`https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`**
11. `config_driveid`: Type **`3`** *(Documents)*
12. Confirm with **`y`**, then type **`q`** to quit.

#### Step 3: Verify Remote Sync Access
```bash
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
```

---

## 🤖 CLI Usage & Workflows (`mrg-finance`)

The `mrg-finance` CLI tool provides end-to-end automation for price scraping, side-by-side screenshot verification, bill submissions, and purchase tracking.

```
Usage:
    mrg-finance report [--fresh] [--order ORDER_ID]
    mrg-finance doctor [--fresh]
    mrg-finance bill-request [--fresh]
    mrg-finance purchase [--fresh] [--order ORDER_ID]
    mrg-finance review [--bill TITLE]
    mrg-finance price-check [--fresh] [--bill TITLE]
    mrg-finance screenshots [--fresh] [--bill TITLE] [--review-only]

Commands:
    report          Generate Budget vs Quoted Full Detail Excel (.xlsx) & CSV reports
    doctor          Run pre-flight health audit on FY27_Bills_Budget.xlsx
    bill-request    Submit a bill request to CampusLabs Engage (Priority 1)
    purchase        Submit purchase requests to Engage (Priority 2)
    review          Launch side-by-side screenshot & price review GUI
    price-check     Check live prices vs budget allocation & warn on overrun
    screenshots     Scrape prices + capture full-page screenshots for a bill
```

---

### 1. `mrg-finance report` — Generate Budget vs Quoted Excel & CSV Reports

Generates a side-by-side **Budget Request vs Quoted Line Items** comparison report containing live Excel formulas (`=E*F`, `=H*I`, `=SUM(...)`), subtotal rows, and grand totals for attachment to Engage purchase requests.

```bash
# Generate report for specific order:
mrg-finance report --order 260811_amazon_awu335

# Sync fresh spreadsheet from SharePoint first, then generate report:
mrg-finance report --fresh --order 260811_amazon_awu335

# Interactive order selection (shows a numbered list of all available orders):
mrg-finance report
```

*Output files are saved to `screenshots/<order_id>/Budget_vs_Quoted_Detail_<order_id>.xlsx` and `.csv`.*

---

### 🩺 `mrg-finance doctor` — Pre-Flight Spreadsheet Health Audit

`mrg-finance doctor` runs a pre-flight health diagnostic audit on `FY27_Bills_Budget.xlsx` before running bill or purchase request submissions. It protects automation scripts from spreadsheet edits, missing links, and broken row references.

```bash
# Run spreadsheet diagnostic check on local file:
mrg-finance doctor

# Sync latest file from SharePoint first, then run diagnostic check:
mrg-finance doctor --fresh
```

#### What `mrg-finance doctor` actually checks:

| Diagnostic Check | Description | Action Required if Flagged |
| :--- | :--- | :--- |
| 🔍 **Duplicate Item IDs** | Detects duplicate `Bill Item ID`s across sheets that cause item mapping collisions. | Ensure each bill line item has a unique ID in Excel. |
| 🔗 **Broken Order References** | Identifies `OrderT` rows referencing a `Bill Item ID` that does not exist in the `Bills` sheet. | Fix or clear the invalid `Bill Item ID` on the order row. |
| 🌐 **Invalid or Missing Links** | Flags items missing product URLs or containing non-HTTP/malformed links. | Add valid product URLs (e.g. Amazon, DigiKey, McMaster) to the item. |
| 💵 **$0.00 Cost Allocations** | Highlights approved items allocated with `$0.00` cost. | Check allocation column for accidental zero values. |
| 📄 **Sheet & Header Offsets** | Scans top 10 rows to detect header shifts and verifies required sheets (`Bills`, `Ordering`). | Auto-resolved by `spreadsheet_utils` fuzzy parser. |

> **💡 Row-Level Reporting**:
> When errors or warnings are detected, `mrg-finance doctor` reports the **exact Excel row numbers** so team members can fix them directly in Excel before submitting requests!

---

### 2. `mrg-finance review` — Instant Side-by-Side Review

Launches the interactive side-by-side screenshot & price review GUI in your default browser **without running web scraping or opening Chrome automation**.

```bash
# Prompt to select a bill:
mrg-finance review

# Or specify a bill directly:
mrg-finance review --bill "Marine Robotics Group RobotX Testing Equipment Bill"
```

---

### 📸 Manual Screenshot Naming Guide

If team members capture or upload screenshots manually, place them in:
```
screenshots/<Bill Title>/<Item Name>.png
# OR on SharePoint:
onedrive:OPS-1 Operations/FY27 Finances/screenshots/<Bill Title>/<Item Name>.png
```

#### How Naming & Recognition Works:
The application uses a **flexible matching algorithm** (`_find_file_in_dir`), so manual screenshots are automatically recognized even with minor naming variations:

1. **Item Name Matching**:
   - Item `"wire cutters"` → `wire cutters.png` or `wire cutters.jpg`
2. **Case & Whitespace Flexible**:
   - Double spaces, trailing spaces, or UPPERCASE/lowercase differences are automatically normalized:
     - Item: `"N type connector  replacement"` (double space)
     - Filename: `N type connector replacement.png` or `N Type Connector Replacement.PNG` → **✅ 100% Recognized**
3. **Special Character Sanitization**:
   - Characters like slashes `/` or colons `:` can be replaced with spaces or underscores:
     - Item: `"2m IP67 LED Strip (144LED/m)"`
     - Filename: `2m IP67 LED Strip (144LED_m).png` or `2m IP67 LED Strip (144LED m).png` → **✅ 100% Recognized**
4. **Supported Extensions**: `.png`, `.jpg`, `.jpeg`, `.webp`

---

### 2. `mrg screenshots` — Scrape Prices & Capture Evidence

Scrapes current product prices via headless Chrome and captures full-page product screenshots. Upon completion, it automatically opens the side-by-side review GUI.

```bash
# Pull fresh spreadsheet & screenshots from SharePoint before running:
mrg screenshots --fresh

# Specify bill title directly:
mrg screenshots --bill "FY27 Budget"

# Launch review GUI directly using existing screenshots:
mrg screenshots --review-only
```

- **Ground-Truth Safeguard**: Existing baseline bill screenshots stored in `screenshots/<bill_title>/<item_name>.png` are **never overwritten**. Newly captured screenshots are stored alongside them for side-by-side comparison.

---

### 3. `mrg bill-request` — Submit Bill to CampusLabs Engage

Automates creating a official bill request on CampusLabs Engage.

```bash
mrg bill-request --fresh
```

**Workflow**:
1. Prompts for GT SSO credentials + Duo MFA.
2. Performs a missing screenshot audit and captures any missing item screenshots.
3. Launches the side-by-side review GUI (`http://localhost:8321`) to verify prices and screenshots.
4. Opens Engage in Chrome, fills out line items for each budget section, uploads screenshot evidence, and saves each item.

---

### 4. `mrg purchase` — Automated Purchase Requests

Automates purchase request submissions on CampusLabs Engage grouped by vendor from `OrderT`.

```bash
# Interactive order selection:
mrg purchase --fresh

# Specify order ID directly:
mrg purchase --fresh --order "260811_amazon_awu335"
```

**Workflow**:
1. Prompts to select an Order ID.
2. Runs a live price audit against vendor product links.
3. Auto-generates a **1-Click Amazon Multi-Item Cart URL** (or warns for non-Amazon vendor items).
4. Opens side-by-side order review window and populates Engage purchase request fields.

---

### 5. `mrg price-check` — Budget Overrun Audit

Runs a headless price check against product links to verify live prices against approved budget allocations.

```bash
mrg price-check --fresh --bill "FY27 Budget" --cart
```

**Workflow**:
1. Scrapes live prices from product pages.
2. Prints a comparison table highlighting budget overruns (`+$XX.XX OVER BUDGET`) or savings.
3. Generates a 1-Click Amazon Cart link for Amazon items.

---

## 🌐 Web Page & Review GUI Features

### 1. Side-by-Side Review Inspector (`http://localhost:8321`)

When running `mrg review`, `mrg screenshots`, or `automation.py`, the system starts a local review server on port `8321` and opens **`http://localhost:8321`** in your browser.

```
+-------------------------------------------------------------------------------+
|  📋 Side-by-Side Review  |  Bill: Testing Equipment Bill    [💾 Save to Excel] |
+------------------+------------------------------------------------------------+
|  SIDEBAR DRAWER  |  ITEM INSPECTOR (Item 6 of 11: large rope)                 |
|                  |  Spreadsheet: $13.99  |  Scraped: $0.25                    |
|  [All (11)]      |  [Use Spreadsheet Price (1)]  [Use Scraped Price (2)]     |
|  [⚠️ Review (2)] |                                                            |
|  [✅ OK (9)]     |  +--------------------------+---------------------------+  |
|                  |  | 📜 Baseline Screenshot    | 📸 New Scraped Screenshot |  |
|  1. hose     ⚠️  |  |   (Ground Truth)         |   (Current Run)           |  |
|  2. anchors  ✅  |  |                          |                           |  |
| >3. large rope ⚠️|  |  [ Image Frame ]         |   [ Image Frame ]         |  |
|  4. Pi Pico  ✅  |  +--------------------------+---------------------------+  |
+------------------+------------------------------------------------------------+
|  Shortcuts: [←/A] Prev  |  [→/D] Next  |  [1] Spreadsheet  |  [2] Scraped     |
+-------------------------------------------------------------------------------+
```

#### Key Visualizer Features:
- 🖼️ **Side-by-Side Split View**: Displays the **Baseline / Old Screenshot** (left) directly alongside the **New / Scraped Screenshot** (right).
- ⚡ **Fast Click-Through Navigation**:
  - `◀ Prev` and `Next ▶` buttons.
  - Left thumbnail drawer sidebar for instant 1-click item selection.
  - **Keyboard Shortcuts**:
    - `←` / `A`: Move to Previous Item
    - `→` / `D`: Move to Next Item
    - `1`: Apply Spreadsheet Price
    - `2`: Apply Scraped Price
    - `Enter`: Save current price & advance to Next Item
- ✏️ **Direct Spreadsheet Saving**: Clicking **`💾 Save to Spreadsheet`** updates `FY27_Bills_Budget.xlsx` directly via background HTTP POST—without popping open Excel application windows.
- 🔍 **High-Res Lightbox**: Click any image to open a full-screen zoom modal.
- ☰ **View Modes**: Toggle between **Focused Inspector View** (single item side-by-side) and **List View** (all cards scrollable list).

---

### 2. Web App Dashboard (`http://localhost:5000`)

To start the full web management dashboard locally:

```bash
source .venv/bin/activate
python3 web-app/app.py
```

Open **`http://localhost:5000`** in your browser (*Password: `boats0519`*):

- **Quick-Add Bar**: Paste any product URL to auto-scrape vendor and price details.
- **Bill Management (`/review/<bill_title>`)**: Review bill items, inspect pre-captured screenshots, and edit line items.
- **Order Creation (`/create-order`)**: Group approved bill items by vendor, select custom quantities (capped at approved bill max), and generate 1-click Amazon Cart links.
- **Side-by-Side Order Review (`/orders/review/<order_id>`)**: Compare baseline bill screenshots against live order prices with overrun badges.

---

## 🛡️ System Safeguards & Offline Mode

1. **Ground-Truth Screenshot Protection**: Original bill evidence images in `screenshots/<bill_title>/<item_name>.png` are permanently preserved.
2. **Zero File Deletions (`rclone copy`)**: SharePoint sync uses `rclone copy --checksum` (never `rclone sync`), preventing accidental file deletion.
3. **No Excel Popups**: Saving edits in the review GUI updates the underlying `.xlsx` file cleanly and touches file timestamps for OneDrive sync without interrupting your workflow.
4. **Offline Excel Mode**: If working offline, save your spreadsheet locally at `finance/FY27_Bills_Budget.xlsx` and run CLI commands without the `--fresh` flag.
