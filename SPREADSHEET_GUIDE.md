# 📊 Master Budget Spreadsheet Guide (`FY27_Bills_Budget.xlsx`)

This guide explains how `FY27_Bills_Budget.xlsx` on SharePoint serves as the authoritative database for the Georgia Tech Marine Robotics Group finance system, how line items and orders are structured, and how `mrg-finance` maintains data integrity.

🔗 **Direct SharePoint Link**: [FY27_Bills_Budget.xlsx (SharePoint Web View)](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)

---

## 📑 Sheet Structure & Schema

### 1. `Bills` Sheet (Master Approved Line Items)
The **`Bills`** sheet stores all approved SGA budget bill line items. Every row represents an approved hardware component, tool, or service.

| Column Name | Data Type | Required? | Example Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `Bill Item ID` | String | **Yes** | `376851_1` | Unique identifier formatted as `<Bill_No>_<Line_No>`. Must be unique across all rows. |
| `Bill No.` | String / Int | **Yes** | `376851` | SGA Bill Number assigned by Georgia Tech CampusLabs Engage. |
| `Bill Title` | String | **Yes** | `RobotX Testing Equipment Bill` | Title of the approved SGA bill. |
| `Item Name` | String | **Yes** | `Radio Transmitter` | Description or product name of the item. |
| `Budget Section` | String | **Yes** | `B03 - General Inventoried Goods` | SGA Budget Category section name. |
| `Cost` | Float / Currency | **Yes** | `$299.99` | Approved unit allocation price. |
| `Link` | String / URL | **Yes** | `https://www.amazon.com/dp/...` | Direct vendor product URL (Amazon, McMaster, DigiKey, etc.). |

---

### 2. `Ordering` Sheet (Vendor Order Groupings `OrderT`)
The **`Ordering`** sheet groups specific line items from the `Bills` sheet into actionable vendor purchase requests.

| Column Name | Data Type | Required? | Example Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `Order ID` | String | **Yes** | `260811_amazon_awu335` | Unique order grouping string. Format: `YYMMDD_<vendor>_<gt_username>`. |
| `Bill Item ID` | String | **Yes** | `376851_1` | References target line item in `Bills` sheet. |
| `Quantity` | Integer | **Yes** | `2` | Number of units to order. |
| `Vendor` | String | **Yes** | `Amazon` | Vendor name (`Amazon`, `McMaster-Carr`, `DigiKey`, etc.). |
| `Allocation` | Float | Optional | `$599.98` | Extended approved cost (`Cost * Quantity`). |

---

## 🩺 Pre-Flight Spreadsheet Health Rules (`mrg-finance doctor`)

Before running automated bill or purchase request submissions, `mrg-finance doctor` audits the spreadsheet for common human editing errors:

1. 🔍 **Duplicate Bill Item IDs**:
   - Every row in `Bills` must have a unique `Bill Item ID`. Duplicate IDs cause item mapping collisions during order building.
2. 🔗 **Broken Order References**:
   - Every `Bill Item ID` in `Ordering` must exist in `Bills`. Broken references are flagged with exact row numbers.
3. 🌐 **Invalid or Missing Product Links**:
   - Product links must begin with `http://` or `https://`. Missing or incomplete URLs (e.g., `jlcpcb.com` missing `https://`) are flagged.
4. 💵 **$0.00 Cost Allocations**:
   - Items with `$0.00` approved cost are flagged to prevent zero-amount submission errors.
5. 📄 **Dynamic Header Row Offsets**:
   - `spreadsheet_utils` scans the first 10 rows of any sheet to automatically locate the true header row, tolerating extra title or blank rows inserted above data.

---

## 🛡️ Formula & Formatting Preservation

When the Web Dashboard (`http://localhost:5000`) or Side-by-Side Review Inspector (`http://localhost:8321`) writes price updates back to `FY27_Bills_Budget.xlsx`:
- **Formula Integrity**: Cell formulas (`=IFERROR(...)`, `=SUM(...)`) are preserved without being overwritten by static values.
- **Openpyxl Engine**: Cell updates are applied directly to target cells without corrupting adjacent columns, borders, or zebra striping.
