# 💻 CLI & Troubleshooting Guide

The `mrg-finance` CLI automates screenshot capturing, price validation, comparison Excel report generation, Share-A-Cart links, and CampusLabs Engage form submission.

---

## 🚀 1. Installation & Setup

### Prerequisites
- [Git](https://git-scm.com/downloads)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (fast Python package and environment manager)

### One-Line Install
```bash
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
uv tool update-shell

# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex
uv tool install --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
uv tool update-shell
```

Reopen your terminal and verify the installation:
```bash
mrg-finance --help
```

To update to the latest code at any time:
```bash
uv tool install --force --refresh --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
```

---

## ☁️ 2. One-Time SharePoint Connection (`rclone`)

Install [rclone](https://rclone.org/install/) to synchronize spreadsheets and screenshots directly with GT SharePoint.

1. In your terminal, run:
   ```bash
   rclone config
   ```
2. Follow these configuration prompts (select items by **name**, not number):
   - Choose **New remote** &rarr; name it `onedrive` (all lowercase).
   - Storage type &rarr; **Microsoft OneDrive** (`onedrive`).
   - Client ID & Secret &rarr; Press Enter to leave at default.
   - Browser authentication &rarr; Complete the GT login and Duo push in your browser.
   - Remote type &rarr; Choose **SharePoint site**.
   - Site URL &rarr; Enter `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`.
   - Document Library &rarr; Select **Documents**.
   - Confirm and quit.
3. Test your connection:
   ```bash
   rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
   ```
   You should see `FY27_Bills_Budget.xlsx`.

---

## 📂 3. Choose a Working Directory

Run all finance operations from a dedicated local folder:

**macOS / Linux:**
```bash
mkdir -p "$HOME/mrg-finance-work"
cd "$HOME/mrg-finance-work"
export FINANCE_XLSX_PATH="$PWD/FY27_Bills_Budget.xlsx"
```

**Windows PowerShell:**
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\mrg-finance-work"
Set-Location "$env:USERPROFILE\mrg-finance-work"
$env:FINANCE_XLSX_PATH = Join-Path (Get-Location).Path "FY27_Bills_Budget.xlsx"
```

Download `FY27_Bills_Budget.xlsx` into this folder, keeping the exact filename. Run `mrg-finance doctor` to confirm the target file is detected properly.

---

## 🛠️ 4. Command Reference

All commands support `--fresh` to pull the latest workbook and screenshots via `rclone` before running.

| Command | Description |
| :--- | :--- |
| `mrg-finance doctor --fresh` | Check workbook readability, formula preservation, duplicate IDs, and broken order links. |
| `mrg-finance bill-request --fresh` | Interactive bill submission to Engage. Select your bill, audit screenshots, and autofill line items. |
| `mrg-finance purchase --fresh` | End-to-end purchase flow: audits prices, opens cart, builds Budget vs Quoted Excel sheet, and autofills Engage form. |
| `mrg-finance report --fresh --order "<Order ID>"` | Generates `Budget_vs_Quoted_Detail_<Order ID>.xlsx` and `.csv` without launching browser automation. |
| `mrg-finance price-check --fresh --bill "<Bill Title>"` | Scrapes live vendor prices for all items in a bill and compares against budgeted amounts. |
| `mrg-finance screenshots --fresh --bill "<Bill Title>"` | Takes headless screenshots for missing item links and uploads to SharePoint. |
| `mrg-finance review --bill "<Bill Title>"` | Launches local split-card review GUI (`http://localhost:8321`) to visually diff screenshots and update prices. |

### Command Flags:
- `--bill "Exact Bill Title"`: Skip the interactive menu and target a specific bill directly.
- `--order "YYMMDD_vendor_gtusername"`: Skip the interactive menu and target a specific order directly.
- `--no-review`: Skip the optional web GUI and proceed immediately to form submission.
- `--excel-path <path>`: Explicit override path to the master `.xlsx` workbook.

---

## 📁 5. Directory Layout for Screenshots & Reports

The CLI maintains this directory structure inside your working directory:

```text
mrg-finance-work/
├── FY27_Bills_Budget.xlsx
└── screenshots/
    ├── <Bill Title>/
    │   ├── Pi Pico.png
    │   └── M2_5 threaded inserts.png
    └── <Order ID>/
        ├── cart.png
        ├── Budget_vs_Quoted_Detail_<Order ID>.xlsx
        └── Budget_vs_Quoted_Detail_<Order ID>.csv
```

---

## 🔍 6. Troubleshooting & FAQ Guide

### ☁️ SharePoint & `rclone` Issues

#### 1. `corrupted on transfer: sizes differ` or `quickxor hashes differ`
- **Cause**: Microsoft SharePoint dynamically re-indexes metadata in `.xlsx` files upon upload, altering file byte size and QuickXor hashes.
- **Solution**: All `mrg-finance` sync commands automatically include `--ignore-checksum --ignore-size --update`. If running manually:
  ```bash
  rclone copy --ignore-checksum --ignore-size --update screenshots "onedrive:OPS-1 Operations/FY27 Finances/screenshots"
  ```

#### 2. Microsoft Graph Token Expired
- **Symptom**: `rclone ls` fails with `token expired` or `oauth error`.
- **Solution**: Reconnect using your GT credentials:
  ```bash
  rclone config reconnect onedrive:
  ```

---

### 🌐 Chrome & Selenium Automation Issues

#### 1. ChromeDriver & Browser Setup
- **Automatic Resolution**: `selenium>=4.27` includes built-in Selenium Manager that automatically locates system Chrome or downloads isolated **Chrome for Testing** binaries across macOS, Windows, and Linux. No manual driver download is required.

#### 2. GT SSO / Duo MFA Timeout
- **Cause**: Duo push notification was not accepted within the 180-second timeout window.
- **Solution**: Keep your phone unlocked and ready to approve the Duo push immediately when running `bill-request` or `purchase`.

#### 3. Engage Form Fallback
- **Cause**: Engage periodically alters question labels or DOM structures.
- **Solution**: The purchase automation looks for specific question headings and automatically dumps unmatched order breakdowns and the Share-A-Cart link into the main **Description** box. If this happens, copy the breakdown lines into the respective form inputs before signing.

---

### 📊 Excel Report & Formula Issues

#### 1. Order Table Lookups Return `#N/A`
- **Cause**: The `Bill Item ID` entered in `Ordering` does not match any entry in `Bills` (or has leading/trailing whitespace).
- **Solution**: Copy the exact value from Column A of `Bills`. Ensure the source bill item exists.

#### 2. Grand Total Double Counting
- **Solution**: `order_excel_builder.py` references individual section subtotal cells rather than a blanket `=SUM(range)`, preventing multi-bill grand total inflation.

---

### 🛠️ Shell & Environment Issues

#### 1. `mrg-finance: command not found`
- **Cause**: The `~/.local/bin` directory is not in your system `$PATH`.
- **Solution**: Run `uv tool update-shell`, then close and reopen your terminal.
