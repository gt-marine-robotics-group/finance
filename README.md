# 🚢 Georgia Tech MRG Finance & Purchasing System

The core features of this system include:
- **Automatic Bill Submission**: Auto-fills Engage forms, uploads screenshot evidence, and includes a side-by-side review page.
- **Automatic Purchase Requests**: Auto-fills Engage forms, dynamically finds section/line numbers, and automatically generates a Budget vs Current Price allocation `.xlsx` report. *(Note: Automated price scraping is primarily validated on Amazon).*
- **Flexible Management**: All bills and orders can be managed manually on the master spreadsheet or through the interactive web dashboard.

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
1. Checks live online prices and flags any overruns.
2. Auto-adds items to an Amazon cart (opens in Incognito).
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

---

## 📚 Documentation Guides

- [**In-Depth Setup & Extra Details**](SETUP_AND_DETAILS.md): Local editable setup, detailed `rclone` configuration, Amazon cart linking behavior, and screenshot naming rules.
- [**Spreadsheet Guide**](SPREADSHEET_GUIDE.md): Master spreadsheet schema, formulas, and `doctor` diagnostic rules.
- [**Troubleshooting**](TROUBLESHOOTING.md): Solutions for `rclone` sync errors, Chrome/Selenium driver issues, and MFA timeouts.
- [**Development Guide**](DEVELOPMENT.md): System architecture, Flask web dashboard, and contributor code map.
