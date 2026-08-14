# ⚓ Georgia Tech MRG Finance & Purchasing System

Automated bill request submission, purchase request automation, live price auditing, and budget spreadsheet management for the **Georgia Tech Marine Robotics Group**.

---

### ⚡ 1-Step Installation (`uv`)

| Platform | Installation Command |
| :--- | :--- |
| 🍎 **macOS / Linux** | `curl -LsSf https://astral.sh/uv/install.sh \| sh && uv tool install git+https://github.com/gt-marine-robotics-group/finance.git` |
| 🪟 **Windows (PowerShell)** | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"; uv tool install git+https://github.com/gt-marine-robotics-group/finance.git` |

---

### 🔌 Prerequisites

1. **Google Chrome**: macOS (`brew install --cask google-chrome`) \| Windows (Install Chrome)
2. **SharePoint Cloud Sync (`rclone`)**: `rclone config` *(Remote: `onedrive` ➔ Storage: `42` ➔ Site: `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`)*
   > ⚠️ **Need Help?**: Ask a finance officer or team lead if you need assistance during initial `rclone` SSO/Duo setup!

---

### 📊 Master Budget Spreadsheet

🔗 **Direct SharePoint Link**: [FY27_Bills_Budget.xlsx (SharePoint Web View)](https://gtvault.sharepoint.com/:x:/r/sites/MarineRoboticsGroup/Shared%20Documents/OPS-1%20Operations/FY27%20Finances/FY27_Bills_Budget.xlsx?d=w89396907686c491395b64a5ef042181c&csf=1&web=1&e=b5knap)

---

### 🤖 CLI Commands Cheat Sheet (`mrg-finance`)

| Command | Action / Description | Example |
| :--- | :--- | :--- |
| `mrg-finance doctor` | Pre-flight audit checking duplicate IDs, broken links & row shifts | `mrg-finance doctor --fresh` |
| `mrg-finance purchase` | Audits prices, builds Amazon cart, attaches `cart.png` & `.xlsx` report, pre-fills form | `mrg-finance purchase --fresh --order 260811_amazon_awu335` |
| `mrg-finance report` | Generates side-by-side Budget vs Quoted Excel (`.xlsx`) & CSV detail reports | `mrg-finance report --fresh --order 260811_amazon_awu335` |
| `mrg-finance bill-request` | Submits draft budget bill to CampusLabs Engage for SGA approval | `mrg-finance bill-request --fresh` |
| `mrg-finance review` | Launches interactive side-by-side screenshot & price review GUI (`:8321`) | `mrg-finance review` |

> ⚠️ **Engage Form Submission**: After `mrg-finance purchase` or `bill-request` pre-fills the form and attaches backup files, **you must click "Submit" on CampusLabs Engage** to finalize the request.

---

### 📚 Complete Documentation Guides

| Guide | Content / Focus |
| :--- | :--- |
| 📘 [**USAGE_GUIDE.md**](USAGE_GUIDE.md) | **Student Workflow Guide**: Purchasing walkthrough, Amazon cart generation, and Engage form pre-filling. |
| 📊 [**SPREADSHEET_GUIDE.md**](SPREADSHEET_GUIDE.md) | **Master Spreadsheet Guide**: `FY27_Bills_Budget.xlsx` schema (`Bills` vs `Ordering`) and formula rules. |
| 🔍 [**TROUBLESHOOTING.md**](TROUBLESHOOTING.md) | **Troubleshooting & FAQ**: Solutions for `rclone` sync errors, Chrome/Selenium drivers, Duo MFA, and Windows setup. |
| 💻 [**DEVELOPMENT.md**](DEVELOPMENT.md) | **Developer Guide**: System architecture map, Flask web dashboard, database schemas, and unit test suite details. |
