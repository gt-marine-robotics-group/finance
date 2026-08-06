# MRG Purchasing

Mobile-friendly web app for Marine Robotics Group (Georgia Tech) to manage purchasing. Team members add items, officers organize them into bills for CampusLabs Engage submission.

## How It Works

```
Team member's phone → Web app (Railway) → reads/writes xlsx via rclone ↔ SharePoint
                                         → takes screenshots in background (headless Chrome)
```

- **Source of truth:** `FY27_Bills_Budget.xlsx` on SharePoint
- **Sync:** rclone pulls every 5 min + pull-before-write + push-after-write
- **Screenshots:** Headless Chromium captures product pages in background
- **CampusLabs submission:** Still done manually via `automation.py` from a laptop with OneDrive sync

## Local Development

```bash
cd mrg-purchasing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your values

python app.py
```

Open http://localhost:5000 — password is `boats0519`.

For local dev without rclone, just place a copy of `FY27_Bills_Budget.xlsx` at the path specified in `LOCAL_XLSX_PATH`.

## Deploy to Railway

### 1. Create Railway project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and init
railway login
railway init
```

### 2. Set up rclone auth (one-time)

On your laptop (which has a browser):

```bash
rclone authorize "onedrive"
```

This opens a browser for GT SSO login. After auth, it prints a token JSON. Copy it.

Then create your rclone config:

```ini
[onedrive]
type = onedrive
token = {"access_token":"...","token_type":"Bearer",...}
drive_type = documentLib
drive_id = YOUR_DRIVE_ID
```

To find your `drive_id`, run:
```bash
rclone config
# Choose: Microsoft OneDrive → SharePoint site
# It will show available drives — pick "Documents - Marine Robotics Group"
```

### 3. Set environment variables on Railway

In the Railway dashboard (or CLI):

```bash
railway variables set SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
railway variables set LOGIN_PASSWORD="boats0519"
railway variables set RCLONE_REMOTE="onedrive:Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
railway variables set LOCAL_XLSX_PATH="/root/mrg-finance/FY27_Bills_Budget.xlsx"
railway variables set XLSX_SHEET_NAME="Bills"
railway variables set RCLONE_CONFIG_CONTENT="$(cat ~/.config/rclone/rclone.conf)"
```

### 4. Deploy

```bash
railway up
```

Railway auto-detects the Dockerfile and deploys. You'll get a public URL like `https://mrg-purchasing-production.up.railway.app`.

### 5. Custom domain (optional)

In Railway dashboard → Settings → Networking → add your custom domain.

## Project Structure

```
mrg-purchasing/
├── app.py                  # Flask app - routes, auth, CRUD
├── xlsx_manager.py         # Read/write xlsx with rclone sync
├── screenshot_worker.py    # Background screenshot thread (Selenium)
├── templates/
│   ├── base.html          # Base layout with nav
│   ├── login.html         # Password gate
│   ├── dashboard.html     # Items grouped by bill
│   ├── add_item.html      # New item form
│   ├── edit_item.html     # Edit/move/delete item
│   ├── bill_view.html     # Bill detail with table + export
│   └── _item_card.html    # Reusable item card partial
├── static/
│   └── style.css          # Mobile-first responsive CSS
├── screenshots/            # Generated screenshots (gitignored)
├── Dockerfile             # Python + Chromium + rclone
├── start.sh               # Entrypoint: cron + gunicorn
├── railway.toml           # Railway deployment config
├── requirements.txt
├── .env.example
└── .gitignore
```

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Login | `/login` | Shared password gate |
| Dashboard | `/` | All items grouped by bill + backlog |
| Add Item | `/add` | Form to add new item |
| Edit Item | `/edit/<id>` | Edit fields, move to bill, delete |
| Bill View | `/bill/<title>` | Table view, total cost, CSV export |

## Workflow

1. **Team member** opens the app on their phone → adds an item (name, cost, qty, link, vendor)
2. Item goes to **Backlog** (no bill assigned)
3. **Officer** opens dashboard → edits item → assigns it to a bill title
4. Officer clicks into **Bill View** → reviews items, total cost
5. When ready to submit to CampusLabs:
   - Export CSV or just confirm items look correct
   - On a laptop with OneDrive sync, run `automation.py` to submit the bill

## Notes

- The xlsx may have conditional formatting — openpyxl only modifies cell values, preserving formatting
- Item names are normalized (extra whitespace trimmed) on read
- Screenshots are named after the item (sanitized filename)
- If rclone fails (token expired), the app still works with the last-synced local copy
- To refresh the rclone token: re-run `rclone authorize "onedrive"` on your laptop, update the env var
