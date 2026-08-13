# 🔍 Troubleshooting & FAQ Guide

Solutions to common issues, rclone sync errors, browser automation timeouts, and spreadsheet issues in the Georgia Tech MRG Finance System.

---

## ☁️ SharePoint & `rclone` Sync Issues

### 1. `corrupted on transfer: sizes differ` or `quickxor hashes differ`
- **Cause**: Microsoft OneDrive / SharePoint automatically compresses and updates metadata inside `.xlsx` files on upload, causing local file byte sizes and QuickXor hashes to differ from OneDrive server values.
- **Solution**: All `rclone` commands in `mrg-finance` pass `--ignore-checksum` and `--ignore-size`:
  ```bash
  rclone copy --ignore-checksum --ignore-size --update screenshots "onedrive:OPS-1 Operations/FY27 Finances/screenshots"
  ```

### 2. `rclone` Command Times Out (60s / 120s)
- **Cause**: Slow network connection or large directory size when scanning files sequentially.
- **Solution**: Use parallel transfer flags (`--transfers 4 --fast-list`):
  ```bash
  rclone copy --ignore-checksum --ignore-size --update --transfers 4 --fast-list screenshots "onedrive:OPS-1 Operations/FY27 Finances/screenshots"
  ```

### 3. Microsoft Graph API Token Expiration
- **Cause**: The Graph API OAuth access token cached in `~/.config/rclone/rclone.conf` expired.
- **Solution**: Re-authenticate rclone with GT SSO:
  ```bash
  rclone config reconnect onedrive:
  ```

---

## 🌐 Chrome & Selenium Automation Issues

### 1. `ChromeDriver` Version Mismatch
- **Cause**: Chrome updated automatically and no longer matches installed `chromedriver`.
- **Solution**: `selenium>=4.27` handles ChromeDriver resolution automatically. Ensure Chrome is updated:
  - macOS: `brew upgrade --cask google-chrome`
  - Linux: `sudo apt update && sudo apt install --only-upgrade chromium-browser`

### 2. GT SSO / Duo MFA Timeout
- **Cause**: Duo MFA push notification was not approved within 3 minutes (180 seconds).
- **Solution**: The script allows 180 seconds for MFA approval. Ensure your phone is ready to receive Duo push notifications before running `mrg-finance purchase` or `mrg-finance bill-request`.

### 3. CampusLabs Engage Form Question Locators
- **Cause**: Engage form structure updated question labels.
- **Solution**: `automation_purchase.py` targets exact form questions ("What is the Budget/Bill # and Request Line #?", "Include Bill # and total reimbursement amount below ($ Per line item)...") and automatically falls back to the main **Description box** if a specific field cannot be located on DOM.

---

## 📊 Excel Report & Formula Issues

### 1. Subtotal / Grand Total Double-Counting
- **Cause**: Using `=SUM(G5:G21)` over a range containing subtotal rows double-counts costs.
- **Solution**: `order_excel_builder.py` builds multi-bill grand total formulas by referencing subtotal cells directly (`=SUM(G9, G22)`), ensuring grand totals match true order costs exactly.

### 2. Column A Auto-Fit Width Blowing Out
- **Cause**: Measuring string length over merged title rows 1–2 blows out Column A width to 100+ characters.
- **Solution**: `order_excel_builder` ignores rows 1–3 when calculating column widths, setting a compact width of 16 for Column A (`Budget Line #`).

---

## 🛠️ CLI & Environment Issues

### 1. `mrg-finance: command not found`
- **Cause**: Python user binaries directory is not in your shell `$PATH`.
- **Solution**:
  - If installed via `uv tool`: Ensure `~/.local/bin` is in `$PATH` (`export PATH="$HOME/.local/bin:$PATH"`).
  - If installed via `pipx`: Run `pipx ensurepath`.

### 2. `ModuleNotFoundError: No module named 'order_excel_builder'`
- **Cause**: Installed package missing `py-modules` entry.
- **Solution**: Run `uv tool install --force .` or `pipx install --force .` from the repository root to reinstall the executable package.
