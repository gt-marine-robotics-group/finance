# Bill Request Automation

Automates submitting bill line items to CampusLabs Engage, including price verification via screenshots.

## Setup (First Time)

### 1. Clone the repo

```bash
git clone git@github.com:gt-marine-robotics-group/finance.git
cd finance
```

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Sync the MRG SharePoint folder via OneDrive

The scripts read directly from the synced SharePoint xlsx. You need the MRG "Documents" folder synced locally.

**To set up OneDrive sync:**
1. Go to https://gatech.sharepoint.com (sign in with your GT account)
2. Find the **Marine Robotics Group** team site → **Documents**
3. Navigate to: `OPS-1 Operations/FY27 Finances/`
4. Click the **Sync** button (top toolbar) — this opens OneDrive and starts syncing
5. The folder will appear at:
   ```
   ~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/
     Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx
   ```

**Verify it's synced:**
```bash
ls ~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/Documents\ -\ Marine\ Robotics\ Group/OPS-1\ Operations/FY27\ Finances/
```
You should see `FY27_Bills_Budget.xlsx`.

**Important:** Close the xlsx in Excel before running scripts. After the script modifies the file, it will open it in Excel automatically — just Cmd+S and close to trigger OneDrive sync.

### 4. Chrome

Install Chrome (required for Selenium). ChromeDriver is managed automatically.

## Workflow

### 1. Prepare the spreadsheet

Each item row in the "Bills" sheet needs:
- **Bill Title** — exact name of the bill (must match across all items in a group)
- **Item Name** — name for the line item
- **Cost** — unit price
- **Quantity** — how many
- **Link** — URL to the product page (for screenshots)
- **Budget Section** — which CampusLabs section to put it in (e.g. `B03 - General Inventoried Goods`)
- **Bill No.** — the CampusLabs bill number (used to auto-generate the URL)

Optional:
- **Description** — fills the description field on CampusLabs

### 2. Run screenshots & price verification

```bash
source .venv/bin/activate
python automation_screenshots.py
```

**What it does:**
1. Shows available bill titles — pick one by number or name
2. Shows all items that will be processed — confirm with `y`
3. Opens each item's link in headless Chrome, scrapes the price, takes a screenshot
4. Compares scraped price against spreadsheet:
   - ✅ Match → marked OK
   - ⚠️ Mismatch → keeps your spreadsheet price, flags for review
   - ❌ Failed → couldn't find a price
5. Generates `review.html` — interactive page with screenshots and editable price fields
6. If mismatches found: starts a local server and opens `review.html` in your browser
7. Edit prices in the browser → click **"Save to Spreadsheet"** → writes directly to the xlsx and opens it in Excel
8. Cmd+S in Excel, close it → OneDrive syncs
9. Press Enter in terminal when done

### 3. Submit items to CampusLabs bill

```bash
source .venv/bin/activate
python automation.py
```

**What it does:**
1. Shows available bill titles with their Bill No. — pick one
2. Auto-generates the CampusLabs URL from the Bill No.
3. Prompts for your GT username and password
4. Shows pre-flight check: all items with costs, quantities, and whether screenshots exist
5. Asks: **Clear existing items** (start fresh) or **Keep existing** (skip duplicates)?
6. Logs into CampusLabs, navigates to the bill, and for each item:
   - Checks if it already exists (deduplication)
   - Fills in name, description, quantity, price
   - Uploads the screenshot if found
   - Clicks Save and verifies it actually saved
   - Retries up to 3 times if something fails
7. Prints a final summary of successes, skips, and failures

### 4. Submit purchase requests (reimbursements)

```bash
source .venv/bin/activate
python automation_purchase.py
```

Pre-fills the CampusLabs purchase request form for each item:
- Subject, description, amount
- Auto-generates "Bill XXXXXX, Line X" reference
- Uploads receipt/screenshot
- Supports overflow items (shipping/tax)

### 5. Re-running after changes

If you update prices or add items in the spreadsheet:
1. Re-run `automation_screenshots.py` to get new screenshots and verify prices
2. Re-run `automation.py` and choose **Option 1 (Clear all)** to replace existing items with the updated data

## File Structure

```
finance/
├── automation.py              # Submits items to CampusLabs budget bill
├── automation_screenshots.py  # Scrapes prices, takes screenshots, generates review page
├── automation_purchase.py     # Fills out purchase request forms
├── review_server.py           # Local server for review.html to save to xlsx
├── engage_tools.py            # SharePoint download utility (optional, needs Azure app)
├── requirements.txt           # Python dependencies
├── .env.example               # Template for optional Azure config
├── .gitignore
└── README.md
```

Generated at runtime (gitignored):
```
├── screenshots/               # Generated screenshots from scraper
├── review.html                # Generated interactive review page
└── *.csv                      # Backup CSVs
```

## Troubleshooting

**Script shows no bill titles:**
- Check that `Bill Title` is filled in for each item row (not just a header row)

**"Spreadsheet appears to be open in Excel":**
- Close Excel first so the script can read/write the xlsx properly

**Screenshots don't show prices:**
- Some sites block headless browsers. The screenshot is still useful as proof of the product page.
- Prices from the spreadsheet are preserved regardless.

**CampusLabs save button doesn't work:**
- Manually click Save in the browser — the script will detect it and continue.

**OneDrive not syncing after script edits:**
- Open the xlsx in Excel → Cmd+S → close. This forces OneDrive to recognize the change.

**Wrong prices showing in pre-flight:**
- The review.html "Save to Spreadsheet" button writes to the xlsx. Make sure you saved and synced before running automation.py.

## Notes

- Screenshots are named to match "Item Name" exactly
- The review.html page requires the background server (handled automatically) to save changes
- OneDrive sync propagates xlsx changes to SharePoint automatically
- Multiple people can sync — SharePoint handles merge conflicts and keeps version history
- `.env` and `.token_cache.bin` are gitignored — credentials stay local
