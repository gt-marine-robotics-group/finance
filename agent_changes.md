# Agent Changes & Technical Changelog

This document provides a comprehensive, chronological, and architectural summary of all modifications, system designs, refactors, and bug fixes made across the MRG Finance automation suite.

---

## 🏗️ 1. Architecture & CLI Modernization

### 📦 Unified CLI Package (`mrg-finance`)
- **Package Standardization**: Migrated isolated standalone scripts into a structured Python package managed via `pyproject.toml` and installable with `uv tool install --force .` or `pipx`.
- **Global Executable**: Registered `mrg-finance` as the unified CLI binary (`mrg.py`), exposing modular subcommands:
  - `mrg-finance bill-request`: Interactive bill submission to CampusLabs Engage.
  - `mrg-finance purchase`: Automatic purchase request form filler with Excel and cart screenshot attachments.
  - `mrg-finance price-check`: Headless price scraper comparing live vendor prices vs spreadsheet allocations.
  - `mrg-finance screenshots`: Capture or re-audit product screenshots.
  - `mrg-finance report`: Generate dynamic `Budget_vs_Quoted_Detail` Excel comparison sheets.
  - `mrg-finance review`: Standalone side-by-side review dashboard web server.
  - `mrg-finance doctor`: Diagnostic test suite verifying Python env, Selenium, Chrome, `rclone`, and SharePoint connectivity.

### 📊 Dynamic Multi-Path Spreadsheet Resolution (`spreadsheet_utils.py`)
- **Hierarchy of Resolution**: Ensured all scripts dynamically locate `FY27_Bills_Budget.xlsx` across environments:
  1. CLI flag `--excel-path <path>` (explicit override)
  2. Environment variable `FINANCE_XLSX_PATH`
  3. Current working directory (`./FY27_Bills_Budget.xlsx`)
  4. Local repository path (`~/mrg/finance/FY27_Bills_Budget.xlsx`)
  5. OneDrive cloud sync path (`~/Library/CloudStorage/OneDrive-.../`)
- **Subprocess Propagation**: Updated `mrg.py` to forward `--excel-path` explicitly when invoking `automation.py`, `automation_purchase.py`, and background workers.
- **Robust Table Loading (`read_sheet_robust`)**:
  - Automatically identifies header offsets (e.g. skips title rows in `Ordering`).
  - Supports both `pandas.ExcelFile` and `openpyxl.Workbook` objects directly.
  - Implements case-insensitive, whitespace-normalized, and substring-tolerant column matching (`get_col_val`) to safely resolve complex column headers like `"Order ID (YYMMDD_vendor_gburdell3)"` or `"Bill Item ID"`.

---

## 📝 2. Bill Request Automation (`automation.py`)

### 📋 Interactive Bill Selection & URL Resolution
- **Dynamic Bill Discovery**: Automatically scans the `Bills` sheet (`BillsT` table), groups items by `Bill Title`, extracts approved `Bill No.` IDs, and presents an interactive indexed menu.
- **Engage URL Construction**: Automatically constructs direct Engage budgeting edit URLs (`https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests#/edit/<bill_no>`).
- **CLI Bypass**: Added `--bill` / `-b` argument to allow skipping the interactive menu during automated or headless runs.

### 📸 Pre-Flight Screenshot Audit & On-Demand Capture
- **Pre-Capture & Pre-Flight Validation**: Audits existing product screenshots before launching Engage automation, flagging missing items (`⚠️`) and presenting item counts and total costs.
- **Headless Chrome Capture**: Integrates on-demand headless Chromium to capture missing or updated screenshots directly from vendor links.
- **Alphanumeric Filename Normalization**: Normalized filename lookup (`re.sub(r"[^a-zA-Z0-9]+", "", item_name)`) to eliminate mismatches between sanitized on-disk names (e.g. `m2_5 threaded inserts.png`) and search queries (`m2.5 threaded inserts`).

### 🛡️ Resilient Engage DOM Interaction & MFA
- **Safe Duo MFA Polling**: Replaced brittle URL wait conditions with a null-safe polling lambda (`lambda d: bool(d.current_url and "gatech.campuslabs.com/engage" in d.current_url)`) to eliminate `TypeError: NoneType is not container` exceptions during browser redirects.
- **Section Management**: Implemented single-pass section processing (`B03`, `B06`, etc.) with user options to either clear all existing items or append/skip duplicates.

---

## 🛒 3. Purchase Request Automation (`automation_purchase.py`)

### 🔍 Live Engage Line Number Scraping (`engage_bill_lookup.py`)
- **Live Line Reference Extraction**: Automatically navigates to approved Engage bills and scrapes live rendered line numbers (e.g. `Bill 344042, Line 34`) corresponding to purchase order items.
- **Fuzzy Matching & Typo Tolerance**: Added string stemming and sequence matching to map items despite minor variations or Engage typos (e.g. matching `Toggle Switch` against Engage entry `Toggle Swtich`).
- **Multi-Tier Fallbacks**: Built a two-tier parser that inspects structured DOM containers first, falling back to a full-page body text regular expression scanner if AngularJS tables fail standard DOM node extraction.

### 📑 Automated Budget vs Quoted Excel Builder (`order_excel_builder.py`)
- **Live Formula Generation**: Generates standalone Excel comparison reports (`Budget_vs_Quoted_Detail_<order_id>.xlsx`) comparing budgeted allocations against live scraped vendor prices.
- **Dynamic Formulas**: Embeds native Excel formulas (`=E*F`, `=H*I`, `=SUM(...)`) with accurate subtotal ranges.
- **Dual Engage Attachments**:
  - **Upload #1**: Cart screenshot from `screenshots/<order_id>/cart.png`.
  - **Upload #2**: Auto-generated `Budget_vs_Quoted_Detail_<order_id>.xlsx` report.

### ⚡ Order Splitting & Overflow Handling
- **Line Item Threshold Management**: Detects orders exceeding Engage line item limit per purchase request and automatically splits them into a primary request and a secondary overflow request.

---

## 🌐 4. Price Scraping & Review Dashboard (`price_scraper.py`, `review_server.py`)

### 🤖 Anti-Bot & Multi-Vendor Scraping
- **Amazon Interstitial Detection**: Detects and automatically bypasses Amazon anti-bot / "Continue shopping" / CAPTCHA interstitial screens.
- **Price Extractors**: Multi-strategy extraction using JSON-LD schema metadata, OpenGraph tags, and prioritized DOM selectors (buybox price, sale price, deal price) while filtering out deceptive per-unit badge prices.

### 🖥️ Side-by-Side Review Web GUI
- **Side-by-Side Visual Diffing**: Renders split-card comparison views showing ground-truth quote screenshots next to newly scraped live vendor pages.
- **Bi-Directional Spreadsheet Sync**: Updates approved price changes across both `Bills` and `Ordering` sheets simultaneously via a local Flask background server.
- **`--no-review` Flag**: Added `--no-review` / `--skip-review` flags and prompt defaults allowing fast command-line execution without opening the browser GUI.

---

## 🔄 5. SharePoint Sync & Safeguards

### ☁️ `rclone` Sync Guarding
- **Safe Transfers**: Integrated `rclone` sync routines with `--ignore-checksum` and `--ignore-size` flags to handle OneDrive timestamp metadata quirks without data loss or duplicate downloads.
- **Execution Guards**: Wrapped CLI sync commands in module guards (`if __name__ == "__main__":`) to prevent recursive sync loops.

---

## 🐛 6. Detailed Bug Fixes & Regression Post-Mortems

| Commit | Component | Issue | Fix Implemented |
| :--- | :--- | :--- | :--- |
| `c4efa62` | `engage_bill_lookup.py` | `sec_items` uninitialized before container loop, causing silent `NameError` and forcing line references to fallback to row numbers. | Initialized `sec_items = []` at the top of each section loop. |
| `c56dc4c` | `spreadsheet_utils.py` | Exact dictionary key matching failed to match `"Order ID (YYMMDD_vendor_gburdell3)"` to `"order_id"`. | Added substring matching fallback in `get_col_val()`. |
| `1103f2a` | `automation_purchase.py` | Hardcoded OneDrive path caused purchase flow to read an outdated spreadsheet copy with blank item names/costs. | Unified path resolution with `mrg.py` and passed `--excel-path` explicitly. |
| `50c629d` | `automation.py` | `_skip = ("nan", "request", "liquid", "misc", "")` contained `""`, causing `startswith("")` to match and discard all bill titles (`[1-0]`). | Removed `""` from `_skip` and cleaned blank titles beforehand. |
| `8425dba` | `automation.py` | `EC.url_contains` threw `TypeError` when `driver.current_url` was momentarily `None` during Duo MFA redirect. | Used null-safe lambda checking `bool(d.current_url and "..." in d.current_url)`. |
| `9f23df0` | `automation.py` | Sanitization replaced `.` with `_` (e.g. `m2_5.png`), but preflight validator searched for `m2.5.png`, reporting existing screenshots as missing (`⚠️`). | Implemented alphanumeric normalization across all screenshot lookups. |

---

## 🧪 7. Test Suite Status
- All **28 unit tests** in `tests/` pass with zero failures:
  - `tests/test_app_routes.py` (13 tests)
  - `tests/test_engage_bill_lookup.py` (5 tests)
  - `tests/test_order_excel_builder.py` (2 tests)
  - `tests/test_price_scraper.py` (5 tests)
  - `tests/test_xlsx_manager.py` (3 tests)
