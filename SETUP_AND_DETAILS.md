# 📘 In-Depth Setup & Extra Details

This guide covers advanced setup options and additional details for the MRG Finance & Purchasing System.

---

## 🚀 5-Minute Detailed Setup Guide

If you wish to set up the repository for local development or editable usage:

### Step 1: Open Terminal & Clone Repository
```bash
git clone git@github.com:gt-marine-robotics-group/finance.git
cd finance
```

### Step 2: Create Python Environment (`.venv`)
Ensure you have [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed:
```bash
uv venv
source .venv/bin/activate        # On Windows: .\.venv\Scripts\activate
uv pip install -e .
```

### Step 3: Detailed SharePoint Sync Configuration (`rclone`)
Screenshots and master Excel files are synced from GT SharePoint via `rclone`.
```bash
# Install rclone (macOS: brew install rclone | Windows: winget install rclone.rclone)
rclone config
```
When prompted by `rclone config`:
1. Type `n` *(New remote)*
2. Name: `onedrive` *(Must be lowercase `onedrive`)*
3. Storage: `42` *(Microsoft OneDrive)*
4. Leave `client_id` / `client_secret` blank (press Enter)
5. Web Browser Auth: Log in with your **`<username>@gatech.edu` SSO + Duo MFA**.
6. `config_type`: Type `3` *(SharePoint site)*
7. Site URL: `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`
8. `config_driveid`: Type `3` *(Documents)*
9. Confirm with `y`, then quit with `q`.

Test your connection:
```bash
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
```

> ⚠️ **WARNING**: If you encounter any issues configuring `rclone` with GT SSO + Duo MFA, ask a finance officer or team lead for help!

---

## 🛒 Amazon Multi-Item Cart Links (Incognito Mode)

> ⚠️ **Note**: This feature is currently broken and may not function as expected.

When placing Amazon orders via `mrg-finance purchase`, the system builds a single multi-item cart URL:

- **Why Incognito Chrome?**: Automatically launches Incognito so any student can generate a fresh cart screenshot without mixing items into their personal Amazon account.
- **How it Works**: Uses Amazon's AWS add-to-cart API (`ASIN.x` and `Quantity.x`). Clicking "Continue" on the Amazon landing page pre-fills your cart instantly.

---

## 📸 Manual Screenshot Naming Guide

If you take screenshot files manually, save them to:
```
screenshots/<Bill Title>/<Item Name>.png
```

### Flexible File Recognition
The system uses a flexible matching algorithm to find your screenshots:
1. **Whitespace & Case Insensitive**: `Small Rope.PNG` matches `small rope`.
2. **Punctuation Sanitized**: `2m IP67 LED Strip (144LED_m).png` matches `2m IP67 LED Strip (144LED/m)`.
3. **Supported Formats**: `.png`, `.jpg`, `.jpeg`, `.webp`.
