# 🚢 Georgia Tech MRG Finance & Purchasing System

The core features of this system include:
- **Automatic Bill Submission**: Auto-fills Engage forms, uploads screenshot evidence, and includes a side-by-side review page.
- **Automatic Purchase Requests**: Auto-fills Engage forms, dynamically finds section/line numbers, and automatically generates a Budget vs Current Price allocation `.xlsx` report. *(Note: Automated price scraping is primarily validated on Amazon).*
- **Flexible Management**: All bills and orders can be managed manually on the master spreadsheet or through the interactive web dashboard *(currently hosted in the background on the team's SIM PC)*.

---

## 🚀 Installation

This tool installs system-wide via [`uv`](https://docs.astral.sh/uv/getting-started/installation/) so the `mrg-finance` command works from **any directory** without manually managing Python environments.

### Step 1: Install CLI

- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
  ```
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  uv tool install git+https://github.com/gt-marine-robotics-group/finance.git
  ```

> 🌐 **Browser Note**: You **do not need to install Chrome**. Selenium automatically downloads and manages an isolated browser on first run.

### Step 2: Configure Cloud Sync (`rclone`)

Item screenshots and master budget files are synced with the team's shared GT SharePoint.

1. **Install `rclone`**: macOS (`brew install rclone`) | Windows (`winget install rclone.rclone`) | Linux (`sudo apt install rclone`)
2. **Configure Remote (`onedrive`)**:
   ```bash
   rclone config
   # Select 'n' (New remote) -> Name: onedrive -> Storage: 42 (OneDrive) -> Auth with GT SSO + Duo MFA -> SharePoint Site: https://gtvault.sharepoint.com/sites/MarineRoboticsGroup -> Drive: Documents (3)
   ```
3. **Verify Sync Access**:
   ```bash
   rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
   ```
   *Seeing `FY27_Bills_Budget.xlsx` listed confirms your cloud connection is working.*

### 📸 Manual Screenshots (CAPTCHA Fallback)

One of the most robust features is the ability to easily override the scraper. If the automation encounters a website with a CAPTCHA, you can simply take the screenshot manually and save it to the synced folder. The system will automatically detect and use it during submission:
```text
screenshots/<Bill Title>/<Item Name>.png
```

## 📋 Spreadsheet Setup (Before Running CLI)

Ensure your items are entered in `FY27_Bills_Budget.xlsx` on SharePoint before running the tools:

- **For Bill Requests (`Bills` Sheet)**: Add your proposed items under the target **`Bill Title`**. Fill in **`Item Name`**, **`Budget Section`** (e.g. `B03 - General Inventoried Goods`, `B06 - Non-Inventoried Items`), **`Cost`**, **`Quantity`**, and a valid product **`Link`** for automated screenshot capture. *(Leave formula columns like `Total Cost` untouched)*.
- **For Purchase Requests (`Ordering` Sheet)**: Group items into an order by assigning an **`Order ID`** formatted as `YYMMDD_<vendor>_<gt_username>` (e.g., `260819_amazon_awu335`). Fill in **`Item Name`**, **`Vendor`**, **`Cost`**, **`Quantity`**, and **`Link`**.

---

## 🛒 Usage & Workflow

Before running commands, you can verify your spreadsheet health with `mrg-finance doctor --fresh`.

### 1. Submit a Bill Request
When submitting a newly drafted bill for SGA approval:
```bash
mrg-finance bill-request --fresh
```
1. Verifies screenshot evidence for every line item.
2. Opens the side-by-side inspector to review items.
3. Pre-fills the Engage bill form automatically.
4. ⚠️ **Final Action Required**: Click **"Submit"** on CampusLabs Engage.

### 2. Submit a Purchase Request
When you are placing an order for items approved on a bill:
```bash
mrg-finance purchase --fresh --order <ORDER_ID>
```
> 💡 **Tip**: If you omit `--order <ORDER_ID>`, the CLI will launch an interactive menu for you to select an order. You can find the exact Order IDs on the `Ordering` sheet of `FY27_Bills_Budget.xlsx`.
1. Checks live online prices and flags any overruns.
2. Auto-adds items to an Amazon cart (opens in Incognito) *(Note: Currently broken)*.
3. Generates the **Budget vs Quoted Detail Report** (`.xlsx`).
4. Pastes the needed info for each line item (cost, bill number) into the Engage **Description** box. *(Note: full auto-filling of specific Engage form fields is still a work in progress).*
5. ⚠️ **Final Actions Required**:
   - Manually input the details from the Description box into the actual Engage form fields.
   - Manually attach the **Cart Screenshot (`cart.png`)** and the **Budget vs Quoted Detail Report**.
   - Digitally "sign" the request by typing your name in the final box.
   - Click **"Submit"** on CampusLabs Engage!

### 3. Review Prices & Screenshots
Open the side-by-side review GUI without running browser automation:
```bash
mrg-finance review
```

### 4. Manual Workflow Alternative (Without CLI)
If you need to submit bill or purchase requests manually on Engage without the CLI:
- **Bill Requests**: Fill out the `Bills` sheet, take product screenshots into `screenshots/<Bill Title>/<Item Name>.png`, open [Engage Budgeting](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting), enter the line items under the target section (`B03`/`B06`), upload each screenshot, and click Submit.
- **Purchase Requests**: Build your cart on the vendor site, take a screenshot of the cart (`cart.png`), open [Create Purchase Request](https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest), enter the bill and line references in the form, attach `cart.png` and your price comparison spreadsheet, sign, submit, and paste the resulting Engage URL into Column V (`Engage Request Link`) on the `Ordering` sheet.
- 📖 **Full Guide**: See [**Manual Workflow Guide**](docs/MANUAL_WORKFLOW.md) for complete field-by-field instructions.

---

## 📚 Documentation Guides

All specialized documentation and guides are organized in the [`docs/`](docs/) directory:

- [**Manual Workflow Guide**](docs/MANUAL_WORKFLOW.md): Step-by-step instructions for submitting bills and purchase requests directly on Engage.
- [**Spreadsheet Guide**](docs/SPREADSHEET_GUIDE.md): Master spreadsheet schema, formulas, and `doctor` diagnostic rules.
- [**In-Depth Setup & Extra Details**](docs/SETUP_AND_DETAILS.md): Local editable setup, detailed `rclone` configuration, Amazon cart linking behavior, and screenshot naming rules.
- [**Troubleshooting**](docs/TROUBLESHOOTING.md): Solutions for `rclone` sync errors, Chrome/Selenium driver issues, and MFA timeouts.
- [**Development Guide**](docs/DEVELOPMENT.md): System architecture, Flask web dashboard, and contributor code map.
- [**AI Agent Guidelines**](docs/agents.md): System specifications, constraints, and architecture manual for AI coding assistants.
- [**Changelog & Technical History**](docs/agent_changes.md): Chronological record of refactors, feature additions, and post-mortems.

---

## 💻 CLI Commands Reference

You can view these options directly from your terminal by running `mrg-finance --help` or appending `--help` to any command.

### `mrg-finance bill-request`
Submit a bill to CampusLabs Engage for SGA approval.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.
- `--no-review`: Skip opening the interactive side-by-side review GUI.

### `mrg-finance purchase`
Submit purchase requests to Engage.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.
- `--order ORDER`, `-o ORDER`: Pass a specific Order ID to skip interactive selection.
- `--no-review`: Skip opening the interactive side-by-side review GUI.

### `mrg-finance report`
Generate the Budget vs Quoted Full Detail Excel/CSV comparison report locally.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.
- `--order ORDER`, `-o ORDER`: Pass a specific Order ID to skip interactive selection.

### `mrg-finance doctor`
Run diagnostic health check on `FY27_Bills_Budget.xlsx`.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.

### `mrg-finance review`
Launch the side-by-side screenshot & price review GUI locally.
- `--bill BILL`, `-b BILL`: Target a specific Bill title to skip interactive selection.

### `mrg-finance price-check`
Check current online prices vs the approved allocation.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.
- `--bill BILL`, `-b BILL`: Target a specific Bill title to skip interactive selection.
- `--cart`, `-c`: Automatically generate an Amazon cart link from the items *(Note: Currently broken)*.

### `mrg-finance screenshots`
Scrape prices and take screenshots in the background.
- `--fresh`, `-f`: Sync latest changes from SharePoint before running.
- `--bill BILL`, `-b BILL`: Target a specific Bill title to skip interactive selection.
- `--review-only`, `-r`: Launch review GUI without scraping new prices.
- `--no-review`: Skip opening the interactive side-by-side review GUI.
