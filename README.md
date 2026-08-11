# ⚓ MRG Finance & Purchasing System

Comprehensive bill request automation, order management, price checking, and purchasing workflow for the **Georgia Tech Marine Robotics Group**.

---

## 🚀 System Architecture

```text
┌───────────────────────────┐      Graph API (OAuth2)      ┌───────────────────────────┐
│     Flask Web Application │ <──────────────────────────> │   SharePoint / OneDrive   │
│  (Gunicorn WSGI / Systemd)│                              │ (FY27_Bills_Budget.xlsx)  │
└─────────────┬─────────────┘                              └─────────────┬─────────────┘
              │                                                          │
              │  Local Cache / Sync                                      │  rclone sync
              ▼                                                          ▼
┌───────────────────────────┐                              ┌───────────────────────────┐
│  Headless Price Scraper & │                              │ CLI Automation Scripts    │
│   Screenshot Background   │                              │ (CampusLabs Engage / Duo) │
└───────────────────────────┘                              └───────────────────────────┘
```

The system combines a Flask web interface running on the team SIM PC with Microsoft Graph API integration, automated price scrapers, and CLI Selenium scripts for CampusLabs Engage purchasing.

---

## 👥 User Guides

### 1. For Team Members (Adding Purchasing Requests)
1. **Access Web App**: Open `http://<sim-pc-ip>:5000` (or via Tailscale).
2. **Login**: Enter username and team password (`boats0519`).
3. **Add Items**: Use the **Quick-Add Bar** on the dashboard or click **"+ Add Item"** for full details.
4. **Paste Link**: Provide a product URL — vendor and live price will auto-fill in the background.

---

### 2. For Officers (Bill Management & Approvals)
1. **Dashboard Overview (`/`)**: View backlog items and active bills grouped by request.
2. **Review Bill (`/review/<bill_title>`)**: Use the **Review Bill** button directly on the dashboard to swipe through item cards, verify links, and inspect pre-captured screenshots.
3. **Add Item to Bill (`+ Add Item`)**: Open any active draft bill and click **`+ Add Item`** to add line items directly to that bill.
4. **🔒 Immutable Approved Bills**: Once a bill is submitted or approved (`bill submitted`, `bill approved`, `purchased...`), the system locks it as **Read-Only**. All edit, delete, and add-item actions are disabled to protect audit records.

---

### 3. For Purchasing Officers (Order Creation & Review)

1. **Create Order (`/create-order`)**:
   - Group approved bill items by vendor.
   - Adjust quantities per item (strictly capped at approved bill maximums).
   - Click **Create Order** to append non-formula input cells to `OrderT` without modifying Excel VLOOKUP formulas.
   - Click **Open Amazon Multi-Item Cart** for 1-click team checkout.

2. **Side-by-Side Order Review (`/orders/review/<order_id>`)**:
   - Click **`Review Order`** to open the side-by-side comparison page.
   - **Left Column**: Displays the **Original Ground-Truth Bill Screenshot** & approved allocation price.
   - **Right Column**: Displays the **Newly Scraped Live Price & Screenshot**.
   - **Price Delta Badges**: Automatically highlights budget overruns (`+$XX.XX OVER BUDGET`) or savings.

3. **Editing & Deleting Orders (`/orders`)**:
   - Batch edit order vendor/purchaser/status or edit individual line items.
   - Deleting an order automatically cleans up its `Order N` title header row from `OrderT` to prevent duplicate/orphaned headers.

---

## 🤖 CLI Automation & Engage Submissions

Officers running purchase automation from their laptops interface directly with CampusLabs Engage via CLI scripts:

### Submit Automated Purchase Request
```bash
python3 mrg.py purchase --fresh
```
- Syncs fresh `FY27_Bills_Budget.xlsx` and screenshots from SharePoint.
- Automatically launches the **Web Order Review window** in your browser for side-by-side audit.
- Uses Selenium Chrome to populate line items, quantities, unit costs, and screenshots on CampusLabs Engage.
- Waits for Duo MFA confirmation from the officer.

### CLI Price Check
```bash
python3 mrg.py price-check
```
- Performs a terminal price check comparing live online prices vs approved allocations.

### Pre-capture Screenshots
```bash
python3 mrg.py screenshots
```
- Captures item page screenshots into `screenshots/<bill_title>/`.

---

## 🛡️ Ground-Truth Screenshot Protection

Original screenshots captured during bill requests serve as **permanent audit ground truth**:
1. **Folder Separation**: Bill screenshots (`screenshots/<bill_title>/`) are isolated from live order review captures (`screenshots/_order_<order_id>/`).
2. **Existence Protection**: `screenshot_worker.py` and `mrg.py` check if `os.path.exists(filepath)` and skip re-taking screenshots unless `--force` or `overwrite=True` is explicitly passed.
3. **Lock Protection**: Approved bills (`is_locked=True`) block re-triggering screenshots.

---

## 📋 Status Lifecycle Reference

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

---

## ⚙️ Service & Systemd Management

The web app runs as a systemd service (`mrg-web-app.service`) on SIM PC under strict resource limits (`CPUQuota=25%`, `Nice=10`, `MemoryMax=512M`):

```bash
# Check status
sudo systemctl status mrg-web-app

# Restart service after updates
sudo systemctl restart mrg-web-app

# View logs
journalctl -u mrg-web-app -f
```

---

## 🧪 Testing & Quality Assurance

Run the test suite (12 unit tests covering graph API mocking, local openpyxl fallbacks, price scraping, and app routes):

```bash
source .venv/bin/activate
pytest tests/ -v
```
