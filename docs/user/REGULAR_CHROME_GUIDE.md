# Capture evidence in regular Chrome

Use this when a vendor keeps repeating its CAPTCHA in the tool's Selenium window. This mode uses installed Google Chrome and your existing browser profile on macOS, Windows, and Linux. It does not use WebDriver or remote-debugging flags. Vendor access is still subject to the site's verification; switching browsers is not a guarantee that a challenge will succeed.

## Start capture

```bash
mrg-finance screenshots --browser chrome
```

Select the bill. Chrome opens a local connection page with the extension folder for your operating system. The CLI creates it automatically under the current user's account:

| Operating system | Extension folder |
| --- | --- |
| macOS | `~/Library/Application Support/mrg-finance/evidence-extension` |
| Windows | `%LOCALAPPDATA%\mrg-finance\evidence-extension` |
| Linux | `~/.local/share/mrg-finance/evidence-extension`, or `$XDG_DATA_HOME/mrg-finance/evidence-extension` when configured |

These locations apply to each user's own account. Expand **Show the full folder path on this computer** on the connection page to copy the resolved path into Chrome's folder chooser.

## Install once

1. In the same Chrome profile, open `chrome://extensions` in another tab.
2. Enable **Developer mode** and click **Load unpacked**.
3. Select the **extension folder for your account**. The CLI prints its resolved path; the connection page shows it under **Show the full folder path on this computer**. On Mac, use Cmd+Shift+G in the folder chooser to paste that path.
4. Return to the connection page and reload it. It should say **Connected**.
5. Return to the Terminal and press Enter if it is waiting for setup.

The extension is bundled with the CLI and installed locally, rather than through the Chrome Web Store. Chrome grants it access to websites so it can read prices and capture product evidence from different vendors. The extension code uses only the product tab created for the connected CLI session; it has no arbitrary-script or cookie-export command. Its authenticated bridge listens only on `127.0.0.1` and stops when capture ends. See Chrome's [unpacked-extension instructions](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world) and [capture permissions](https://developer.chrome.com/docs/extensions/reference/api/tabs).

No Apple Events setting, operating-system screen-recording permission, new Python dependency, or Share-A-Cart extension is needed for this capture mode. Keep the extension installed between runs. After updating the CLI, click **Reload** on the **MRG Finance Evidence** extension card if the CLI asks you to reconnect. The extension's folder stays in the same place.

## Capture each product

The CLI opens product links in a separate tab in the connection window. Keep the connection tab open. Finish any vendor verification yourself, dismiss overlays, and scroll or zoom until the product name and price are visible. Return to the Terminal and press Enter to capture.

The image covers the **visible page**, not the entire scrolling document. The CLI reads the product price, saves the image and checked `.evidence.json` record, and writes the normal `screenshot_audit.csv`. It does not change approved prices in the master workbook. A CAPTCHA or access-denied page remains a diagnostic under `challenges/`, never usable bill evidence. A repeated challenge can be cancelled; Chrome stays open.

## Default and fallback modes

- `mrg-finance screenshots`: opens visible Selenium Chrome by default. At a challenge prompt, type `chrome` to switch to regular Chrome, Enter to recheck the current page, or `cancel` to stop that item.
- `mrg-finance screenshots --interactive`: the same visible mode; the flag is retained for existing commands.
- `mrg-finance screenshots --browser chrome`: starts directly in regular Chrome.
- `mrg-finance screenshots --browser selenium`: uses visible Selenium without offering the extension fallback.
- `mrg-finance screenshots --headless --bill "<Bill Title>"`: runs without a visible browser or verification prompts. Supplying the bill also skips the selection menu. Blocked items are recorded as challenges in the audit and are not usable bill evidence. Use this for unattended capture; regular-Chrome mode requires a visible window.

The on-demand screenshot step in `bill-request` also accepts `chrome` at a challenge prompt. You can instead capture first with `screenshots --browser chrome`; `bill-request` reuses valid evidence and does not require recapturing it.

## Local spreadsheet use

Download the workbook and edit it in Excel. Save and close it before running the tool. Either run the CLI from the folder containing `FY27_Bills_Budget.xlsx`, or explicitly select the file:

```bash
# macOS / Linux
export FINANCE_XLSX_PATH="/full/path/FY27_Bills_Budget.xlsx"
mrg-finance doctor
mrg-finance screenshots --browser chrome
mrg-finance bill-request
```

```powershell
# Windows PowerShell
$env:FINANCE_XLSX_PATH = "C:\full\path\FY27_Bills_Budget.xlsx"
mrg-finance doctor
mrg-finance screenshots --browser chrome
mrg-finance bill-request
```

Omit `--fresh` to use the local edits without downloading the cloud workbook. Check the printed **Workbook** path before proceeding. Product pages and Engage still require internet. Screenshot commands may upload evidence if rclone is configured; omitting `--fresh` controls the download, not every cloud operation.

## Troubleshooting

- **No Chrome found:** install Google Chrome. This mode uses your regular installed browser; it cannot download Chrome for Testing as a substitute.
- **Waiting for the extension:** use the same Chrome profile for installation and the connection page; reload the page after loading the extension.
- **Could not read the product page:** check the extension's site access, wait for loading to finish, and retry. Managed Chrome policies may prevent loading local extensions.
- **Extension stopped responding:** keep the connection tab open, reload the extension, and rerun the command. Finish one capture session before starting another.
- **CAPTCHA still loops:** try the same link in another ordinary tab to determine whether access fails outside the tool too. Do not accept a challenge image as the quote.
