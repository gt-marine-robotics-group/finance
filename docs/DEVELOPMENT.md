# Development Guide

## Repo Structure

```
finance/
├── web-app/                     ← Flask web app (runs on SIM PC)
│   ├── app.py                   # Routes, auth, CRUD
│   ├── xlsx_manager.py          # Graph API writes, rclone reads
│   ├── screenshot_worker.py     # Background Chromium screenshots + price scraping
│   ├── templates/               # Jinja2 HTML
│   ├── static/style.css         # Mobile-first CSS
│   ├── screenshots/             # Local screenshot cache (gitignored)
│   ├── mrg-purchasing.service   # systemd unit file
│   ├── Dockerfile               # For cloud deployment
│   └── README.md                # Web app specific setup
├── automation.py                ← Bill submission to CampusLabs Engage
├── automation_purchase.py       ← Purchase request form filler
├── automation_screenshots.py    ← Legacy CLI screenshot tool
├── engage_tools.py              ← SharePoint download utility
├── review_server.py             ← Legacy review page
├── requirements.txt             ← CLI script dependencies
├── .env.example                 ← Config template
├── README.md                    ← User-facing docs
└── DEVELOPMENT.md               ← You are here
```

## Architecture

```
Web app (SIM PC)                          CLI scripts (officer laptop)
─────────────────                         ──────────────────────────────
Flask + Graph API                         Selenium + OneDrive sync
writes cells directly to SharePoint       reads local OneDrive copy
takes screenshots via Chromium            uploads screenshots to Engage
accessible via Tailscale :5000            requires GT login + Duo MFA
```

Both connect through SharePoint xlsx as the shared data layer.

## Web App Setup

```bash
cd web-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### rclone Setup (for SharePoint sync)

```bash
rclone config
# Type: onedrive → option 3 (URL) → https://gtvault.sharepoint.com/sites/MarineRoboticsGroup → Documents (option 3)
# Auth: run `rclone authorize "onedrive"` on a machine with a browser, paste token
```

### systemd Service

```bash
sudo cp web-app/mrg-purchasing.service /etc/systemd/system/mrg-web-app.service
sudo systemctl daemon-reload
sudo systemctl enable mrg-web-app
sudo systemctl start mrg-web-app
```

Resource limits: 25% CPU, 512MB RAM, Nice=10. Won't affect Gazebo.

## Graph API Details

- Token stored in `~/.config/rclone/rclone.conf` (rclone's OneDrive auth)
- Drive ID: `b!N2jMdT_mCUGwm_kbNtcriy0U15MgYvlDp9Y3NuMGGZ4kw04Ai38XSIlj5IWhyCRr`
- File ID: `014676AIQHNE4YS3DICNEZLNSKL3YEEGA4`
- Scopes: `Files.ReadWrite.All`

### Writing to the spreadsheet

**Never overwrite formula columns** (Bill Item ID = col A, Total Cost = col K).

For BillsT: use `_patch_row_values()` which writes individual cells, skipping formula columns.

For TestTable: use `graph_add_row()` (rows/add endpoint) since TestTable has no formulas.

### Tables

| Sheet | Table | Purpose |
|-------|-------|---------|
| Bills | BillsT | All bill items (formulas in cols A, K) |
| Test | TestTable | Backlog/queue (no formulas) |
| Ordering | OrderT | Purchase tracking (formulas pull from BillsT) |

## Spreadsheet Conventions

- **Separator rows:** Bill Title = "Request N", Item Name = empty. Mark bill group boundaries.
- **Negative IDs:** Metadata rows (Liquid allocations). Filtered out by web app.
- **Status values:** lowercase, e.g. "bill requested", "bill approved"
- **Formulas extend to ~row 500.** Write to existing empty rows, don't insert.

## CLI Scripts Setup (Mac/laptop)

```bash
cd finance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires:
- Chrome (automatically managed by Selenium)
- OneDrive syncing the MRG SharePoint
- rclone configured (for `--fresh` flag)

## Code Map

For contributors adding features, here is how the codebase is structured:

```
finance/
├── web-app/                 # Flask web dashboard (http://localhost:5000)
├── automation_purchase.py   # Purchase request submission flow & Amazon cart launcher
├── engage_bill_lookup.py    # Engage DOM scraper (finds section titles & line numbers)
├── automation.py            # Bill request submission flow & item creation logic
├── automation_screenshots.py# Price scraper integration & review HTML generator
├── price_scraper.py         # Live price scraping (Amazon, McMaster, etc.) & ASIN parser
├── review_server.py         # Local HTTP server (port 8321) for saving price edits to Excel
├── review.html              # Side-by-side screenshot review GUI
├── mrg.py                   # CLI entrypoint for `mrg-finance` commands
└── engage_tools.py          # SharePoint download utility
```

### Key Functions to Know:
- **`lookup_bill_item_locations()`** in `engage_bill_lookup.py`: Navigates to an Engage bill URL, clicks the "Budget" tab, traverses section headers, and returns `{item_name: {section, section_line_number}}`.
- **`generate_amazon_cart_url()`** in `price_scraper.py`: Parses Amazon URLs for ASINs (`/dp/B0...`) and builds the AWS cart URL.
- **`_open_incognito_browser()`** in `automation_purchase.py`: Launches Chrome in `--incognito` mode across macOS, Linux, and Windows.

## Adding Features

### Web app changes
1. Edit files in `web-app/`
2. Test locally: `cd web-app && python app.py`
3. Deploy: `git push` then `sudo systemctl restart mrg-web-app`

### CLI script changes
1. Edit `automation.py` or `automation_purchase.py`
2. Test: `python automation.py` (will prompt for credentials)
3. Commit and push — other officers pull via `git pull`

## Token Refresh

The rclone token expires periodically. To refresh:
1. On a machine with a browser: `rclone authorize "onedrive"`
2. Copy the token to the SIM PC's `~/.config/rclone/rclone.conf`
3. Or re-run `rclone config` on the SIM PC and paste the token when prompted
