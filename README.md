# Bill Request Automation

## Quick Start

1. Download the images for the bill you are submitting on SharePoint and save them in the `/downloads` folder
2. Download the most recent bill `.csv` in UTF-8 encoding (or use `engage_tools.py download` to auto-pull from SharePoint)

3. Run `automation_screenshots.py` to scrape prices and take screenshots.
    - Opens each item link, extracts the price, and saves a screenshot
    - Generates `review.html` — open it in your browser to quickly verify all prices match
    - Updates the CSV with scraped prices → `FY27_Bills_Budget_Updated.csv`

4. Run `automation.py` to submit items to CampusLabs.
    - If it gets stuck when saving items, click save and it should continue.
    - Includes deduplication: won't add an item that already exists in a section
    - Verifies each save completed before moving to the next item
    - Prints a final summary showing successes, skips, and failures

5. Run `python engage_tools.py verify --bill "Your Bill Name" --csv FY27_Bills_Budget.csv` to confirm items saved.


## Setup: SharePoint Auto-Download & API Verification

### 1. Register an Azure App (for SharePoint access)

1. Go to [Azure Portal](https://portal.azure.com) → sign in with `yourname@gatech.edu`
2. Search for **"App registrations"** → **New registration**
   - Name: `MRG Finance Automation`
   - Supported account types: **"Accounts in this organizational directory only (Georgia Tech)"**
   - Redirect URI: leave blank
   - Click **Register**
3. On the app's Overview page, copy:
   - **Application (client) ID** → this is your `AZURE_CLIENT_ID`
   - **Directory (tenant) ID** → this is your `AZURE_TENANT_ID`
4. Go to **Authentication** → under "Advanced settings":
   - Set **"Allow public client flows"** to **Yes** → Save
5. Go to **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**:
   - `Files.Read.All`
   - `Sites.Read.All`
   - Click **Add permissions**
6. If you see "Admin consent required" and it's not granted:
   - For delegated permissions with device code flow, admin consent is usually NOT required
   - If it is, ask your GT admin or try without — it often works for read-only access to your own sites

### 2. Get a CampusLabs Engage API Key

1. Go to: https://gatech.campuslabs.com/engage/admin/apikeys
   - You need **All Access** admin role on your org
2. Click **Create API Key**
   - Name: `MRG Automation`
   - Description: `Bill verification script`
3. Set restrictions:
   - **IP restriction**: Add your machine's IP (or leave unrestricted for now)
   - **Method & Endpoint**: Allow `GET` on `/v3.0/finance/request/funding`
4. Copy the key (starts with `esk_live_`)

### 3. Create your `.env` file

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 4. Verify everything works

```bash
# Test Engage API connection
python engage_tools.py verify --bill "Marine Robotics Group"

# Test SharePoint connection (first time opens browser for auth)
python engage_tools.py ls General

# Download the spreadsheet
python engage_tools.py download -o FY27_Bills_Budget.xlsx

# Convert xlsx to csv
python engage_tools.py convert FY27_Bills_Budget.xlsx
```

### How to verify API permissions are set up correctly

**For the Engage API:**
```bash
# Quick test — should return funding request data (or empty list if no requests yet)
curl -s -H "X-Engage-Api-Key: YOUR_KEY_HERE" \
  "https://engage-api.campuslabs.com/api/v3.0/finance/request/funding?take=1" | python3 -m json.tool
```
- ✅ If you get `{"totalItems": ..., "items": [...]}` → key works
- ❌ `401` → key not provided correctly
- ❌ `403` → key invalid, IP restricted, or endpoint not permitted

**For SharePoint/Microsoft Graph:**
```bash
# Run the tool — it will prompt you to sign in via browser on first run
python engage_tools.py ls
```
- ✅ If you see a file listing → permissions work
- ❌ "Insufficient privileges" → go to App registrations → API permissions, make sure `Files.Read.All` and `Sites.Read.All` are added
- ❌ "AADSTS700016" → CLIENT_ID is wrong
- ❌ "AADSTS90002" → TENANT_ID is wrong

**Checking Azure Portal permissions visually:**
1. Go to [portal.azure.com](https://portal.azure.com) → App registrations → your app
2. Click **API permissions** — you should see:
   | API | Permission | Type | Status |
   |-----|-----------|------|--------|
   | Microsoft Graph | Files.Read.All | Delegated | ✅ Granted |
   | Microsoft Graph | Sites.Read.All | Delegated | ✅ Granted |
3. If Status shows "Not granted", click **Grant admin consent** (if you have permission) or it will work anyway for delegated flows where the user consents at login time.


## Notes
- Images must have the same exact name as what is in the "Item Name" column.
- The `review.html` page has filter buttons to quickly find items that need manual review.
- Token is cached in `.token_cache.bin` — delete it to force re-authentication.
- `.env` and `.token_cache.bin` are in `.gitignore` so credentials won't be committed.


## Dependencies

```bash
pip install msal requests pandas selenium openpyxl
```
