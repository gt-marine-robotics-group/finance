# ⚓ MRG Finance & Purchasing System

Bill request automation, order management, price checking, and purchasing workflow for the **Georgia Tech Marine Robotics Group**.

---

## ⚡ Local Computer Setup & Quick Start (macOS / Linux / Windows)

### 1. Install CLI Tool Globally (`mrg-finance`)

**Prerequisites**: Python 3.10+ and `uv`.
- **macOS / Linux / WSL**: `curl -LsSf https://astral.sh/uv/install.sh | sh` *(or `brew install uv`)*
- **Windows (PowerShell)**: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

```bash
# Clone the repository
git clone git@github.com:gt-marine-robotics-group/finance.git
cd finance

# Install mrg-finance CLI globally via uv
uv tool install .
```

### 2. Primary CLI Commands

```bash
# 1. Submit Bill Request to Engage (interactive)
mrg-finance bill-request --fresh

# 2. Submit Purchase Request to Engage (interactive)
mrg-finance purchase --fresh

# 3. Headless price check & budget overrun audit
mrg-finance price-check --bill "FY27 Budget" --cart
```

### 3. Run Web App Dashboard Locally

```bash
# Create virtual environment
uv venv

# Activate virtual environment:
# - macOS / Linux / WSL:  source .venv/bin/activate
# - Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# - Windows CMD:         .venv\Scripts\activate.bat
source .venv/bin/activate

# Install web app dependencies
uv pip install -r requirements.txt

# Start local web app server
python3 web-app/app.py   # On Windows: python web-app/app.py
```

Open **`http://localhost:5000`** in your browser:
- **Login Password**: `boats0519`
- **User Name**: Your Name / GT ID *(e.g. `gburdell3`)*

---

### 📄 Working Offline with a Local Excel File

If you prefer to manually download and edit the spreadsheet locally instead of using cloud sync:

1. **Download Spreadsheet**: Download the master Excel file from SharePoint (`OPS-1 Operations/FY27 Finances`).
2. **Repository Target Path & Name**: Save the file directly in the repository root directory:
   - **Target Location**: `finance/FY27_Bills_Budget.xlsx`
   - **Exact Filename**: **`FY27_Bills_Budget.xlsx`** *(case-sensitive)*
3. **Execute Locally (Without `--fresh`)**:
   ```bash
   mrg-finance purchase      # Reads local FY27_Bills_Budget.xlsx file directly
   mrg-finance price-check   # Reads local FY27_Bills_Budget.xlsx file directly
   ```

---

### 4. ☁️ SharePoint & Screenshot Sync Setup (`rclone`)

Screenshots are synced directly with the team's shared **GT OneDrive / SharePoint** folder (and kept out of Git to keep the repository lightweight).

To enable automatic screenshot & `.xlsx` syncing on your computer:

1. **Install `rclone`**:
   - **macOS**: `brew install rclone`
   - **Linux**: `sudo apt install rclone`
   - **Windows**: `winget install rclone.rclone` *(or in PowerShell: `choco install rclone`)*

2. **Configure GT OneDrive Remote (Step-by-Step Prompt Walkthrough)**:
   Run `rclone config` in your terminal and follow this exact key sequence:
   - `e/n/d/r/c/s/q>` $\rightarrow$ Type **`n`** *(New remote)*
   - `name>` $\rightarrow$ Type **`onedrive`** *(Must be exactly `onedrive` in lowercase!)*
   - `Storage>` $\rightarrow$ Type **`42`** *(Microsoft OneDrive)*
   - `client_id>` $\rightarrow$ Press **Enter** *(Leave blank)*
   - `client_secret>` $\rightarrow$ Press **Enter** *(Leave blank)*
   - `region>` $\rightarrow$ Press **Enter** *(Default `1 / global`)*
   - `Edit advanced config?` $\rightarrow$ Type **`n`**
   - `Use web browser to authenticate?` $\rightarrow$ Type **`y`**
   - **Browser Pop-up**: Log in with your **Georgia Tech SSO (`<username>@gatech.edu`) + Duo MFA** and click Accept.
   - `Choose a number from 1 to 6 >` $\rightarrow$ Type **`1`** *(OneDrive Personal or Business)*
   - `Chose drive to use:>` $\rightarrow$ Type **`0`** *(OneDrive Business)*
   - `Is that OK?` $\rightarrow$ Type **`y`**
   - Main Menu $\rightarrow$ Type **`q`** to quit.

3. **Verify Configuration**:
   ```bash
   rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
   ```

4. **How Syncing Works**:
   - **Download Sync**: `mrg-finance --fresh` downloads the latest `.xlsx` and team screenshots from SharePoint.
   - **Upload Sync**: `mrg-finance screenshots` automatically uploads newly captured screenshots to SharePoint (`onedrive:OPS-1 Operations/FY27 Finances/screenshots/`).

---

## 🛡️ Built-In System Reliability & Safeguards

The system is designed with **5 strict technical safeguards** to prevent accidental mistakes or budget overruns:

1. **🚫 Zero File Deletions (`rclone copy`)**: Syncing strictly uses `rclone copy --checksum` (never `rclone sync`). It **only adds missing files** and never deletes existing remote or local screenshots.
2. **🔒 Duplicate Order Protection**: Items marked `pending purchase` or listed on `OrderT` are strictly locked. The web UI disables selection and the backend rejects duplicate submissions.
3. **🛡️ Ground-Truth Screenshot Protection**: Existing bill submission screenshots are permanently preserved and never overwritten automatically when taking screenshots.
4. **🛑 Read-Only Instructions & Quantity Caps**: Order forms enforce maximum quantity caps based on SOFO approval, and vendor `Ordering Instructions` are read-only to prevent accidental edits.
5. **🩹 Graceful `rclone` Fallback**: If `rclone` is not installed or configured, the system output displays a notice and operates locally without crashing.

---

## 🤖 CLI Commands & Options Reference (`mrg-finance`)

### 🛡️ Screenshot Overwrite Policy
> **Does the `screenshots` command overwrite old screenshots?**  
> **NO.** Original ground-truth bill screenshots stored in `screenshots/<bill_title>/<item_name>.png` are **permanently preserved** and never overwritten automatically.  
> - **Bill Requests**: The script audits existing files and only captures screenshots for items that are missing images.  
> - **Order Reviews**: Live price audit captures during `mrg-finance purchase` are isolated in `screenshots/_order_<order_id>/` so original bill submission evidence is never touched.  
> - **Manual Re-take**: Officers can intentionally force re-capturing individual item screenshots via the web page **`📸`** buttons or `/bill/<bill_title>` header actions.

---

### 📋 Full Command & Option Reference

#### 1. `mrg-finance bill-request`
Automates bill submission on CampusLabs Engage.
- **Options**:
  - `-f`, `--fresh`: Pull a fresh copy of the budget `.xlsx` from SharePoint/OneDrive via `rclone` before running.
- **Workflow**:
  1. Prompts for interactive bill selection.
  2. Runs a missing screenshot audit. Prompts to capture any missing item screenshots via headless Chrome.
  3. Launches the Web Review Page (`http://localhost:5000/review/<bill_title>`) in your default browser.
  4. Pre-fills CampusLabs Engage form fields and pauses for officer inspection before final submission.
- **Example**:
  ```bash
  mrg-finance bill-request --fresh
  ```

#### 2. `mrg-finance purchase`
Automates purchase request submissions on CampusLabs Engage.
- **Options**:
  - `-f`, `--fresh`: Pull a fresh copy of the budget `.xlsx` from SharePoint/OneDrive via `rclone` before running.
  - `-o`, `--order <ORDER_ID>`: Specify an Order ID directly (skips interactive order selection).
- **Workflow**:
  1. Prompts to select an Order ID from `OrderT` (or fallback by Bill Title).
  2. Prompts to run a live price check audit.
  3. Displays live price comparison table with budget overrun alerts (`+$XX.XX`).
  4. Auto-generates 1-Click Amazon Multi-Item Cart link (or displays non-Amazon vendor cart warning).
  5. Auto-opens Side-by-Side Order Review window (`http://localhost:5000/orders/review/<order_id>`).
  6. Launches Engage purchase request pre-filling with GT SSO + Duo MFA.
- **Example**:
  ```bash
  mrg-finance purchase --fresh --order "260811_amazon_awu335"
  ```

#### 3. `mrg-finance price-check`
Runs a headless online price check against product links.
- **Options**:
  - `-f`, `--fresh`: Pull a fresh copy of the budget `.xlsx` from SharePoint/OneDrive via `rclone` before running.
  - `-b`, `--bill <TITLE>`: Specify a Bill Title directly (skips interactive selection).
  - `-c`, `--cart`: Automatically generate and prompt to open the 1-Click Amazon Multi-Item Cart URL.
- **Workflow**:
  1. Scrapes live prices from product links via headless Chrome.
  2. Compares live price vs approved bill allocation cost in a terminal table.
  3. Flags budget overruns (`+$XX.XX OVER BUDGET`) or savings.
  4. Auto-builds 1-Click Amazon Cart link and offers to launch it in your browser.
- **Example**:
  ```bash
  mrg-finance price-check --fresh --bill "FY27 Budget" --cart
  ```

#### 4. `mrg-finance screenshots`
Scrapes live product prices and captures headless Chrome screenshots for bill items.
- **Options**:
  - `-f`, `--fresh`: Pull a fresh copy of the budget `.xlsx` from SharePoint/OneDrive via `rclone` before running.
  - `-b`, `--bill <TITLE>`: Specify a Bill Title directly (skips interactive selection).
- **Workflow**:
  1. Scrapes current prices and takes full-page product screenshots.
  2. Saves screenshots to `screenshots/<bill_title>/<item_name>.png`.
  3. Existing screenshots are strictly preserved and **never overwritten**.
- **Example**:
  ```bash
  mrg-finance screenshots --fresh --bill "FY27 Budget"
  ```

---

## 📚 Advanced Documentation & Technical Reference

<details>
<summary><strong>1. 👤 Team Member Guide (Adding Items)</strong></summary>

1. Open Web App (`http://localhost:5000` or SIM PC IP). Log in with team credentials (`boats0519`).
2. Use the **Quick-Add Bar** on the dashboard (`Item Name`, `Qty`, `Link`).
3. Paste an item link — vendor and price auto-fill in the background.
</details>

<details>
<summary><strong>2. 👮 Officer Guide (Bill Management & Immutability)</strong></summary>

1. **Dashboard (`/`)**: View backlog items and active bill cards.
2. **Review Bill (`/review/<bill_title>`)**: Swipe through item cards, verify links, and inspect pre-captured screenshots.
3. **Inline Bill Editing (`/bill/<bill_title>`)**: Edit item names, costs, quantities, and vendors directly in the bill table, or click **`📸 Take All Screenshots`**.
4. **🔒 Locked Bills**: Approved or submitted bills (`bill submitted`, `bill approved`, `purchased...`) are read-only to protect audit records.
</details>

<details>
<summary><strong>3. 🛒 Purchasing Officer Guide (Order Creation & Review)</strong></summary>

1. **Create Order (`/create-order`)**: Group approved bill items by vendor, select custom quantities (capped at approved bill max), and generate 1-click **Amazon Cart URLs**.
2. **Side-by-Side Order Review (`/orders/review/<order_id>`)**: Compare original bill screenshots & allocated prices (left) against newly scraped live prices & screenshots (right) with budget overrun alert badges (`+$XX.XX`).
3. **Order Management (`/orders`)**: Edit order line items or delete orders without leaving empty Excel title headers.
</details>

<details>
<summary><strong>4. 📋 Status Lifecycle Reference</strong></summary>

| Status | Meaning |
| :--- | :--- |
| `review requested` | Newly added item awaiting officer review |
| `bill requested` | Grouped into a bill, waiting for submission |
| `bill submitted` | Submitted to CampusLabs Engage (🔒 Bill Locked) |
| `bill approved` | Approved by SOFO/CampusLabs — ready to order (🔒 Bill Locked) |
| `pending purchase` | Added to an order on `OrderT` |
| `purchased - SOFO` | Purchased using SOFO card |
| `purchased - cash` | Purchased with personal funds |
| `purchased - awaiting reimbursement` | Purchased, waiting for reimbursement |
| `arrived` | Item received by team |
</details>

<details>
<summary><strong>5. ⚙️ Systemd Service & Server Management</strong></summary>

The production web app runs as `mrg-web-app.service` on SIM PC (`CPUQuota=25%`, `Nice=10`, `MemoryMax=512M`):

```bash
sudo systemctl status mrg-web-app   # Check status
sudo systemctl restart mrg-web-app  # Restart service
journalctl -u mrg-web-app -f        # View live logs
```
</details>

<details>
<summary><strong>6. 🧪 Testing & Quality Assurance</strong></summary>

```bash
source .venv/bin/activate
pytest tests/ -v
```
</details>
