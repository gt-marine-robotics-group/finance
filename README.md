# Bill Request Automation

Automates submitting bill line items to CampusLabs Engage, including price verification via screenshots.

## Prerequisites

```bash
cd /Users/aaronwu/mrg/finance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You also need Chrome installed (for Selenium).

## Workflow

### 1. Prepare the spreadsheet

The scripts read directly from the synced SharePoint xlsx:
```
~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/
  Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx
```

Each item row needs these columns filled in:
- **Bill Title** — exact name of the bill (must match across all items in a group)
- **Item Name** — name for the line item
- **Cost** — unit price
- **Quantity** — how many
- **Link** — URL to the product page (for screenshots)
- **Budget Section** — which CampusLabs section to put it in (e.g. `B03 - General Inventoried Goods`)

Optional:
- **Description** — fills the description field on CampusLabs
- **Bill No.** — the CampusLabs bill number (for reference)

### 2. Run screenshots & price verification

```bash
source .venv/bin/activate
python automation_screenshots.py
```

**What it does:**
1. Shows available bill titles from the spreadsheet — pick one by number or name
2. Shows all items that will be processed — confirm with `y`
3. Opens each item's link in headless Chrome, scrapes the price, takes a screenshot
4. Compares scraped price against spreadsheet:
   - ✅ Match → marked OK
   - ⚠️ Mismatch → keeps your spreadsheet price, flags for review
   - ❌ Failed → couldn't find a price
5. Generates `review.html` — interactive page with screenshots and editable price fields
6. If mismatches found: starts a local server and opens `review.html` in your browser
7. Edit prices in the browser → click **"Save to Spreadsheet"** → writes directly to the xlsx
8. Press Enter in terminal when done

**Output:**
- `screenshots/` folder with a .png per item
- `review.html` — interactive review page
- `FY27_Bills_Budget_Updated.csv` — CSV with final prices (backup)

### 3. Download screenshot images for upload

The screenshots in `screenshots/` are named to match "Item Name" exactly. Copy whichever ones you need into `downloads/` for the automation script to upload them:

```bash
# Copy all screenshots to downloads folder
cp screenshots/*.png downloads/
```

Or just the ones you need for a specific bill.

### 4. Submit items to CampusLabs

```bash
source .venv/bin/activate
python automation.py
```

**What it does:**
1. Shows available bill titles — pick one
2. Prompts for the bill URL (the CampusLabs edit page for the specific bill)
3. Prompts for your GT username and password
4. Shows pre-flight check: all items with their costs, quantities, and whether a file exists in `downloads/`
5. Asks: **Clear existing items** (start fresh) or **Keep existing** (skip duplicates)?
6. Logs into CampusLabs, navigates to the bill, and for each item:
   - Checks if it already exists (deduplication)
   - Fills in name, description, quantity, price
   - Uploads the matching file from `downloads/` if found
   - Clicks Save and verifies it actually saved
   - Retries up to 3 times if something fails
7. Prints a final summary of successes, skips, and failures

**Options when running:**
- **Option 1: Clear all** — deletes every existing line item in the section first, then re-adds everything. Use when you've changed prices and want a clean slate.
- **Option 2: Keep existing** — only adds items not already in the section. Use if the script got interrupted and you want to resume.

### 5. Re-running after changes

If you update prices or add items in the spreadsheet:
1. Re-run `automation_screenshots.py` to get new screenshots and verify prices
2. Re-run `automation.py` and choose **Option 1 (Clear all)** to replace existing items with the updated data

## File Structure

```
finance/
├── automation.py              # Submits items to CampusLabs
├── automation_screenshots.py  # Scrapes prices, takes screenshots, generates review page
├── review_server.py           # Local server for review.html to save to xlsx
├── engage_tools.py            # SharePoint download utility (requires Azure app setup)
├── requirements.txt           # Python dependencies
├── .env.example               # Template for Azure/API config
├── .gitignore
├── downloads/                 # Put item images here (named same as Item Name)
├── screenshots/               # Generated screenshots from scraper
└── review.html                # Generated interactive review page
```

## Troubleshooting

**Script shows no bill titles:**
- Check that `Bill Title` is filled in for each item row (not just a header row)

**Screenshots don't show prices:**
- Some sites block headless browsers. The screenshot is still useful as proof of the product page.
- Prices from the spreadsheet are preserved regardless.

**CampusLabs save button doesn't work:**
- Manually click Save in the browser — the script will detect it and continue.

**"No file for item":**
- Put the image in `downloads/` named exactly like the Item Name column (e.g. `hose.png`)

**Want to clear token cache (force re-auth):**
```bash
rm .token_cache.bin
```

## Notes
- Images in `downloads/` must have the **same exact name** as the "Item Name" column (with .png/.jpg/.pdf extension)
- The review.html page requires `review_server.py` to be running (handled automatically by the screenshot script) to save changes back to the spreadsheet
- OneDrive sync propagates xlsx changes to SharePoint automatically
- `.env` and `.token_cache.bin` are gitignored — credentials stay local
