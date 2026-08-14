# 📘 Georgia Tech MRG Finance & Purchasing — Student & Developer Usage Guide

Welcome to the **Marine Robotics Group (MRG) Finance & Purchasing System**! This application has **two primary priority functions** plus an interactive management GUI:

---

## 🌟 The Two Core Priority Functions

### 1️⃣ Priority 1: Submit Bill Requests (`mrg-finance bill-request` / `automation.py`)
- **Purpose**: Submits new draft budget bills to Georgia Tech CampusLabs Engage for SGA approval.
- **Features**: Groups line items by budget section, verifies screenshot evidence for every item, and pre-fills the Engage bill form automatically.

### 2️⃣ Priority 2: Submit Purchase Requests (`mrg-finance purchase` / `automation_purchase.py`)
- **Purpose**: Submits purchase requests to CampusLabs Engage for approved items ready to be ordered.
- **Features**: Groups order items by vendor, checks live prices vs approved budget allocations, auto-adds items to Amazon carts, captures `cart.png` evidence, resolves exact live section & line numbers on Engage, and pre-fills the purchase request form.

---

### 🛠️ Supporting Feature: Spreadsheet Item Management & Web GUI
- **Purpose**: Easily add, edit, and review items in `FY27_Bills_Budget.xlsx`.
- **GUI Tools**:
  - **Side-by-Side Inspector (`http://localhost:8321`)**: Visually compare baseline bill screenshots against current live scraped prices.
  - **Web Dashboard (`http://localhost:5000`)**: Full Flask web interface to paste product URLs, auto-scrape vendor details, and manage orders.

---

## 🌐 1-Step Global CLI Installation (Use Anywhere!)

This repository exclusively uses [`uv`](https://docs.astral.sh/uv/getting-started/installation/) as the package manager.

```bash
uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
```
*Now typing `mrg-finance purchase`, `mrg-finance bill-request`, or `mrg-finance doctor` works system-wide in any terminal window!*

*(For local editable setup, run `git clone git@github.com:gt-marine-robotics-group/finance.git && cd finance && uv venv && source .venv/bin/activate && uv pip install -e .`)*

---

## 🚀 5-Minute Quick Start Guide for Students

Follow these steps to set up your Mac or PC:

### Step 1: Open Terminal & Clone Repository
```bash
git clone git@github.com:gt-marine-robotics-group/finance.git
cd finance
```

### Step 2: Create Python Environment
Make sure you have **Python 3.10+** installed:
```bash
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Step 3: Configure SharePoint Sync (`rclone`)
Screenshots and master Excel files are synced from GT SharePoint via `rclone`.
```bash
# Install rclone (macOS: brew install rclone)
rclone config
```
When prompted by `rclone config`:
1. Type `n` *(New remote)*
2. Name: `onedrive` *(Must be lowercase `onedrive`)*
3. Storage: `42` *(Microsoft OneDrive)*
4. Leave `client_id` / `client_secret` blank (press Enter)
5. Web Browser Auth: Log in with your **`<username>@gatech.edu` SSO + Duo MFA**.
6. `config_type`: Type `3` *(SharePoint site)*
7. Site URL: `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`
8. `config_driveid`: Type `3` *(Documents)*
9. Confirm with `y`, then quit with `q`.

Test your connection:
```bash
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
```

> ⚠️ **WARNING / IMPORTANT**:
> Configuring `rclone` to sync GT OneDrive / SharePoint involves multi-factor authentication (GT SSO + Duo MFA) and specific remote settings. If you encounter any issues during this configuration step, **ask a finance officer or team lead for help**!

---

## 🩺 Pre-Flight Spreadsheet Diagnostic (`mrg-finance doctor`)

Before submitting bills or purchase requests, run **`mrg-finance doctor`** to run a diagnostic health audit on `FY27_Bills_Budget.xlsx`:

```bash
# Audit local spreadsheet:
mrg-finance doctor

# Pull fresh copy from SharePoint & audit:
mrg-finance doctor --fresh
```

**What `mrg-finance doctor` checks**:
- 🔍 **Duplicate Bill Item IDs**: Flags duplicate ID numbers that would cause item misalignments.
- 🔗 **Broken / Unlinked References**: Identifies Order rows referencing non-existent Bill Item IDs.
- 🌐 **Invalid Links**: Highlights items missing URLs or containing incomplete link strings (e.g. `jlcpcb.com` missing `https://`).
- 💰 **Zero / Invalid Costs**: Warns on items with missing or `$0.00` cost allocations.

---

## 🛒 Common Student Workflows

All commands are executed via the `mrg-finance` CLI executable:

### 1. Submit a Purchase Request (`mrg-finance purchase`)
Use this when you are placing an order for items approved on a bill.

```bash
# Pull fresh spreadsheet from SharePoint & start purchase flow:
mrg-finance purchase --fresh
```

**What happens**:
1. Prompts for your GT username & Duo MFA.
2. Select an Order ID from the list.
3. Checks live online prices and flags any overruns (e.g. price increased since bill approval).
4. **Generates an Amazon Multi-Item Cart Link**:
   - Offers to open the cart link in **Incognito Chrome** (recommended so you don't need to be signed into any personal Amazon account).
   - Click "Continue" on Amazon to add all order items to your cart automatically.
5. Auto-generates the **Budget vs Quoted Detail Report** (`Budget_vs_Quoted_Detail_<order_id>.xlsx`) with live formulas (`=E*F`, `=SUM(...)`).
6. Pre-fills the Engage Purchase Request form fields and attaches the **two mandatory backup documents**:
   - 📸 **Upload #1**: Cart Screenshot (`cart.png`).
   - 📗 **Upload #2**: Budget vs Quoted Detail Report (`Budget_vs_Quoted_Detail_<order_id>.xlsx`).
7. ⚠️ **Final Action Required**: Review the pre-filled form in Chrome and click **"Submit"** on CampusLabs Engage to finalize the request!

---

### 2. Submit a New Bill to Engage (`mrg-finance bill-request`)
Use this when submitting a newly drafted bill to CampusLabs Engage for SGA approval.

```bash
mrg-finance bill-request --fresh
```

**What happens**:
1. Scrapes prices and verifies screenshot evidence images for every line item.
2. Opens the side-by-side inspector to review items before submission.
3. Logs into Engage and populates each budget section automatically.

---

### 3. Review Prices & Screenshots (`mrg-finance review`)
Use this to open the side-by-side review GUI without running browser automation.

```bash
mrg-finance review
```

Open **`http://127.0.0.1:8321`** in your browser to inspect line items, view baseline vs scraped screenshots, edit prices, and click **`💾 Save Prices`** to update the spreadsheet.

---

## 🛒 Amazon Multi-Item Cart Links (Incognito Mode)

When placing Amazon orders, the system automatically builds a single multi-item cart URL:

```text
🛒 Amazon Multi-Item Cart Link Generated (14 item(s)):
   https://www.amazon.com/gp/aws/cart/add.html?ASIN.1=...&Quantity.1=6...

Options to open cart:
  1. Open in Incognito Chrome (Recommended — No Amazon login required)
  2. Open in Default Browser
  3. Skip opening
```

- **Why Incognito Chrome?**: Allows any student to open the cart and generate a cart screenshot without needing to log into Amazon.
- **How Amazon Cart Links Work**: Uses Amazon's AWS add-to-cart API (`ASIN.x` and `Quantity.x`). Clicking "Continue" on the Amazon landing page pre-fills your Amazon cart with all items in the order at once.

---

## 📸 Manual Screenshot Naming Guide

If you take or add screenshot files manually, save them to:
```
screenshots/<Bill Title>/<Item Name>.png
```

### Flexible File Recognition:
The system uses a flexible matching algorithm (`_find_file_in_dir`), so manual files are recognized even with minor differences:
1. **Whitespace & Case Insensitive**: `Small Rope.PNG` matches `small rope`.
2. **Punctuation Sanitized**: `2m IP67 LED Strip (144LED_m).png` matches `2m IP67 LED Strip (144LED/m)`.
3. **Supported Formats**: `.png`, `.jpg`, `.jpeg`, `.webp`.

---

## 💻 Novice Developer Code Map

If you want to modify or add features to this repository, here is how the codebase is structured:

```
finance/
├── automation_purchase.py   # Purchase request submission flow & Amazon cart launcher
├── engage_bill_lookup.py    # Engage DOM scraper (finds section titles & line numbers)
├── automation.py            # Bill request submission flow & item creation logic
├── automation_screenshots.py# Price scraper integration & review HTML generator
├── price_scraper.py         # Live price scraping (Amazon, McMaster, etc.) & ASIN parser
├── review_server.py         # Local HTTP server (port 8321) for saving price edits to Excel
├── review.html              # Side-by-side screenshot review GUI
├── mrg.py                   # CLI entrypoint for `mrg-finance` commands
└── web-app/                 # Flask web dashboard (http://localhost:5000)
```

### Key Functions to Know:
- **`lookup_bill_item_locations()`** in [`engage_bill_lookup.py`](file:///Users/aaronwu/mrg/finance/engage_bill_lookup.py):
  Navigates to an Engage bill URL, clicks the "Budget" tab, traverses section headers (`h4.groupTitle`), and returns `{item_name: {section, section_line_number}}`.
- **`generate_amazon_cart_url()`** in [`price_scraper.py`](file:///Users/aaronwu/mrg/finance/price_scraper.py):
  Parses Amazon URLs for ASINs (`/dp/B0...`) and builds the AWS cart URL.
- **`_open_incognito_browser()`** in [`automation_purchase.py`](file:///Users/aaronwu/mrg/finance/automation_purchase.py):
  Launches Chrome in `--incognito` mode across macOS, Linux, and Windows.

---

## ❓ Troubleshooting & FAQs

#### Q: Duo MFA timed out or browser closed early?
Re-run the command (`python3 automation_purchase.py`). The script gives you 180 seconds to complete Duo MFA on your phone.

#### Q: An item price changed or is wrong on the Review GUI?
Edit the price in the text box on `http://127.0.0.1:8321` and click **`💾 Save Prices`**. It will update the master Excel file automatically.

#### Q: `rclone` gives an error or won't sync?
Run `rclone config reconnect onedrive:` to re-authenticate your GT SSO credentials.
