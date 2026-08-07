# MRG Finance & Purchasing

Georgia Tech Marine Robotics Group — bill request automation and purchasing management.

## What's in this repo

```
finance/
├── web-app/                 ← Web app (runs on SIM PC, accessible from phone)
├── automation.py            ← Submits bills to CampusLabs Engage (run from laptop)
├── automation_screenshots.py ← CLI screenshot tool (legacy, web app replaces this)
├── automation_purchase.py   ← Purchase request form filler
├── review_server.py         ← Local review page server (legacy)
├── engage_tools.py          ← SharePoint download utility
├── requirements.txt         ← Dependencies for automation scripts
├── .env.example             ← Config template for automation scripts
└── README.md                ← You are here
```

## Quick Start

### For team members (adding items to buy)

1. Open the web app on your phone: `http://<sim-pc-tailscale-ip>:5000`
2. Password: `boats0519`
3. Quick-add items from the dashboard, or use "+ Add Item" for the full form
4. Paste a link and the app auto-fills price/vendor in background

### For officers (organizing bills)

1. Open the web app → dashboard
2. Items in **Backlog** are waiting to be assigned
3. Click **"Create Bill from Backlog"** → select items → name the bill
4. The bill appears on SharePoint immediately with a "Request N" separator row
5. When ready to submit to CampusLabs: run `automation.py` from a laptop with OneDrive

### Running automation.py (bill submission to CampusLabs)

```bash
cd finance
source .venv/bin/activate
python automation.py
```

Requires: GT login + Duo MFA, OneDrive sync, Chrome installed.

## CLI Scripts vs Web App

### Web App (`web-app/`) — runs on SIM PC

**Purpose:** Day-to-day item management for the whole team.

| Feature | How |
|---------|-----|
| Add items to backlog | Quick-add bar or full form |
| Organize items into bills | "Create Bill from Backlog" |
| Take screenshots | Automatic on add (background) |
| Edit items | Tap Edit on any item |
| Track status | Status badges on each item |
| View bills | Collapsible sections on dashboard |

**Who uses it:** Everyone on the team (from phone/laptop)  
**Where it runs:** SIM PC (always on, accessible via Tailscale)  
**Writes to:** SharePoint xlsx via Graph API (instant, no file lock issues)

---

### CLI Scripts — run from officer's laptop

**Purpose:** Interact with CampusLabs Engage (requires GT login + Duo MFA + browser).

| Script | Purpose |
|--------|---------|
| `automation.py` | Submit a bill request to CampusLabs Engage |
| `automation_purchase.py` | Fill out purchase request forms on Engage |
| `automation_screenshots.py` | (Legacy) Take screenshots — web app does this now |

**Who uses it:** Officers only  
**Where it runs:** Any laptop with OneDrive sync + Chrome  
**Reads from:** Local OneDrive-synced xlsx + screenshots folder

### How they connect

```
Web app adds items → SharePoint xlsx ← OneDrive syncs to laptop
Web app takes screenshots → SharePoint ← OneDrive syncs to laptop
                                        ↓
                            automation.py reads xlsx + screenshots
                            → submits bill to CampusLabs Engage
                                        ↓
                            automation_purchase.py
                            → creates purchase requests on Engage
```

The web app and CLI scripts never conflict because:
- Web app writes via Graph API (cell-level, no file lock)
- CLI scripts only READ the xlsx (via OneDrive sync)
- Screenshots sync via OneDrive from SharePoint

---

## Purchase Request Flow

### Creating a purchase request from a bill

1. **Bill must be approved** on CampusLabs first (status: "bill approved")
2. Open the bill on the web app → verify items, prices, screenshots
3. On your laptop, run `automation_purchase.py` to fill the Engage purchase form
4. Purchase request groups items by **vendor** (one request per vendor)

### Tracking: Allocated vs Actual Cost

The **Ordering sheet** (OrderT) tracks what was actually purchased:

1. Type Bill Item IDs into column B → item details auto-populate from BillsT
2. **Allocation** (column G) = original price × qty from the bill
3. **Total Cost** (column H) = what you actually paid (manual entry)
4. **Cost Overrun** (column I) = Total Cost - Allocation (auto-calculated)

### Before ordering, check if prices changed

- Web app scrapes current prices when items are added
- Re-check before ordering: open the product link, compare to Allocation
- If price increased significantly, flag it before proceeding

### Statuses

| Status | Meaning |
|--------|---------|
| bill requested | Bill submitted to CampusLabs, waiting for approval |
| bill submitted | Bill form completed |
| bill approved | Approved by SGA — ready to purchase |
| pending purchase | Approved but not yet ordered |
| purchased - SOFO | Bought with SOFO card |
| purchased - cash | Bought with personal funds |
| purchased - awaiting reimbursement | Bought, waiting for reimbursement |
| arrived | Item received |
| review requested | Needs review before proceeding |

```
Team member's phone → Web app (SIM PC) → Graph API → SharePoint xlsx
                                        → Screenshots (headless Chromium)

Officer's laptop → automation.py → CampusLabs Engage (Selenium)
                 ↑ reads xlsx via OneDrive sync
                 ↑ reads screenshots via OneDrive sync
```

**Source of truth:** `FY27_Bills_Budget.xlsx` on SharePoint  
**Queue/backlog:** "Test" sheet → TestTable  
**Bills:** "Bills" sheet → BillsT  
**Screenshots:** SharePoint `OPS-1 Operations/FY27 Finances/screenshots/<bill_title>/`

## Can I manually edit the spreadsheet?

**Yes!** The web app reads from SharePoint — it doesn't own the data.

- **Add to backlog manually:** Add a row to the TestTable on the "Test" sheet. Web app picks it up on next refresh.
- **Create a bill manually:** Add a "Request N" separator row (Bill Title = "Request N", empty Item Name), then add item rows below it with the Bill Title filled in.
- **Edit items:** Edit any cell directly in Excel/SharePoint. Hit 🔄 Sync in the web app to see changes.

The only thing that could conflict: if you and the web app write to the same row at the same exact second (unlikely with a small team).

## Web App Setup (SIM PC)

See [web-app/README.md](web-app/README.md) for full setup details.

**TL;DR:**
```bash
cd web-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Runs as a systemd service for 24/7 availability:
```bash
sudo systemctl start mrg-web-app   # start
sudo systemctl restart mrg-web-app # restart after code changes  
sudo systemctl stop mrg-web-app    # stop
sudo journalctl -u mrg-web-app -f  # view logs
```

## Spreadsheet Structure

### Bills sheet (BillsT table)

| Column | Description |
|--------|-------------|
| Bill Item ID | Auto-incremented integer |
| Bill No. | CampusLabs bill number |
| Bill Title | Full bill name (groups items) |
| Item Name | Product name |
| Status | "Bill Requested", "bill approved", etc |
| Budget Section | e.g. "B03 - General Inventoried Goods" |
| Vendor | Amazon, DigiKey, etc |
| Description | What it's for |
| Quantity | How many |
| Cost | Unit price |
| Total Cost | Quantity × Cost |
| Link | Product URL |
| File URL | Screenshot URL |
| Person Requesting | Who asked for it |

**Separator rows:** `Bill Title = "Request N"` with empty Item Name. These mark bill group boundaries.

### Test sheet (TestTable)

Same structure minus Status, Total Cost, File URL, Person Requesting. This is the backlog/queue.

## Screenshots

Screenshots are stored at:
- **Local (SIM PC):** `web-app/screenshots/<bill_title>/<item_name>.png`
- **SharePoint:** `OPS-1 Operations/FY27 Finances/screenshots/<bill_title>/<item_name>.png`
- **Backlog items:** saved under `_queue/` until assigned to a bill

When a bill is created from backlog, screenshots are copied to the bill's folder.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Web app shows stale data | Hit 🔄 Sync on dashboard |
| Can't add items | Check if Graph API token expired — re-run `rclone config` |
| Screenshots not working | Check `chromium-browser --version` on SIM PC |
| automation.py can't find screenshots | They sync via OneDrive from SharePoint |
| "File locked" in logs | Someone has the xlsx open — auto-retries later |
| Service not running | `sudo systemctl status mrg-web-app` |
