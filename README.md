# ⚓ Georgia Tech MRG Finance & Purchasing System

Automated bill request submission, purchase request automation, live price auditing, and budget spreadsheet management for the **Georgia Tech Marine Robotics Group**.

---

## 🛠️ Quick Installation

This repository exclusively uses [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for package management.

### 1. Install `mrg-finance` CLI Tool (System-Wide Access)

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

### 2. Prerequisites
1. **Google Chrome**: macOS: `brew install --cask google-chrome` | Windows: Install Chrome browser.
2. **SharePoint Cloud Sync (`rclone`)**:
   ```bash
   rclone config   # Remote: onedrive -> Storage: 42 (OneDrive) -> Site: https://gtvault.sharepoint.com/sites/MarineRoboticsGroup
   ```
   > ⚠️ **Need Help?**: `rclone` config uses GT SSO + Duo MFA. Ask a finance officer or team lead for assistance during initial setup!

---

## 📊 Master Budget Spreadsheet

🔗 **Direct SharePoint Link**: [FY27_Bills_Budget.xlsx (SharePoint Web View)](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)

---

## 🤖 CLI Quick Reference (`mrg-finance`)

```bash
# 1. Run pre-flight health diagnostic audit on spreadsheet
mrg-finance doctor --fresh

# 2. Submit purchase request to Engage (Audits prices, attaches cart.png + Budget vs Quoted .xlsx report, pre-fills form)
mrg-finance purchase --fresh --order 260811_amazon_awu335

# 3. Generate side-by-side Budget vs Quoted Excel & CSV report
mrg-finance report --fresh --order 260811_amazon_awu335

# 4. Submit draft bill request to Engage for SGA approval
mrg-finance bill-request --fresh

# 5. Launch side-by-side screenshot & price review GUI
mrg-finance review
```

> ⚠️ **Engage Form Submission**: After `mrg-finance purchase` or `bill-request` pre-fills the form and attaches backup files, you **must click "Submit" on CampusLabs Engage** to finalize the request.

---

## 📚 Complete Documentation Index

| Guide | Description |
| :--- | :--- |
| 📘 [**USAGE_GUIDE.md**](USAGE_GUIDE.md) | **Student Workflow Guide**: Complete step-by-step purchasing walkthrough, Amazon cart generation, and Engage submissions. |
| 📊 [**SPREADSHEET_GUIDE.md**](SPREADSHEET_GUIDE.md) | **Master Spreadsheet Guide**: Deep dive into `FY27_Bills_Budget.xlsx`, `Bills` vs `Ordering` schema, and formula preservation. |
| 🔍 [**TROUBLESHOOTING.md**](TROUBLESHOOTING.md) | **Troubleshooting & FAQ**: Solutions for `rclone` sync errors, Chrome/Selenium issues, Duo MFA, and Windows setup. |
| 💻 [**DEVELOPMENT.md**](DEVELOPMENT.md) | **Developer Guide**: System architecture map, Flask web dashboard, database schemas, and unit test suite details. |
