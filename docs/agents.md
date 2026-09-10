# AGENTS.md — AI Agent Guidelines & Architecture Manual

This manual provides authoritative context, architecture specifications, operational workflows, and safety constraints for AI agents working in the `gt-marine-robotics-group/finance` codebase.

---

## 🧭 1. System Overview & Core Objectives

The MRG Finance system automates financial workflows for the Georgia Tech Marine Robotics Group:
1. **SGA Bill Requests (`mrg-finance bill-request`)**: Submits equipment funding requests to Georgia Tech CampusLabs Engage with verified screenshot evidence.
2. **Purchase Requests (`mrg-finance purchase`)**: Auto-fills Engage purchase request forms, verifies live quoted prices, generates audit reports, creates Share-A-Cart bundles, and writes links back to the master spreadsheet.
3. **Audit & Review (`mrg-finance report`, `mrg-finance review`, `mrg-finance price-check`)**: Side-by-side visual diffing and dynamic Excel comparison generation.
4. **Master Database Sync (`FY27_Bills_Budget.xlsx`)**: Bi-directional synchronization with GT SharePoint via `rclone`.

---

## 🏗️ 2. Repository Architecture & File Blueprint

```
finance/
├── mrg.py                     # Unified CLI entrypoint (mrg-finance binary)
├── automation.py              # CampusLabs Engage bill submission automation
├── automation_purchase.py     # Purchase request form filler & order workflow
├── automation_screenshots.py  # Headless Chromium scraper & screenshot auditor
├── order_excel_builder.py     # Budget vs Quoted Excel generator with live formulas
├── price_scraper.py           # Multi-vendor scraper (Amazon, McMaster, DigiKey)
├── share_a_cart.py            # Share-A-Cart API integration & link generator
├── spreadsheet_utils.py       # Robust sheet reader, column normalizer, link writer
├── review_server.py           # Local HTTP server for review.html & Excel sync
├── review.html                # Side-by-side card visual inspection interface
├── FY27_Bills_Budget.xlsx     # Local mirror of SharePoint master workbook
├── tests/                     # Comprehensive pytest test suite (28+ tests)
├── web-app/                   # Flask web dashboard (runs on team SIM PC)
├── pyproject.toml             # uv package definition & CLI console script
└── docs/                      # Technical documentation, guides, and agent manuals
    ├── CLI_GUIDE.md           # CLI reference, rclone connection, and advanced commands
    ├── agents.md              # Operational manual and guidelines for AI agents
    ├── agent_changes.md       # Chronological technical changelog & post-mortems
    ├── MANUAL_WORKFLOW.md     # Step-by-step manual Engage submission guide
    ├── SPREADSHEET_GUIDE.md   # Schema & formula preservation rules
    ├── TROUBLESHOOTING.md     # Common errors & driver troubleshooting
    └── DEVELOPMENT.md         # System architecture & SIM PC web app guide
```

---

## 📑 3. Master Spreadsheet Schema & Integrity Rules

The master workbook is **`FY27_Bills_Budget.xlsx`** on SharePoint. Agents modifying or reading the spreadsheet must observe these hard rules:

### A. Never Overwrite Formulas
* In **`Bills` (`BillsT`)**: Column A (`Bill Item ID`) and Column K (`Total Cost`) are calculated via formulas. Writing static values corrupts auto-incrementing IDs.
* In **`Ordering` (`OrderT`)**: Columns C (`Bill No.`), D (`Bill Title`), E (`Item Name`), F (`Vendor`), G (`Cost`), I (`Total Cost`), J (`Allocation`), and O (`Budget Section`) are populated via `INDEX(MATCH(...))` looking into `BillsT`. Only write to static columns.

### B. Table Ranges & Boundaries
* **`BillsT`**: Defined table on sheet `Bills`.
* **`OrderT`**: Defined table on sheet `Ordering` spanning Columns A through V:
  - Col A (1): `Order ID (YYMMDD_vendor_gburdell3)`
  - Col B (2): `Bill Item ID`
  - Col C–T (3–20): Calculated fields, status, purchaser, instructions
  - Col U (21): `Share-A-Cart Link` (Direct link to online shopping cart)
  - Col V (22): `Engage Request Link` (URL to submitted Engage purchase request)

### C. Multi-Row Order Structure
* An order (e.g. `260819_amazon_awu335`) consists of multiple item rows.
* Order-level links (`Share-A-Cart Link` and `Engage Request Link`) must be written to **all rows** sharing that `Order ID` so sorting and filtering maintain record integrity. Use `spreadsheet_utils.update_order_table_links()`.

### D. Header Offsets
* The `Ordering` sheet has summary subtotals on Row 1 (`TOTALS`). The true column headers are on **Row 2**. Data begins on **Row 3**.
* Always use `spreadsheet_utils.read_sheet_robust()` or `spreadsheet_utils.get_col_val()` which automatically handle header row offsets and case/substring variations.

---

## ⚡ 4. Operational Workflows & CLI Invocations

When modifying or testing automation scripts:

### Standard Commands
```bash
# Health audit of the spreadsheet
mrg-finance doctor --fresh

# Submit bill request to Engage
mrg-finance bill-request --fresh --bill "<Bill Title>" --no-review

# Process purchase request
mrg-finance purchase --fresh --order "<Order ID>" --no-review

# Generate local Excel comparison report
mrg-finance report --fresh --order "<Order ID>"
```

### Global Installation & Package Updates
Whenever making changes to the CLI or package dependencies:
```bash
# 1. Verify syntax across all modules
uv run python -m py_compile mrg.py automation_purchase.py automation.py spreadsheet_utils.py share_a_cart.py

# 2. Run unit tests
uv run pytest tests/

# 3. Bump patch version in pyproject.toml
# 4. Force-reinstall globally for the user
uv tool install --force .
```

---

## 🛡️ 5. Critical Agent Guardrails & Failure Modes

Past regressions documented in `agent_changes.md` reveal critical traps agents must avoid:

1. **The `startswith("")` Trap**:
   Never include empty strings `""` in filter tuples evaluated with `.startswith()`. In Python, `'AnyString'.startswith("")` is always `True` and will silently purge all valid data.
2. **Dynamic Spreadsheet Path Resolution**:
   Never hardcode file paths like `~/Library/CloudStorage/...`. Always resolve paths through the unified hierarchy (`--excel-path` → `FINANCE_XLSX_PATH` → CWD → Repo → OneDrive). Forward `--excel-path` in all subprocess calls.
3. **Punctuation Sanitization in Filenames**:
   When matching screenshot filenames, use alphanumeric normalization (`re.sub(r'[^a-zA-Z0-9]+', '', name)`). Dots (e.g., `m2.5`) are often sanitized to underscores (`m2_5.png`), which will fail exact substring string checks.
4. **Duo MFA Redirect Handling**:
   Never use raw `EC.url_contains` during login redirects, as `driver.current_url` can momentarily return `None`, throwing a fatal `TypeError`. Always use a null-safe lambda: `lambda d: bool(d.current_url and "..." in d.current_url)`.
5. **rclone Zero-Overwrite Sync**:
   Always pass `--ignore-checksum --ignore-size --update` when executing `rclone copy` to prevent file corruption or duplicate overwrite loops on SharePoint.
