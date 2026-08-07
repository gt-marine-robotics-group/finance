# MRG Finance & Purchasing

Georgia Tech Marine Robotics Group — bill request automation and purchasing management.

## For Team Members (adding items to buy)

1. Open the web app: `http://<sim-pc-tailscale-ip>:5000`
2. Enter your name + password (`boats0519`)
3. Quick-add items from the dashboard, or use "+ Add Item" for the full form
4. Paste a link — price/vendor auto-fills in background

## For Officers (organizing bills)

1. Open the web app → dashboard
2. Items in **Backlog** are waiting to be assigned
3. Click **"Create Bill from Backlog"** → select items → pick existing bill or create new
4. The bill appears on SharePoint immediately
5. When ready to submit to CampusLabs: run `automation.py --fresh` from your laptop

## Submitting Bills to CampusLabs

```bash
cd finance
python automation.py --fresh
```

- `--fresh` downloads the latest xlsx + screenshots from SharePoint before running
- Requires: GT login, Duo MFA, Chrome, rclone configured

## Creating Purchase Requests

```bash
python automation_purchase.py --fresh
```

- Groups items by vendor (one request per vendor)
- Pre-fills the Engage purchase request form
- Requires: bill must be approved first (status: "bill approved")

## Statuses

| Status | Meaning |
|--------|---------|
| bill requested | Submitted to CampusLabs, waiting for approval |
| bill submitted | Form completed |
| bill approved | Approved — ready to purchase |
| pending purchase | Approved but not yet ordered |
| purchased - SOFO | Bought with SOFO card |
| purchased - cash | Bought with personal funds |
| purchased - awaiting reimbursement | Waiting for reimbursement |
| arrived | Item received |
| review requested | Needs review before proceeding |

## Editing the Spreadsheet Manually

**Yes, you can!** The web app doesn't own the data.

- **Add to backlog:** Add a row to TestTable on the "Test" sheet
- **Create a bill:** Add a "Request N" separator row (Bill Title = "Request N", empty Item Name), then item rows below
- **Edit items:** Edit any cell. Hit Sync in the web app to see changes
- **Order tracking:** Type Bill Item IDs into column B on the Ordering sheet — details auto-populate

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Web app shows stale data | Hit Sync button on dashboard |
| Can't add items | Graph API token may have expired — ask an officer to re-run `rclone config` on SIM PC |
| Screenshots not showing | They take ~10s per item after adding |
| automation.py can't find screenshots | Run with `--fresh` flag |
| Service not running | `sudo systemctl restart mrg-web-app` |
