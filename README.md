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

### 🛠️ Supporting Feature: Spreadsheet Item Management & Web GUI
- **Purpose**: Easily add, edit, and review items in `FY27_Bills_Budget.xlsx`.
- **GUI Tools**:
  - **Side-by-Side Inspector (`http://localhost:8321`)**: Visually compare baseline bill screenshots against current live scraped prices.
  - **Web Dashboard (`http://localhost:5000`)**: Full Flask web interface to paste product URLs, auto-scrape vendor details, and manage orders.

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
```bash
pipx install git+https://github.com/gt-marine-robotics-group/finance.git
```
*After running this once, `mrg purchase`, `mrg bill-request`, and `mrg doctor` work system-wide in any terminal window!*

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

After installation, the CLI is available as `mrg` (or `mrg-finance`).

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

## 🤖 CLI Usage & Workflows (`mrg` / `mrg-finance`)

The `mrg` CLI tool provides end-to-end automation for price scraping, side-by-side screenshot verification, bill submissions, and purchase tracking.

```
Usage:
    mrg doctor [--fresh]
    mrg bill-request [--fresh]
    mrg purchase [--fresh] [--order ORDER_ID]
    mrg review [--bill TITLE]
    mrg price-check [--fresh] [--bill TITLE]
    mrg screenshots [--fresh] [--bill TITLE] [--review-only]

Commands:
    doctor          Run pre-flight health audit on FY27_Bills_Budget.xlsx
    bill-request    Submit a bill request to CampusLabs Engage (Priority 1)
    purchase        Submit purchase requests to Engage (Priority 2)
    review          Launch side-by-side screenshot & price review GUI
    price-check     Check live prices vs budget allocation & warn on overrun
    screenshots     Scrape prices + capture full-page screenshots for a bill
```

---

### 1. `mrg review` — Instant Side-by-Side Review

Launches the interactive side-by-side screenshot & price review GUI in your default browser **without running web scraping or opening Chrome automation**.

```bash
# Prompt to select a bill:
mrg review

# Or specify a bill directly:
mrg review --bill "Marine Robotics Group RobotX Testing Equipment Bill"
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
