# ⚓ MRG Finance & Purchasing System

Bill request automation, order management, price checking, and purchasing workflow for the **Georgia Tech Marine Robotics Group**.

---

## ⚡ Quick Start

```bash
# 1. Install mrg-finance CLI globally via uv
uv tool install .

# 2. Or install in editable dev mode
uv pip install -e .

# 3. Primary Officer Command: Submit Bill Request to Engage
mrg-finance bill-request --fresh

# 4. Submit Purchase Request to Engage
mrg-finance purchase --fresh
```

---

## 🚀 Core Features

- **🌐 Web App (`http://<sim-pc-ip>:5000`)**: Dashboard, item queue, inline bill editing, vendor order creation, and side-by-side screenshot comparisons.
- **🤖 Engage CLI Automation (`mrg-finance`)**: `uv`-installable CLI with Selenium scripts for CampusLabs Engage bill & purchase request submissions with GT SSO + Duo MFA.
- **🛡️ Ground-Truth Protection**: Original bill screenshots (`screenshots/<bill_title>/`) are permanently preserved and never overwritten.

---

## 📖 Complete Documentation & Guides

<details>
<summary><strong>1. 👤 Team Member Guide (Adding Items)</strong></summary>

1. Open Web App (`http://<sim-pc-ip>:5000`). Log in with team credentials (`boats0519`).
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
<summary><strong>4. 🤖 CLI Commands Reference (`mrg-finance`)</strong></summary>

- `mrg-finance bill-request --fresh`: Interactive bill selection, screenshot audit/capture, web review window launch, and CampusLabs Engage submission.
- `mrg-finance purchase --fresh`: Interactive live price check, web order review launch, and Engage purchase request submission.
- `mrg-finance price-check`: Headless live price check comparing online prices vs approved allocations.
- `mrg-finance screenshots`: Batch pre-capturing item screenshots.
</details>

<details>
<summary><strong>5. 📋 Status Lifecycle Reference</strong></summary>

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
<summary><strong>6. ⚙️ Systemd Service & Server Management</strong></summary>

The web app runs as `mrg-web-app.service` on SIM PC (`CPUQuota=25%`, `Nice=10`, `MemoryMax=512M`):

```bash
sudo systemctl status mrg-web-app   # Check status
sudo systemctl restart mrg-web-app  # Restart service
journalctl -u mrg-web-app -f        # View live logs
```
</details>

<details>
<summary><strong>7. 🧪 Testing & Quality Assurance</strong></summary>

```bash
source .venv/bin/activate
pytest tests/ -v
```
</details>
