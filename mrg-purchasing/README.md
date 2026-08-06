# MRG Purchasing Web App

Mobile-friendly web app for adding items and organizing bill requests. Runs on the SIM PC, accessible from any phone on Tailscale.

## Setup (first time)

```bash
cd mrg-purchasing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### rclone (for syncing xlsx from SharePoint)

```bash
rclone config
# Type: onedrive → SharePoint site → Marine Robotics Group → Documents
# See main README for detailed steps
```

### Run it

```bash
python app.py
# Open http://localhost:5000 or http://<tailscale-ip>:5000
# Password: boats0519
```

### Run as a service (24/7)

```bash
sudo cp mrg-purchasing.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mrg-purchasing
sudo systemctl start mrg-purchasing
```

**Resource usage:** Idles at ~30MB RAM, 0% CPU. Screenshots briefly use ~200-400MB. Will not interfere with Gazebo sims (capped at 25% CPU, 512MB RAM, low priority).

## Architecture

```
Phone → Flask app → Graph API → SharePoint xlsx (TestTable / BillsT)
                  → Chromium → screenshots → Graph API → SharePoint
```

All writes go directly to SharePoint via Microsoft Graph API (instant, no file upload, no lock issues). Reads come from a local cached copy of the xlsx (synced via rclone).

## Project Structure

```
mrg-purchasing/
├── app.py                  # Flask routes, auth, CRUD
├── xlsx_manager.py         # Graph API writes, rclone reads, xlsx parsing
├── screenshot_worker.py    # Background screenshots + price scraping
├── templates/              # Jinja2 HTML templates
│   ├── base.html          # Nav + flash messages
│   ├── dashboard.html     # Main page: quick-add, backlog, bills
│   ├── add_item.html      # Full add form with link fetch
│   ├── edit_item.html     # Edit bill item
│   ├── edit_queue_item.html # Edit backlog item
│   ├── bill_view.html     # Bill detail + export
│   ├── create_bill.html   # Select backlog items → new bill
│   ├── copy_to_bill.html  # Copy item between bills
│   ├── login.html         # Password gate
│   └── _item_card.html    # Reusable item card partial
├── static/style.css        # Mobile-first CSS
├── screenshots/            # Local screenshot cache (by bill title)
├── mrg-purchasing.service  # systemd unit file
├── Dockerfile              # For Railway/cloud deployment
├── start.sh                # Docker entrypoint
├── railway.toml            # Railway config
├── requirements.txt
├── .env.example
└── .gitignore
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| SECRET_KEY | (dev key) | Flask session secret |
| LOGIN_PASSWORD | boats0519 | Shared team password |
| RCLONE_REMOTE | onedrive:OPS-1.../FY27_Bills_Budget.xlsx | rclone path to xlsx |
| LOCAL_XLSX_PATH | ~/mrg/finance/FY27_Bills_Budget.xlsx | Local xlsx cache |
| XLSX_SHEET_NAME | Bills | Main bills sheet |
| XLSX_QUEUE_SHEET_NAME | Test | Backlog/queue sheet |
| PULL_INTERVAL_SECONDS | 300 | How often to sync from SharePoint |
| MAX_SCREENSHOT_STORAGE_MB | 500 | Cleanup threshold |
| PORT | 5000 | Web server port |

## Key Behaviors

- **Quick-add:** Type name + optional link → instant add to SharePoint TestTable
- **Auto-fill:** If link provided, scrapes price/vendor in background (~10 seconds)
- **Create Bill:** Select backlog items → inserts "Request N" separator + items into BillsT
- **Copy to Bill:** Duplicate item + screenshot to another bill
- **Screenshots:** Taken automatically, uploaded to SharePoint, served in app
- **Manual edits welcome:** Edit the xlsx directly — hit 🔄 Sync to see changes in app
