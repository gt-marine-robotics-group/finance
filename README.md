# MRG Finance

Everything starts in the shared spreadsheet: **[FY27_Bills_Budget.xlsx on SharePoint](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)** (sign in with your GT account).

---

## 📋 Step-by-Step Guide

### Step 1: Request Funding (`Bills` sheet)
> *Do this when you want SGA to approve budget for future purchases.*

1. Open the **`Bills`** sheet.
2. Group your items under a shared **`Bill Title`** (e.g., `RobotX Equipment Bill`).
3. Fill in: `Item Name`, `Vendor`, unit `Cost`, `Quantity`, product `Link`, `Budget Section` (`B03` for equipment/tools, `B06` for supplies), and `Person Requesting`.
4. **Do not edit `Bill Item ID` or `Total Cost`** — Excel calculates these automatically.
5. Submit the draft on [MRG Budgeting in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting).
6. Once SGA approves the bill, write the official **`Bill No.`** on all your item rows.

---

### Step 2: Order Items (`Ordering` sheet)
> *Do this when you are ready to purchase items with approved funding.*

1. Open the **`Ordering`** sheet (headers are on row 2, data starts on row 3).
2. Create an **`Order ID`**: `YYMMDD_vendor_gtusername` (e.g., `260910_amazon_gburdell3`). Enter this on every row in this cart.
3. **Copy the `Bill Item ID`** from the `Bills` sheet and paste it into Column B (`Bill Item ID`).
   - Excel formulas will automatically pull the Item Name, Vendor, Cost, and Bill info. **Do not type into these columns!**
4. Fill in: `Quantity` (how many you are ordering now), `Purchaser`, and `Status` (`Pending`).

---

### Step 3: Submit the Purchase Request

Choose **Option A** (manual) or **Option B** (automated CLI):

#### Option A: Submit Manually (No install needed)
1. Add items to your cart on the vendor site and take a screenshot (`cart.png`).
2. Open [Create Purchase Request in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest).
3. Fill in vendor, amount, funding account, and approved SGA bill & line numbers.
4. Attach `cart.png` and a price comparison spreadsheet, sign, and submit.
5. On the `Ordering` sheet, paste the submitted URL into **`Engage Request Link`** (Col V) and any cart link into **`Share-A-Cart Link`** (Col U) on all rows for that order.

#### Option B: Use the Automated CLI
1. Check your spreadsheet:
   ```bash
   mrg-finance doctor --fresh
   ```
2. Submit a bill draft:
   ```bash
   mrg-finance bill-request --fresh
   ```
3. Process a purchase order:
   ```bash
   mrg-finance purchase --fresh
   ```
   *(Press Enter in the terminal only after clicking Submit on Engage so it saves your links back to SharePoint).*

---

## 💻 Optional: Install the CLI

```bash
# macOS / Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git

# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex
uv tool install --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
```
Reopen your terminal and verify with `mrg-finance --help`.

---

## 📚 Detailed Reference Guides

- [Spreadsheet & Manual Workflow Guide](docs/user/WORKFLOW_GUIDE.md) — Complete schema, formulas, and Engage form reference.
- [CLI & Troubleshooting Guide](docs/user/CLI_GUIDE.md) — Detailed rclone setup, commands, and common error fixes.
- [Developer & Web App Guide](docs/dev/DEVELOPMENT.md) — System architecture, SIM PC deployment, and Graph API.
