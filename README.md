# ⚓ MRG Finance Automation Suite

Automated budget management, live price auditing, quotation comparisons, screenshot capture, and CampusLabs Engage submissions for the **Georgia Tech Marine Robotics Group**.

All team purchasing begins in the master shared workbook:
👉 **[FY27_Bills_Budget.xlsx on SharePoint](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)** *(sign in with your `@gatech.edu` account)*.

---

## 📑 Table of Contents
1. [Installation from Scratch](#-installation-from-scratch)
2. [One-Time SharePoint Connection (`rclone`)](#-one-time-sharepoint-connection-rclone)
3. [Optional: Manual & Offline Usage (Without `rclone`)](#-optional-manual--offline-usage-without-rclone)
4. [Complete Uninstall & Reset](#-complete-uninstall--reset)
5. [Running Tests from Scratch](#-running-tests-from-scratch)
6. [CLI Commands Reference](#-cli-commands-reference)
7. [Core Purchasing Workflow Guide](#-core-purchasing-workflow-guide)
8. [Mobile Purchasing Web App](#-mobile-purchasing-web-app)
9. [Troubleshooting & FAQs](#-troubleshooting--faqs)
10. [Detailed Reference Guides](#-detailed-reference-guides)

---

## 🚀 Installation from Scratch

Choose either **Option A** (recommended for general members) or **Option B** (for developers contributing code):

### Option A: Global CLI Install via `uv` (Recommended)
Installs `mrg-finance` into an isolated environment and exposes the CLI command directly to your PATH:

```bash
# 1. Install uv (if not already installed)
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex

# 2. Install mrg-finance globally directly from GitHub
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git

# 3. Verify installation
mrg-finance --help
```

To update to the latest version at any time:
```bash
uv tool install --force --refresh git+https://github.com/gt-marine-robotics-group/finance.git
```

### Option B: Local Repository Setup (Developers)
```bash
# 1. Clone the repository
git clone https://github.com/gt-marine-robotics-group/finance.git
cd finance

# 2. Install dependencies into virtual environment
uv sync

# 3. Verify CLI execution
uv run mrg-finance --help
```

---

## ☁️ One-Time SharePoint Connection (`rclone`)

The recommended way to use `mrg-finance` is with `rclone`. This allows the CLI to automatically synchronize the master `FY27_Bills_Budget.xlsx` spreadsheet and screenshots directly with Georgia Tech's SharePoint vault using the `--fresh` (`-f`) flag.

### 1. Install `rclone`
* **macOS**: `brew install rclone`
* **Linux**: `sudo -v ; curl https://rclone.org/install.sh | sudo bash`
* **Windows**: `winget install Rclone.Rclone`

### 2. Configure the GT SharePoint Remote
Run the interactive wizard in your terminal:
```bash
rclone config
```

Follow the prompts below (select options by **name**, not number):

| Prompt | What to Enter / Select |
| :--- | :--- |
| `No remotes found, make a new?` | `n` *(New remote)* |
| `name>` | `onedrive` *(Must be lowercase `onedrive`)* |
| `Storage>` | `onedrive` *(Microsoft OneDrive / SharePoint)* |
| `client_id>` | *(Press Enter to leave blank)* |
| `client_secret>` | *(Press Enter to leave blank)* |
| `region>` | *(Press Enter for global default)* |
| `Edit advanced config?` | `n` |
| `Use web browser to authenticate?` | `y` *(Opens browser: log in with `@gatech.edu` and approve Duo 2FA)* |
| `Your choice>` | Select `SharePoint site` |
| `Site URL>` | `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup` |
| `Select drive / document library` | Select `Documents` |
| `Confirm details?` | `y` |
| `Quit config?` | `q` |

### 3. Verify Connection & Pull Master Spreadsheet
```bash
# Verify connection by listing the team finances directory
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"

# Download the master spreadsheet to your working directory
rclone copy --ignore-checksum --ignore-size --update "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx" .
```

> [!TIP]
> Once `rclone` is configured, adding `--fresh` (`-f`) to any command (e.g. `mrg-finance doctor --fresh` or `mrg-finance purchase --fresh`) automatically pulls the newest spreadsheet and screenshots from SharePoint before executing.

---

## 📁 Optional: Manual & Offline Usage (Without `rclone`)

While `rclone` is the recommended setup for automated cloud sync, it is **strictly optional**. You can use `mrg-finance` completely offline or with a manually managed spreadsheet.

### 1. Running Locally Without `rclone`
Simply **omit the `--fresh` flag** from any command (e.g., run `mrg-finance doctor` instead of `mrg-finance doctor --fresh`). 

The CLI automatically searches for `FY27_Bills_Budget.xlsx` in this priority order:
1. **Current Working Directory**: `./FY27_Bills_Budget.xlsx`  
   *(If you run `mrg-finance` in the same directory as your downloaded `FY27_Bills_Budget.xlsx`, it detects it automatically!)*
2. **Repository Root**: `~/mrg/finance/FY27_Bills_Budget.xlsx`
3. **Native Desktop OneDrive Sync Folder** *(Mac/Windows)*: Automatically detected if you use the official Microsoft OneDrive desktop sync client.
4. **Custom Path Environment Variable**:
   ```bash
   export FINANCE_XLSX_PATH="/path/to/my_custom_budget.xlsx"
   ```

### 2. Manual Spreadsheet Workflow
1. Download `FY27_Bills_Budget.xlsx` directly from SharePoint in your browser (**File > Save As > Download a Copy**).
2. Move it into your working directory.
3. Run CLI commands without `--fresh`:
   ```bash
   mrg-finance doctor
   mrg-finance price-check --bill "Marine Robotics Group RobotX Testing Equipment Bill"
   mrg-finance report --order 260811_amazon_awu335
   mrg-finance review --bill "Marine Robotics Group RobotX Testing Equipment Bill"
   ```
4. When finished, upload the edited spreadsheet back to SharePoint via the web interface (or let your desktop OneDrive client sync it).

### 3. Working Completely Offline (No Internet / Field Use)
* **What works 100% offline**:
  - `mrg-finance doctor` (validates formulas, columns, and costs using local Python libraries).
  - `uv run pytest` (runs the 8 simulation workflows offline against in-memory mock data).
  - `mrg-finance report --order <ID>` (generates formatted `.xlsx` and `.csv` reports; automatically falls back to budgeted baseline unit costs if vendor sites are unreachable).
  - `mrg-finance review --bill "..."` (serves the review interface locally at `http://127.0.0.1:8321` using local screenshots and data).
  - Local spreadsheet editing in Microsoft Excel, LibreOffice, or Numbers.
* **What requires internet**:
  - Dynamic scraping of live vendor prices (`price-check`, `screenshots`) and CampusLabs Engage web submissions (`bill-request`, `purchase`). Prepare everything offline, then submit once connected.

---

## 🧹 Complete Uninstall & Reset

If you ever need to uninstall `mrg-finance` or reset your environment to a clean state:

```bash
# 1. Uninstall the global CLI tool
uv tool uninstall mrg-finance

# 2. Uninstall any pip packages (if installed previously via pip)
pip uninstall -y mrg-finance

# 3. Verify binary is completely removed
which mrg-finance  # Should return empty or 'not found'

# 4. (Optional) Reset rclone SharePoint connection
rclone config delete onedrive
# Or delete the config file entirely: rm -f ~/.config/rclone/rclone.conf

# 5. Clean local virtual environments, test caches, and build artifacts
rm -rf .venv build dist *.egg-info __pycache__ mrg_finance/__pycache__ .pytest_cache review.html
```

---

## 🧪 Running Tests from Scratch

The repository includes a consolidated end-to-end simulation suite in [`tests/test_workflow_simulation.py`](tests/test_workflow_simulation.py). The tests build temporary mock workbooks in memory and verify all 8 core workflows against deterministic ground truth without requiring external network calls or SharePoint logins:

```bash
uv run pytest
```

### Workflows Simulated & Verified:
1. **Spreadsheet Ingestion & Health Checks**: Multi-bill parsing, empty row handling, formula filtering.
2. **Dynamic Price Scraping & Fallbacks**: Scrapes Amazon, Adafruit, and generic vendors; tests baseline cost fallbacks on scrape failure; verifies 10-character Amazon ASIN extraction.
3. **Engage Bill Request Submission**: Authentication, line item entry, cost calculations, and screenshot upload sequencing.
4. **Engage Bill Line Lookup**: Automated bill matching, budget category identification, and dropdown line indexing.
5. **Budget vs Quoted Report Compilation**: Multi-tab formatted Excel sheet (`.xlsx`) and `.csv` generation with executive KPI blocks.
6. **Cart Generation**: 1-Click Amazon Multi-Item Cart URL and Share-A-Cart JSON payload building.
7. **Human Review Server**: Side-by-side screenshot verification, price adjustment, and overrun calculations.
8. **Web App Dashboard**: Multi-sheet aggregation and vendor allocation visualization.

---

## 🛠️ CLI Commands Reference

All commands accept `--fresh` (`-f`) when `rclone` is configured to sync directly with SharePoint:

| Command | Description |
| :--- | :--- |
| `mrg-finance doctor [--fresh]` | Diagnostics: validates formulas, missing bill numbers, blank URLs, and non-positive costs. *(Works offline without `--fresh`)*. |
| `mrg-finance price-check [--bill <TITLE>] [--cart]` | Scrapes live vendor prices, reports price deltas, and generates 1-Click Amazon multi-item cart links. |
| `mrg-finance report --order <ORDER_ID>` | Compiles formatted Budget vs Quoted Excel (`.xlsx`) & `.csv` comparison reports. *(Works offline)*. |
| `mrg-finance review [--bill <TITLE>]` | Opens local web review UI (`http://127.0.0.1:8321`) to inspect screenshots and prices. *(Works offline)*. |
| `mrg-finance screenshots [--bill <TITLE>] [--fresh]` | Captures full-page vendor screenshots and scrapes prices for items in a bill. |
| `mrg-finance bill-request [--bill <TITLE>] [--fresh]` | Automates Engage funding bill submission and screenshot attachments. |
| `mrg-finance purchase [--order <ORDER_ID>] [--fresh]` | Price audits, cart generation, Budget vs Quoted reports, and Engage purchase submission. |

---

## 📋 Core Purchasing Workflow Guide

All team purchasing data lives in **`FY27_Bills_Budget.xlsx`**:

### Step 1: Request Funding (`Bills` sheet)
> *Do this when you want SGA to approve budget for future purchases.*

1. Open the **`Bills`** sheet on SharePoint.
2. Group items under a shared **`Bill Title`** (e.g. `Marine Robotics Group RobotX Testing Equipment Bill`).
3. Fill in: `Item Name`, `Vendor`, unit `Cost`, `Quantity`, product `Link`, `Budget Section` (`B03` for equipment/tools, `B06` for supplies), and `Person Requesting`.
4. **Do not edit `Bill Item ID` or `Total Cost`** — Excel calculates these automatically.
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
3. **Copy the `Bill Item ID`** from the `Bills` sheet into Column B (`Bill Item ID`). Formulas will auto-pull the item details.
4. Fill in: `Quantity` (how many you are ordering now), `Purchaser`, and `Status` (`Pending`).

---

### Step 3: Submit the Purchase Request

Run the automated purchasing assistant:
```bash
mrg-finance purchase --fresh
```
This audits live vendor prices, captures cart screenshots, builds the Budget vs Quoted comparison report (`.xlsx`/`.csv`), generates vendor carts, and fills the Engage request form.

*(If submitting manually without the CLI: take a vendor cart screenshot, open [Create Purchase Request in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest), attach your cart screenshot and price comparison, and record the Engage URL in Col V and cart link in Col U).*

---

## 📱 Mobile Purchasing Web App

The repository includes a mobile-friendly Flask web application located in [`web-app/`](web-app/) designed to run 24/7 on the lab's SIM PC (accessible via Tailscale):
- **Quick Add**: Add items with vendor URLs directly from your phone.
- **Background Scraping**: Automatic screenshot capture and price fetching.
- **Bi-directional Cloud Sync**: Direct reads from local cached copy and writes to SharePoint via Microsoft Graph API.

To run the web app locally:
```bash
python web-app/app.py
# Access http://localhost:5000 (Default password: boats0519)
```

---

## ❓ Troubleshooting & FAQs

### Token Expired or OAuth Error on `rclone`
If SharePoint synchronization reports an authorization error:
```bash
rclone config reconnect onedrive:
```
Follow the browser prompt to re-authenticate with your Georgia Tech credentials and approve Duo 2FA.

### Running with a Custom Spreadsheet Path
If your spreadsheet is stored in a custom directory, point the CLI to it with:
```bash
export FINANCE_XLSX_PATH="/path/to/my_custom_budget.xlsx"
```

### Windows Path Whitespace Issues
`mrg-finance` v0.2.8+ automatically handles usernames and paths containing spaces on Windows without splitting arguments.

### Headless Chrome / Selenium Issues
Selenium automatically manages the appropriate `chromedriver` binary matching your local Google Chrome installation. Ensure Google Chrome is installed on your system.

---

## 📚 Detailed Reference Guides
- [Spreadsheet & Manual Workflow Guide](docs/user/WORKFLOW_GUIDE.md) — Comprehensive schema, formulas, column reference, and manual Engage walkthrough.
- [CLI & Troubleshooting Guide](docs/user/CLI_GUIDE.md) — Full CLI flags, custom paths, and troubleshooting FAQs.
- [Developer & Architecture Guide](docs/dev/DEVELOPMENT.md) — System architecture, simulation test suites, SIM PC deployment, and Graph API.
