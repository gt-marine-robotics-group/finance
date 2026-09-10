# 📋 Manual Finance & Purchasing Workflow Guide

This guide details how to perform SGA Bill Requests and Purchase Requests **manually** on Georgia Tech CampusLabs Engage without using the `mrg-finance` CLI tool. Use this guide if you are submitting orders manually, testing the workflow, or overriding automated steps.

---

## 📑 Prerequisites & Master Spreadsheet Setup

All financial requests trace back to **`FY27_Bills_Budget.xlsx`** on SharePoint.

🔗 **Direct SharePoint Link**: [FY27_Bills_Budget.xlsx](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)

---

## 📝 Workflow 1: Manual SGA Bill Request Submission

Use this workflow when submitting a proposed budget bill to SGA for funding allocation before purchasing items.

### Step 1: Draft Items in the `Bills` Sheet
1. Open `FY27_Bills_Budget.xlsx` and go to the **`Bills`** sheet.
2. Add your items under your target **`Bill Title`** (e.g., `Marine Robotics Group RobotX Testing Equipment Bill`):
   - **`Bill Title`**: Exact name of the proposed bill.
   - **`Item Name`**: Descriptive component or product name.
   - **`Budget Section`**: SGA category (most common: `B03 - General Inventoried Goods` or `B06 - Non-Inventoried Items`).
   - **`Cost`**: Unit price quote in USD.
   - **`Quantity`**: Number of units requested.
   - **`Link`**: Direct vendor product page URL.
   - ⚠️ *Note: Leave formula columns like `Bill Item ID` (Column A) and `Total Cost` (Column K) untouched.*

### Step 2: Capture Quote Screenshots
1. Open each product link in your browser.
2. Take a clear screenshot of the product page showing:
   - Item title/name
   - Current unit price
   - Quantity or package specifications
3. Save each screenshot to your local folder:
   ```text
   screenshots/<Bill Title>/<Item Name>.png
   ```

### Step 3: Create the Budget Request on Engage
1. Go to **CampusLabs Engage Budgeting**:
   `https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting`
2. Log in using your **GT credentials** and complete **Duo MFA**.
3. Click **"Create Request"** (or select your draft request under the Budgeting tab).
4. Fill in the request header details (Title, Organization: Marine Robotics Group, Fiscal Year: FY27).

### Step 4: Add Line Items to the Budget Tab
1. Click the **"Budget"** tab.
2. For each category section (e.g. `B03` or `B06`):
   - Click **"Add Item"**.
   - Enter **Name**, **Description**, **Quantity**, and **Unit Cost**.
   - Upload the corresponding quote screenshot from `screenshots/<Bill Title>/<Item Name>.png`.
   - Click **"Save"**.
3. Repeat for all line items.

### Step 5: Review & Submit
1. Verify the grand total on Engage matches your master spreadsheet calculation.
2. Click **"Submit"** to route the bill to SGA for review.
3. Once SGA approves the bill, record the official **`Bill No.`** (e.g., `376945`) in Column C of the `Bills` sheet for all items in that bill.

---

## 🛒 Workflow 2: Manual Purchase Request Submission

Use this workflow when purchasing items that have already received SGA bill approval.

### Step 1: Group Items in the `Ordering` Sheet
1. Open `FY27_Bills_Budget.xlsx` and go to the **`Ordering`** sheet.
2. Add a new row for each item you plan to order:
   - **`Order ID`**: Format as `YYMMDD_<vendor>_<gt_username>` (e.g., `260910_amazon_awu335`).
   - **`Bill Item ID`**: ID referencing the approved item from the `Bills` sheet. (Calculated columns like `Bill No.`, `Bill Title`, `Item Name`, and `Cost` will auto-populate).
   - **`Quantity`**: Number of units to order.
   - **`Vendor`**: Vendor name (e.g. `Amazon`, `McMaster-Carr`).
   - **`Purchaser`**: Your GT username.
   - **`Status`**: Set to `pending purchase`.

### Step 2: Build the Shopping Cart & Capture Cart Screenshot
1. Log into your vendor account (e.g., Amazon, McMaster) in your standard browser.
2. Add all items from the order with their exact quantities to your cart.
3. Navigate to the shopping cart page (`https://www.amazon.com/gp/cart/view.html`).
4. Take a full-window screenshot showing all items, quantities, and the subtotal:
   - Save the image to: `screenshots/<Order ID>/cart.png`
   - *(This is mandatory Upload #1 required by GT Finance).*

### Step 3: (Optional) Generate Share-A-Cart Link
1. If using the [Share-A-Cart browser extension](https://share-a-cart.com):
   - Open your shopping cart in Chrome.
   - Click the **Share-A-Cart** extension icon and click **"Create Cart"**.
   - Copy the generated URL (`https://share-a-cart.com/get/<ID>`).
2. Paste this URL into Column U (**`Share-A-Cart Link`**) on the `Ordering` sheet for that order.

### Step 4: Prepare the Budget vs Quoted Comparison
If current live prices differ from the approved bill allocation:
1. Create an Excel sheet comparing:
   - Item Name | Bill # & Line # | Approved Unit Cost | Live Quoted Cost | Variance | Extended Total
2. *(Alternatively, run `mrg-finance report --order <Order ID>` to generate this file automatically as `Budget_vs_Quoted_Detail_<Order ID>.xlsx`).*
3. *(This is mandatory Upload #2 required by GT Finance).*

### Step 5: Open & Fill the Engage Purchase Request Form
1. Go to **Create Purchase Request**:
   `https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest`
2. Log in with your **GT credentials** and complete **Duo MFA**.
3. Complete the form fields:
   - **Subject**: `Marine Robotics Group <Vendor> Purchase Request <Date>` (e.g. `Marine Robotics Group Amazon Purchase Request 2026-09-10`).
   - **Requested Amount**: Total order dollar amount.
   - **Description**: Include cart details and Share-A-Cart link:
     ```text
     Share-A-Cart Link:
     https://share-a-cart.com/get/...
     ```
   - **Category**: Supplies / Materials / Equipment (as approved by SGA).
   - **Account**: Select your organization's SGA or Agency account.
   - **What is the Budget/Bill # and Request Line #?**:
     - List each item's bill number and line reference:
       `Bill 344042, Line 34; Bill 344042, Line 35`
   - **SGA Bill Box** (*"Include Bill # and total reimbursement amount below ($ Per line item)"*):
     - Itemize the dollar breakdown:
       `$49.95, Line 34, Bill 344042, B06 - Non-Inventoried Items`
       `$49.95, Line 35, Bill 344042, B06 - Non-Inventoried Items`

### Step 6: Attach Mandatory Documentation
1. **Attachment #1**: Upload your cart screenshot (`cart.png`).
2. **Attachment #2**: Upload your Budget vs Quoted Excel detail report (`.xlsx`).

### Step 7: Digitally Sign & Submit
1. Type your legal full name in the digital signature text box at the bottom of the form.
2. Click **"Submit Request"**.

### Step 8: Update Master Spreadsheet
1. Once submitted, copy the confirmation page URL from your browser address bar:
   `https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/ViewPurchaseRequest/<ID>`
2. Paste this link into Column V (**`Engage Request Link`**) in `FY27_Bills_Budget.xlsx` on the `Ordering` sheet for all rows of that order.
3. Save the spreadsheet so your team lead and financial advisor can review and approve it.
