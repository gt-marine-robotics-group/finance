# 📋 Bill Request Automation Guide (`mrg-finance bill-request`)

This guide is the complete step-by-step walkthrough for **`mrg-finance bill-request`**. It covers terminal prompts, browser automation, Georgia Tech Duo 2FA, line item form autofill, screenshot attachment requirements on CampusLabs Engage, and post-approval logging.

---

## 📑 Table of Contents
1. [When to Use This Command](#1-when-to-use-this-command)
2. [Spreadsheet Prerequisites (`Bills` Sheet)](#2-spreadsheet-prerequisites-bills-sheet)
3. [Running the Command](#3-running-the-command)
4. [Step-by-Step Interactive Terminal Prompts](#4-step-by-step-interactive-terminal-prompts)
5. [Browser Automation on Engage Budgeting](#5-browser-automation-on-engage-budgeting)
6. [Required Attachments on Engage (Line-by-Line)](#6-required-attachments-on-engage-line-by-line)
7. [Post-Submission & Post-Approval Steps](#7-post-submission--post-approval-steps)
8. [Troubleshooting & Common Questions](#8-troubleshooting--common-questions)

---

## 1. When to Use This Command

Use `mrg-finance bill-request` during **Stage 1 (Funding Allocation)** of the club finance lifecycle:
- You want the Student Government Association (SGA) to allocate budget for future club equipment, parts, tools, or supplies.
- You have entered your proposed items under a shared **`Bill Title`** in the `Bills` sheet of `FY27_Bills_Budget.xlsx`.
- You want to eliminate the tedious manual work of clicking "Add Item", typing item names, descriptions, prices, quantities, and uploading product quote screenshots one-by-one into Engage.

---

## 2. Spreadsheet Prerequisites (`Bills` Sheet)

Open `FY27_Bills_Budget.xlsx` on SharePoint and verify your rows in the **`Bills`** sheet:

| Column | Field Name | Required Value | Notes |
| :--- | :--- | :--- | :--- |
| **A** | `Bill Item ID` | *Formula* | **Do NOT edit.** Calculated automatically (e.g. `B03-01`). |
| **B** | `Bill No.` | Blank / Number | Leave blank for new drafts. Fill in once SGA approves the bill. |
| **C** | `Bill Title` | Text | Shared bill name (e.g. `Marine Robotics Group RobotX Testing Equipment Bill`). |
| **D** | `Item Name` | Text | Clear name matching vendor listing (e.g. `Pi Pico Microcontroller`). |
| **E** | `Vendor` | Text | Vendor name (e.g. `Amazon`, `McMaster-Carr`, `DigiKey`). |
| **F** | `Description` | Text | Brief educational/engineering justification for SGA. |
| **G** | `Budget Section` | Dropdown | `B03 - General Inventoried Goods` (assets/tools) or `B06 - Non-Inventoried Items` (consumables). |
| **H** | `Quantity` | Integer | Total units needed. |
| **I** | `Cost` | Currency | Unit price (or pack price) of one unit. |
| **K** | `Total Cost` | *Formula* | **Do NOT edit.** Auto-multiplies `Quantity * Cost`. |
| **L** | `Link` | URL | Direct vendor product URL for quote verification. |
| **M** | `Person Requesting` | Text | Your GT username or full name. |

---

## 3. Running the Command

```bash
# Standard interactive launch:
mrg-finance bill-request

# With automated SharePoint sync before running:
mrg-finance bill-request --fresh

# Skipping the interactive bill selection menu:
mrg-finance bill-request --bill "Marine Robotics Group RobotX Testing Equipment Bill"

# Review product evidence in the spreadsheet:
mrg-finance screenshots --bill "<Bill Title>" --interactive
```

---

## 4. Step-by-Step Interactive Terminal Prompts

When you launch `mrg-finance bill-request`, the CLI guides you through the following prompts:

### Prompt 1: Georgia Tech Credentials
```text
Enter your GT username: gburdell3
Enter GT password (for CampusLabs + Duo MFA): [hidden]
```
- **What to do**: Enter your GT username and password. The password input is masked for security.
- *Tip*: Set `export ENGAGE_USERNAME="gburdell3"` in your terminal to avoid typing your username every time.

### Prompt 2: Bill Selection Menu
If you did not pass `--bill`, the CLI lists all available bill titles found in your spreadsheet:
```text
Available Bill Titles:
  1. Marine Robotics Group RobotX Testing Equipment Bill (Bill #344042, 11 items)
  2. Marine Robotics Group Shore Equipment Bill (Bill #344043, 6 items)
  3. Marine Robotics Group OrangeBoat Jetson Bill (Bill #?, 4 items)

Select Bill Title [1-3]: 1
```
- **What to do**: Type the number (e.g. `1`) or copy-paste the exact bill title.

### Prompt 3: Engage Bill URL Resolution
- **If `Bill No.` is already recorded in Excel**: The CLI automatically builds the direct edit URL:
  `https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests#/edit/<BILL_NO>`
- **If `Bill No.` is blank (new bill draft)**:
  ```text
  Could not find Bill No. Enter Engage Edit URL manually: 
  ```
  - Log in to [MRG Budgeting in Engage](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting).
  - Click **Create Request** &rarr; select the fiscal year (e.g. `FY27`) &rarr; name the request your exact `Bill Title`.
  - Copy the URL from your browser address bar (it looks like `.../requests#/edit/123456`) and paste it into the terminal.

### Prompt 4: Screenshot Audit & On-Demand Capture
The CLI checks `screenshots/<Bill Title>/` for product screenshots with a checked `.evidence.json` sidecar, matching source URL, and unchanged image hash. Legacy images without this record need recapturing:
```text
📸 Screenshot Audit for 'Marine Robotics Group RobotX Testing Equipment Bill':
   ✅ Checked screenshots: 9
   ⚠️ Missing or unverified screenshots: 2
```
If screenshots are missing:
```text
Capture missing screenshots in Chrome? (Y/n): y
```
- Type `y`: Visible Chrome will visit the vendor links for missing items, dismiss popups, and capture high-resolution product screenshots.
- Complete any CAPTCHA in that window and press Enter to retry, or type `cancel`. The browser session is retained under `.mrg-finance-browser/evidence/`. Linked items with missing or unverified evidence stop the bill flow before Engage opens. The source URL/hash are checked again immediately before attachment upload.
- If verification keeps repeating, type `chrome` at that prompt to switch to your regular installed Chrome. The one-time extension setup works on macOS, Windows, and Linux; see the [regular Chrome guide](REGULAR_CHROME_GUIDE.md). Position the product name and price in view before capturing. You can also run `mrg-finance screenshots --browser chrome` first and reuse its verified evidence.
- Keep the `.evidence.json` files with the images and review the images visually; challenge detection checks known text/widgets.

### Prompt 5: Spreadsheet review
Review the workbook and screenshot evidence before proceeding. The side-by-side GUI has been removed. Screenshot capture uses visible Chrome so you can solve CAPTCHAs; unresolved challenges are saved as separate diagnostics rather than quote attachments.

---

## 5. Browser Automation on Engage Budgeting

Once terminal prompts are complete, a visible Google Chrome browser window will open automatically:

```
[CLI Terminal] ──► Opens Chrome ──► GT Single Sign-On ──► Duo MFA Push
                                                              │
[Autofill Form] ◄── Navigates to Engage Budgeting Edit Page ◄─┘
```

1. **GT SSO & Duo MFA**:
   - The browser navigates to `https://gatech.campuslabs.com/engage/` and clicks **Sign In**.
   - It submits your GT username and password.
   - Terminal prints:
     ```text
     📲 Complete Duo MFA on your device if prompted...
     ```
   - Approve the Duo 2FA push on your phone. The automation detects approval and proceeds immediately.

2. **Budget Section Navigation**:
   - The automation loads your bill edit page on Engage.
   - It iterates through sections:
     - `B03 - General Inventoried Goods`
     - `B06 - Non-Inventoried Items`

3. **Line Item Autofill**:
   For every row in your spreadsheet belonging to that section:
   - Clicks **Add Item**.
   - Fills **Item Name** from Column D.
   - Fills **Description** from Column F.
   - Fills **Quantity** from Column H.
   - Fills unit **Cost** from Column I.
   - Locates the line item's file attachment input and uploads the screenshot.
   - Clicks **Save**.

---

## 6. Required Attachments on Engage (Line-by-Line)

SGA policy requires documentation verifying the quoted unit price for **every single item requested**.

```
Engage Budget Request Line Item
├── Item Name: [Pi Pico Microcontroller]
├── Description: [Embedded compute board for thruster controller]
├── Quantity: [2]
├── Cost: [$12.99]
└── [📎 File Attachment Input]
       └── Uploads: screenshots/<Bill Title>/Pi Pico.png
```

### Attachment Rules:
* **Quantity**: Exactly **1 quote screenshot per line item**.
* **File Location**: `screenshots/<Bill Title>/<Item Name>.png` (or `.jpg` / `.pdf`).
* **Content Requirement**:
  - The image must clearly show the vendor product title.
  - The item variant, model, or pack size (e.g. "Pack of 10") must be visible.
  - The unit price on the screenshot must match the unit `Cost` entered into the form.
* **How Automation Handles It**: The automation locates the matching file from your `screenshots/` directory, uploads it directly into the line item modal, and saves the item.

---

## 7. Post-Submission & Post-Approval Steps

1. **Verify Totals on Engage**:
   - In the open browser window, review the subtotal for each section (`B03`, `B06`) and the grand total.
   - Confirm it matches the subtotal in `FY27_Bills_Budget.xlsx`.
2. **Submit to SGA**:
   - Click the blue **Submit Request** button in Engage.
3. **Record Official Bill Number**:
   - Once submitted, SGA assigns a Request Number (e.g., `344042`).
   - Open `FY27_Bills_Budget.xlsx` and paste that number into Column B (**`Bill No.`**) on **all rows** for that bill.
   - *This step is critical because `mrg-finance purchase` will later use this Bill Number to look up line item allocations!*

---

## 8. Troubleshooting & Common Questions

### Q: What if an item's product link is broken or unavailable?
- If the vendor URL is 404 or out of stock, update Column L (`Link`) in `FY27_Bills_Budget.xlsx` with an active alternative product link before running `bill-request`.

### Q: Duo 2FA timed out in the terminal?
- If network lag causes the automatic Duo detector to time out, the terminal displays:
  ```text
  ⏳ Duo MFA wait timed out automatically.
  Press Enter after completing Duo MFA in your browser window →
  ```
  Simply approve the Duo push on your phone and press Enter in the terminal.

### Q: Can I run this without installing rclone?
- **Yes!** Just omit the `--fresh` flag. As long as `FY27_Bills_Budget.xlsx` is in your working directory, the command runs completely fine off your local file.
