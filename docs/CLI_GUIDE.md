# CLI guide

[Install the CLI and run requests using the README](../README.md#2-optional-install-the-command-line-tool). This reference covers the one-time connection, file locations, and additional commands.

## Connect SharePoint once

Install [rclone](https://rclone.org/install/) for your operating system, then open Terminal or PowerShell:

```text
rclone config
```

Create a remote connection with these settings. Select menu entries **by their labels**; the option numbers can change. The connection uses rclone's [Microsoft OneDrive / SharePoint backend](https://rclone.org/onedrive/).

1. Choose New remote and name it `onedrive` (lowercase).
2. Choose Microsoft OneDrive as the storage type.
3. Leave client ID and client secret at their defaults unless the team has supplied an application configuration.
4. Complete browser authentication using your GT account and Duo.
5. Choose the SharePoint site option and enter `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup`.
6. Select the site's Documents library, confirm the configuration, and quit.

Check that you can see the finance folder:

```text
rclone ls "onedrive:OPS-1 Operations/FY27 Finances"
```

Look for `FY27_Bills_Budget.xlsx`. If it is missing, check the site/library choice and your permissions with the finance officer before continuing.

## Choose a working folder

Use a dedicated folder for finance work. These commands create one in your user folder and enter it.

macOS / Linux:

```bash
mkdir -p "$HOME/mrg-finance-work"
cd "$HOME/mrg-finance-work"
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\mrg-finance-work"
Set-Location "$env:USERPROFILE\mrg-finance-work"
```

Download the master workbook from the [SharePoint link in the README](../README.md#1-fill-in-the-shared-excel-sheet) into this folder, keeping the exact name `FY27_Bills_Budget.xlsx`. Do not use a renamed download such as `FY27_Bills_Budget (1).xlsx`.

Point all helpers at this workbook. Run the appropriate line **after entering your working folder in each new terminal session**:

macOS / Linux:

```bash
export FINANCE_XLSX_PATH="$PWD/FY27_Bills_Budget.xlsx"
```

Windows PowerShell:

```powershell
$env:FINANCE_XLSX_PATH = Join-Path (Get-Location).Path "FY27_Bills_Budget.xlsx"
```

Run `mrg-finance doctor` and verify the printed target path. Save edits in the shared workbook before using `--fresh`. Avoid editing the local workbook while a request is running; purchase automation writes links to it and attempts to upload the file.

### Workbook selection and synchronization

The main CLI uses `FINANCE_XLSX_PATH` if set. Otherwise, it looks for the named workbook in the current directory, then `~/mrg/finance/`, then the existing macOS OneDrive fallback. The main `mrg-finance` command does **not** accept `--excel-path`; that flag exists on some underlying scripts.

Setting the environment variable explicitly is useful because not all helper scripts share the main CLI's path logic. The standalone report builder also prefers a workbook in the current directory or `~/mrg/finance/` before its supplied path; keep the current-directory copy and configured path the same.

`--fresh` attempts to pull the workbook and screenshots. It does not guarantee a download: transfers use `--update`, and failures may leave the command using a local copy. The purchase workflow also attempts to push the workbook after saving request links. Verify the result in SharePoint, particularly if someone else has been editing it.

## Other commands

Use `mrg-finance COMMAND --help` for accepted options. Replace example names and IDs with values from your workbook.

| Command | Purpose |
| --- | --- |
| `mrg-finance doctor --fresh` | Synchronize, then check the workbook for common data problems. |
| `mrg-finance report --fresh --order "260910_amazon_gburdell3"` | Generate the Budget vs Quoted Excel and CSV reports. Verify live prices and Engage references before using them. |
| `mrg-finance price-check --fresh --bill "RobotX Testing Equipment Bill"` | Compare current product prices against the bill's recorded costs. |
| `mrg-finance screenshots --fresh --bill "RobotX Testing Equipment Bill"` | Capture product screenshots; existing captures are normally preserved. This command also attempts to upload screenshots. |
| `mrg-finance review --bill "RobotX Testing Equipment Bill"` | Open the screenshot/price comparison page. Saving price changes writes to the workbook, so review the proposed edits first. |

`--bill` and `--order` skip interactive selection on commands that support them. Quote values containing spaces. Request commands accept `--no-review` to skip the optional comparison page; this does not remove the need to review the Engage form.

Some screenshot options appear in help but are not handled by the current screenshot command. Use the dedicated `review` command to open the comparison page. Automatic cart creation is a convenience: verify the resulting cart or build it manually.

## Screenshots and generated reports

For bill and purchase scripts, the working-folder layout is:

```text
mrg-finance-work/
├── FY27_Bills_Budget.xlsx
└── screenshots/
    ├── RobotX Testing Equipment Bill/
    │   └── Product name.png
    └── 260910_amazon_gburdell3/
        ├── cart.png
        ├── Budget_vs_Quoted_Detail_260910_amazon_gburdell3.xlsx
        └── Budget_vs_Quoted_Detail_260910_amazon_gburdell3.csv
```

Use the paths printed by the tool. The top-level screenshot command and its initial sync use a screenshots folder beside the installed module, while bill/purchase scripts use the working folder. The review HTML is also generated beside the installed module. Do not assume these are the same directory in a global installation.

If a product page blocks automated capture, take the screenshot in your normal browser and save it under the matching bill folder. Use PNG for predictable matching. Keep the item name recognizable; replace filename-invalid characters with underscores (for example, `M2.5 bolts` can be saved as `M2_5 bolts.png`). Check the capture is readable and shows the correct variant and price.

For a purchase, save manual cart evidence to `screenshots/<Order ID>/cart.png` under the working folder. Check both attachments on Engage even if the terminal reports that uploads were attempted.

## Update an installed tool

Use the [uv tool commands](https://docs.astral.sh/uv/guides/tools/) to manage the installation. To reinstall from the current repository version:

```text
uv tool install --force --refresh --python 3.12 git+https://github.com/gt-marine-robotics-group/finance.git
mrg-finance --help
```

For editing the code, use [Development](DEVELOPMENT.md). For failed installs, browser prompts, or sync failures, use [Troubleshooting](TROUBLESHOOTING.md).
