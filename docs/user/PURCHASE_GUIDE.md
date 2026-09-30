# 🛒 Purchase Request Automation Guide (`mrg-finance purchase`)

This guide is the complete step-by-step walkthrough for **`mrg-finance purchase`**. It covers terminal prompts, live price auditing, cost overrun mitigation, cart screenshot capture, Engage bill line lookups, Budget vs Quoted Excel report compilation, mandatory Engage attachments, and automatic link persistence.

---

## 📑 Table of Contents
1. [When to Use This Command](#1-when-to-use-this-command)
2. [Spreadsheet Prerequisites (`Ordering` Sheet)](#2-spreadsheet-prerequisites-ordering-sheet)
3. [Running the Command](#3-running-the-command)
4. [Step-by-Step Interactive Terminal Walkthrough](#4-step-by-step-interactive-terminal-walkthrough)
   - [Phase 1: Order Selection](#phase-1-order-selection)
   - [Phase 2: Live Price Auditing & Overrun Mitigation](#phase-2-live-price-auditing--overrun-mitigation)
   - [Phase 3: Seller Quantity Limits & Cart Generation](#phase-3-seller-quantity-limits--cart-generation)
   - [Phase 4: Side-by-Side Review GUI](#phase-4-side-by-side-review-gui)
   - [Phase 5: Shipping & Tax Overflow Questions](#phase-5-shipping--tax-overflow-questions)
5. [Browser Automation & Form Autofill on Engage](#5-browser-automation--form-autofill-on-engage)
   - [Automated Bill Line Item Lookup](#automated-bill-line-item-lookup)
   - [Form Field Mapping](#form-field-mapping)
6. [Required Attachments on Engage (Upload #1 & #2)](#6-required-attachments-on-engage-upload-1--2)
   - [Upload #1: Shopping Cart Screenshot (`cart.png`)](#upload-1--shopping-cart-screenshot-cartpng)
   - [Upload #2: Budget vs Quoted Audit Report (`.xlsx`)](#upload-2--budget-vs-quoted-audit-report-xlsx)
7. [Final Submission & Automatic Spreadsheet Logging](#7-final-submission--automatic-spreadsheet-logging)
8. [Troubleshooting & FAQs](#8-troubleshooting--faqs)

---

## 1. When to Use This Command

Use `mrg-finance purchase` during **Stage 2 (Spending Approved Funds)** of the club finance lifecycle:
- The SGA has approved your funding bill and assigned an official `Bill No.` (e.g. `344042`).
- You have assigned an `Order ID` (e.g. `260811_amazon_awu335`) and copied the `Bill Item ID`s into the **`Ordering`** sheet.
- You are ready to purchase items from a vendor (Amazon, McMaster-Carr, DigiKey, etc.) and submit the formal Purchase Request on Georgia Tech's [CampusLabs Engage Finance](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest) portal.

---

## 2. Spreadsheet Prerequisites (`Ordering` Sheet)

Open `FY27_Bills_Budget.xlsx` on SharePoint and verify your rows in the **`Ordering`** sheet:
*(Note: Row 1 contains subtotals, Row 2 contains headers, **data begins on Row 3**).*

| Column | Field Name | Required Input | Notes |
| :--- | :--- | :--- | :--- |
| **A** | `Order ID` | Text | Format: `YYMMDD_vendor_gtusername` (e.g. `260811_amazon_awu335`). Repeat on every row for this order. |
| **B** | `Bill Item ID` | **Input** | **Copy and paste from Column A of the `Bills` sheet.** *(Drives all formulas).* |
| **C–G** | `Bill No.`, `Bill Title`, `Item Name`, `Vendor`, `Cost` | *Formula* | **Do NOT type here.** Formulas pull these from `BillsT`. |
| **H** | `Quantity` | Integer | Enter how many units you are purchasing in this specific order. |
| **I** | `Total Cost` | *Formula* | **Do NOT type here.** `=Quantity * Cost`. |
| **J** | `Allocation` | *Formula* | Total funding approved on the source bill. |
| **K** | `Purchaser` | Text | Name or GT username of person placing the order. |
| **L** | `Status` | Text | Set to `Pending`. |
| **U** | `Share-A-Cart Link` | URL | **Autofilled by CLI** (or paste vendor cart link). |
| **V** | `Engage Request Link` | URL | **Autofilled by CLI** (URL of the submitted Engage request). |

---

## 3. Running the Command

```bash
# Standard interactive launch:
mrg-finance purchase

# With automated SharePoint sync before running:
mrg-finance purchase --fresh

# Target an order directly (skips interactive selection):
mrg-finance purchase --order 260811_amazon_awu335

# Skip the optional visual review GUI:
mrg-finance purchase --no-review
```

---

## 4. Step-by-Step Interactive Terminal Walkthrough

### Phase 1: Order Selection
The CLI scans the `Ordering` sheet for pending orders:

```text
Available Orders:
  1. 260811_amazon_awu335 (Amazon, 12 items)
  2. 260821_bluerobotics_awu335 (Blue Robotics, 4 items)

Select order (number or Order ID): 1
```
- Type the number `1` or the order ID to select it.
- The CLI displays an itemized summary table showing Item Name, Approved Unit Cost, Quantity, and Line Total.

---

### Phase 2: Live Price Auditing & Overrun Mitigation
```text
🔍 Check live online prices against approved budget allocations? (Y/n): y
```
- **Type `y`**: Chrome opens product links, scrapes live online prices, and compares them against approved budget allocations.

#### Handling Cost Overruns (Price Increases):
If a live price is higher than the approved budget:
```text
⚠️ Cost Overrun for '2m IP67 LED Strip': Allocated $10.99, Live $12.59 (+$3.20 total over)
   👉 Enter substitute product link (or Enter to keep current): 
```
- **Option A**: Paste a link to an in-stock alternative item that fits within the budget. The CLI scrapes the new link immediately and verifies that the price is under budget.
- **Option B**: Press **Enter** to keep the current link and accept the overrun (you may need to allocate an overflow request for the difference).

---

### Phase 3: Seller Quantity Limits & Cart Generation

#### Quantity Limit Detection:
If an Amazon seller restricts order quantities (e.g., max 2 units per customer):
```text
⚠️ QUANTITY LIMIT DETECTED on 'M2.5 Threaded Inserts':
   Requested: 5 units | Max Available: 2 units
   👉 Enter substitute product link with full stock (or Enter to accept limit):
```
- Paste a substitute seller link or press **Enter** to automatically adjust the order quantity from 5 down to 2.

#### Shopping Cart Screenshot (`cart.png`):
- For Amazon orders, the automation adds items to the cart, navigates to `https://www.amazon.com/gp/cart/view.html`, and captures:
  `screenshots/<Order ID>/cart.png`
- For non-Amazon vendors (McMaster-Carr, DigiKey, etc.), the CLI prompts you:
  ```text
  ℹ️ Non-Amazon Vendor Items Detected:
     Please create a shopping cart directly on the vendor website and take a cart screenshot.
  ```
  Save your screenshot to `screenshots/<Order ID>/cart.png`.

#### Share-A-Cart Link Creation:
- The CLI automatically generates a multi-item cart link via the Share-A-Cart API.
- **Automatic Excel Update**: It immediately saves this link into Column U (**`Share-A-Cart Link`**) across all rows for this order in the `Ordering` sheet!

---

### Phase 4: Side-by-Side Review GUI
```text
🖥️  Open interactive side-by-side review GUI? [y/N]: y
```
- Type `y` to view product screenshots, approved allocations, and live prices side-by-side in your browser at `http://127.0.0.1:8321/review.html`.
- Press **Enter** in the terminal when done reviewing.

---

### Phase 5: Shipping & Tax Overflow Questions
```text
Do any items have shipping/tax overflow?
Add shipping/tax for a separate 2nd overflow request? [y/N]: n
```
- If shipping or taxes cause an order to exceed the SGA bill allocation, type `y` to record the overflow amounts for a secondary reimbursement request. Otherwise, type `n`.

Confirm the submission:
```text
Submit purchase request to Engage? (12 items, $734.64) [Y/n]: y
```

---

## 5. Browser Automation & Form Autofill on Engage

A visible Google Chrome browser window will open automatically.

### Automated Bill Line Item Lookup
Before opening the purchase form, the automation navigates to the approved SGA bills on Engage:
- It opens each source bill (`.../budgeting/requests#/view/<BILL_NO>`).
- It extracts the exact **Engage Line Number** and **Budget Section** (e.g. `B03 Line 12`) matching your items.
- *Why this matters*: Engage line numbers are generated by CampusLabs and are NOT Excel row numbers. The automation discovers the true Engage line numbers automatically.

### Form Field Mapping
The automation navigates to [Create Purchase Request](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest) and populates the fields:

```
CampusLabs Engage Purchase Request Form
├── Subject: Marine Robotics Group Amazon Purchase Request 2026-09-15
├── Requested Amount: $734.64
├── Description: [Order summary + Share-A-Cart Link]
├── What is the Budget/Bill # and Request Line #?:
│     └── Bill 344042 Line 1, Bill 344042 Line 4, Bill 344042 Line 7
└── SGA Bill Box:
      └── $11.99 - Line 1, Bill 344042, B06 - Non-Inventoried Items
          $18.99 - Line 4, Bill 344042, B03 - General Inventoried Goods
```

---

## 6. Required Attachments on Engage (Upload #1 & #2)

Georgia Tech SGA policy requires **two specific attachments** for every purchase request. The automation uploads both files automatically:

```
Engage Attachments Section
│
├── 📎 Upload #1: Shopping Cart Screenshot
│   ├── File: screenshots/<Order ID>/cart.png
│   └── Verifies: All items in cart, quantities, vendor estimated total
│
└── 📎 Upload #2: Price Comparison Audit Spreadsheet
    ├── File: screenshots/<Order ID>/Budget_vs_Quoted_Detail_<Order ID>.xlsx
    └── Verifies: Budget vs Quoted prices, variance, bill & line numbers
```

---

### Upload #1 — Shopping Cart Screenshot (`cart.png`)
* **File Location**: `screenshots/<Order ID>/cart.png`
* **Format**: `.png`
* **What it must show**:
  - The vendor shopping cart interface (e.g. Amazon Cart, McMaster Cart).
  - Every item name, selected options, and ordered quantities.
  - The estimated order subtotal, shipping, and taxes.

---

### Upload #2 — Budget vs Quoted Audit Report (`.xlsx`)
* **File Location**: `screenshots/<Order ID>/Budget_vs_Quoted_Detail_<Order ID>.xlsx`
* **Format**: Formatted Microsoft Excel Workbook (`.xlsx`)
* **What it contains**:
  1. **Executive KPI Block**:
     - `Total Budgeted Allocation ($)`
     - `Total Quoted Amount ($)`
     - `Net Variance ($)` (Color-coded green for savings, red for overrun)
  2. **Itemized Audit Table**:
     - `Item Name`
     - `Engage Reference` (e.g. `Bill 344042, Line 4`)
     - `Budget Section` (`B03` or `B06`)
     - `Approved Unit Cost`, `Approved Quantity`, `Approved Total`
     - `Quoted Unit Cost`, `Quoted Quantity`, `Quoted Total`
     - `Line Variance ($)`
  3. **Category Summary Table**:
     - Subtotals for `B03 - General Inventoried Goods` vs `B06 - Non-Inventoried Items`.

---

## 7. Final Submission & Automatic Spreadsheet Logging

Once the form fields and attachments are loaded, the terminal pauses:

```text
⏸️  Form pre-filled with 12 items totaling $734.64
    Review and fill remaining fields (Category, Account, etc.)
    Press Enter after you submit this purchase request → 
```

### Steps to Complete in the Browser:
1. **Category / Account**: Select the designated funding account (e.g. `SGA Sub-Account` or `Operations`).
2. **Digital Signature**: Type your full name.
3. **Submit**: Click the blue **Submit Request** button.

### Steps to Complete in the Terminal:
1. Return to your terminal and press **Enter**.
2. The automation detects the submitted Engage URL:
   ```text
   👉 Enter submitted Engage Request URL [https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/ViewRequest/987654]: 
   ```
   Press **Enter** to accept the detected URL (or paste it if not automatically detected).
3. **Automatic Spreadsheet Update**:
   - The CLI writes the URL into Column V (**`Engage Request Link`**) across all rows for that order in the `Ordering` sheet!
   - If `rclone` is enabled, it automatically syncs the updated sheet back to SharePoint.

---

## 8. Troubleshooting & FAQs

### Q: What if an Engage line number says `Line ?`?
- Check that the `Bill No.` on your `Ordering` sheet matches an approved bill on Engage. If the bill was approved under a different number, update Column B (`Bill No.`) in Excel before running the command.

### Q: What if the automated file upload fails on Engage?
- If Engage updates its file input elements and automated upload fails, manually drag and drop:
  1. `screenshots/<Order ID>/cart.png`
  2. `screenshots/<Order ID>/Budget_vs_Quoted_Detail_<Order ID>.xlsx`
  into the **Attachments** box on the Engage webpage before clicking Submit.

### Q: Can I generate the Budget vs Quoted report without opening the browser?
- **Yes!** Run:
  ```bash
  mrg-finance report --order <ORDER_ID>
  ```
  This creates `screenshots/<Order ID>/Budget_vs_Quoted_Detail_<Order ID>.xlsx` and `.csv` immediately without launching any browser automation.
