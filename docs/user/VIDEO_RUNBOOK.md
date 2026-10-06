# MRG Finance: quick video recording script

Record **six short clips**, then join them into an 8–10 minute walkthrough. Follow the numbered sections below in order. Commands are ready to paste; **Say** is your narration; **Show** is the shot to keep. This assumes the feature changes have been merged into `main`.

Use your existing OneDrive-synced workbook. Keep your installed tools and rclone configuration. **No uninstall, clean clone, or test-suite demonstration is needed.**

## Before you press Record — five-minute setup

1. Choose two examples: a small funding bill with an editable Engage draft, and a pending purchase against a **separate, already approved budget or bill**. Each purchase order must use one vendor. Keep their menu numbers/IDs and any draft URL in a private note.
2. Save the synced workbook and let OneDrive finish syncing. Show it when needed, then **close Excel before the CLI writes links**. Close comparison reports before continuing their update/upload step.
3. Use Terminal at 18–20 pt, with Chrome/Excel alongside it. Turn on Do Not Disturb. Keep passwords, MFA, account details, and payment information out of recordings.
4. Create your recording folder and working directory:

   ```bash
   mkdir -p "$HOME/mrg/finance/scratch/video/raw" "$HOME/mrg/finance/scratch/video/exports" "$HOME/mrg/finance/scratch/video/demo"
   cd "$HOME/mrg/finance/scratch/video/demo"
   ```

   Run the video's commands from this Terminal. Screenshots/reports go into `demo/screenshots/`. Your workbook stays in OneDrive; no copy is needed. `scratch/` is ignored by Git.
5. Press **Shift–Command–5 → Record Selected Portion**. In Options, select your microphone, enable Show Mouse Clicks, and save to `/Users/aaronwu/mrg/finance/scratch/video/raw`. Record a 20-second test and play it back to check voice and text readability. [Apple recording instructions](https://support.apple.com/en-us/102618)

Stop with **Command–Control–Esc**. The Mac recorder has no pause button: stop before login, resume afterward, and name the continuation `-part2.mov`. Leave two seconds at each end. If you stumble, pause and repeat the sentence; keep the raw take.

Use actual requests you intend to prepare. `bill-request` writes to the live draft; `purchase` writes workbook links and fills/uploads into Engage. There is no dry-run mode. Rehearse without submitting the same request twice.

## Clip 1 — Install the CLI · 45–60 seconds

**Save as:** `01-install.mov`

**Say:** “MRG Finance uses our finance spreadsheet to prepare funding bills and purchase requests. I'll install it, connect SharePoint, then show both workflows.”

Run:

```bash
uv tool install --force "git+https://github.com/gt-marine-robotics-group/finance.git@main"
mrg-finance --help
mrg-finance purchase --help
```

**Show:** successful installation and the `bill-request`, `purchase`, `screenshots`, and `doctor` commands. Cut the download wait.

**Say:** “Automated is the default cart source. Amazon and DigiKey use their own Chrome cart windows. The personal flag skips automatic additions so I can build the cart myself.”

If uv is missing, install it using the [official uv instructions](https://docs.astral.sh/uv/getting-started/installation/). If `mrg-finance` is not found, run `uv tool update-shell` and reopen Terminal. Git is needed for this GitHub installation. Selenium Manager uses installed Chrome or downloads Chrome for Testing and its driver; the first uncached browser run needs internet. [Selenium browser management](https://www.selenium.dev/documentation/selenium_manager/)

**Overlay to add later:** `1. Install`

## Clip 2 — Install/connect rclone · 1–2 minutes

**Save as:** `02-rclone.mov`

**Say:** “OneDrive syncs the workbook I edit. rclone lets the CLI transfer the workbook and screenshots directly to and from SharePoint.”

Run:

```bash
brew install rclone
rclone version
rclone listremotes
```

If `onedrive:` already appears, **keep it** and go straight to the connection check. Explain the setup table on screen. If you need to demonstrate a new connection, run `rclone config` and use these choices:

| Prompt | Choose |
| --- | --- |
| New remote | `n` |
| Name | `onedrive` — exact lowercase name |
| Storage | Microsoft OneDrive / `onedrive` |
| Client ID / secret | Leave blank |
| Region / advanced config | Global/default; `n` for advanced |
| Browser authentication | `y`; GT account and Duo |
| Connection type | SharePoint site |
| Site URL | `https://gtvault.sharepoint.com/sites/MarineRoboticsGroup` |
| Library | Documents |
| Confirm / quit | `y`, then `q` |

Choose by label; wizard numbers can change. **Stop recording before authentication and keep it stopped through the final configuration summary**, which can show tokens. Resume for this connection check:

```bash
rclone lsf "onedrive:OPS-1 Operations/FY27 Finances"
```

**Show:** `FY27_Bills_Budget.xlsx` in the results.

**Say:** “The remote is named onedrive and points at the MRG SharePoint library. Fresh downloads the cloud copy before a command. Today I'll use my already synced workbook.”

Show `mrg-finance doctor --fresh` as a caption; omit `--fresh` from the remaining demo commands. Run a refresh only after checking the destination, closing Excel, and finishing OneDrive sync. Omitting `--fresh` skips the initial download; screenshot/purchase commands can still upload through configured rclone.

[Official rclone SharePoint setup](https://rclone.org/onedrive/) · [Homebrew rclone](https://formulae.brew.sh/formula/rclone)

**Overlay:** `2. Connect SharePoint` → `OneDrive: workbook sync | rclone: CLI transfers`

## Clip 3 — Show the workbook and doctor · 45–60 seconds

**Save as:** `03-workbook.mov`

**Show:** your funding example in Bills and your approved purchase example in Ordering.

**Say:** “Bills holds the funding items and approved costs. Ordering selects the items and quantities we're purchasing. Spreadsheet item IDs are different from Engage line numbers.”

Run:

```bash
mrg-finance doctor
```

**Check `Target file:`.** If it is your OneDrive workbook, continue. If it points somewhere else, run this on this Mac and repeat doctor:

```bash
export FINANCE_XLSX_PATH="$HOME/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
mrg-finance doctor
```

This selects the existing file; it does not copy it. You only need the export when auto-discovery picks the wrong file, and it applies to this Terminal session. Another Mac needs its own actual path.

**Say:** “Doctor checks common workbook data problems. I'll check its file path and resolve any warnings relevant to these examples.”

**Show:** path and diagnostic results. Close Excel after the shot. A new funding draft can legitimately lack an approved bill number; doctor does not verify every formula or live vendor page.

**Overlay:** `3. Check the workbook`

## Clip 4 — Screenshots and funding bill · 2 minutes

**Save as:** `04-bill.mov`, with `-part2` after GT login

**Say:** “First I'll capture product evidence, review it, and add the funding items to our Engage draft.”

Run:

```bash
mrg-finance screenshots --interactive
```

Select your prepared funding bill at **Select bill title or number**. Show one product page, its screenshot, and the printed `screenshot_audit.csv` in Excel. Review them, then close Excel. Keep the `.evidence.json` sidecars with the images; the bill flow verifies the URL and image bytes. The audit does not overwrite requested workbook costs.

Run:

```bash
mrg-finance bill-request
```

| When this happens | Do this |
| --- | --- |
| GT credentials / Duo | Stop recording; resume after authentication. |
| Bill-title menu | Select the same bill. |
| Missing Bill No. | Paste your prepared Engage draft edit URL. |
| Re-capture screenshots? | Type `n` after reviewing the captures. |
| Section/item preview; Proceed? | Check names, costs, quantities, and sections; press Enter to continue. |
| Existing items; Choice [1/2] | **Type `2`** to keep existing items and skip duplicates. Do not press Enter: the current default clears existing lines. |
| Automated entry | Record one complete item and screenshot upload. Cut repeated entry. |
| Completion | Show counts and inspect the draft; resolve failures before calling it complete. |

**Say:** “The CLI has prepared the funding draft. Approval happens later. For purchasing, I'll switch to a separate approved example.”

**Show:** the approved budget/bill and its pending order for five seconds. Submit the funding draft only when ready; CLI completion means line entry, not approval.

**Overlay:** `4. Prepare funding` → `Funding → approval → purchase`

## Clip 5 — Purchase · 3–4 minutes

**Save as:** `05-purchase.mov`, with continuations around sign-in

**Say:** “Prices can change after funding approval. Purchase checks the current cart, fills a comparison workbook, and uses that verified amount in Engage.”

Run the default workflow and select your prepared order:

```bash
mrg-finance purchase
```

There is **one preparation confirmation** and no cart-source menu. The product URLs determine the vendor, even if the Order ID still contains an older vendor name. For an optional personal Amazon demonstration, use `mrg-finance purchase --cart-source personal` instead; you add items yourself in the dedicated Chrome window.

Follow this checklist in order:

| Step / prompt | Action and shot to keep |
| --- | --- |
| Order selection | Select the prepared order. Show allocation, workbook path, and evidence directory. |
| Prepare and verify vendor cart? [Y/n] | Press Enter. |
| Change product links before building the cart? [y/N] | Press Enter for the planned demo. See the optional replacement clip below. |
| Product-price check | Show one current price versus approved cost. If over budget, Enter keeps it; a replacement HTTPS URL changes it. If unreadable, Enter tries the cart; manual price entry is optional. |
| Vendor Chrome opens | Complete sign-in/verification in **this** window off camera. Automatic mode attempts additions. If it needs help, check what's already added before adding again. Keep only this order's products and exact quantities. |
| Cart verification | Leave the cart page visible. Press Enter when prompted; DigiKey attempts automatic reading without this readiness prompt in automated mode. Show the verified items/subtotal. |
| Charges — Amazon | Enter the actual shipping, tax, and final vendor total without `$`. Enter uses zero only for shipping/tax when the vendor shows zero. **Type the final total explicitly.** Never treat uncalculated charges as zero. |
| Charges — DigiKey | Supported carts supply the quote automatically. GT accountant purchases use $0 shipping; the report retains the public shipping estimate separately. Merchandise and tax remain verified. |
| Share-A-Cart Link/Code | Create a fresh link with the extension in the vendor Chrome window and paste it. If automated Amazon offers a newly generated link, Enter accepts it after review. Show **Saved and verified Share-A-Cart URL in Ordering**. |
| Comparison workbook | Open the printed `.xlsx`. Show approved/cart prices, variance, and Cart Reconciliation charges. Funding references are pending at this point. **Close it.** |
| Continue to Engage? [Y/n] | Press Enter after review. `n` stops with the comparison saved. |
| GT credentials / Duo | Stop recording; resume after login. |
| Funding lookup | Show Menu → Budget lookup and verified section/line. Nonzero requested fees need funding references. |
| Review comparison spreadsheet | Show completed funding references, then close the report and press Enter. |
| Select Category/Account and SGA option | In Engage select the prompted **SGA Budget or SGA Bill**, then press Enter in Terminal. Use the source that actually funds this order. |
| Before upload | Show cart/amount recheck. Amazon asks you to reconfirm the final vendor total; supported DigiKey quotes recheck automatically. |
| Filled form | Show the fields below and both attachments. |
| Finish | Review/sign/submit manually. Only then press Enter at the submission prompt and confirm the real resulting URL. Show saved workbook links and the actual cloud-sync result. |

**Show these Engage fields:**

| Field | Expected content |
| --- | --- |
| Requested Amount | Verified payable amount; includes tax and applicable shipping |
| Description | Share-A-Cart link |
| Budget/Bill # and Request Line # | Verified funding number, section, line |
| Selected SGA Budget / SGA Bill answer | Quoted amounts and matching funding references |
| Payee and Payee Email | Vendor name/address and verified email when available; DigiKey uses `orders@digikey.com` |
| Attachments | `cart.png` and comparison `.xlsx` |

**Say:** “The amount matches the verified payable quote. Funding references and payee details go into their own fields. I review and submit the request myself.”

If recording **form preparation only**, finish before submission and label the result `Prepared form — not submitted`. Stop recording, then end the waiting CLI with Control-C. Do not acknowledge a submission that did not happen.

**Overlays:** `5. Verify and prepare purchase`, then `Verified payable amount = Engage amount`. Highlight one field at a time.

## Clip 6 — Result and closing · 20–30 seconds

**Save as:** `06-result.mov`

**Show:** saved Share-A-Cart/request links in Ordering, plus the comparison workbook.

**Say:** “The workbook keeps our funding references and order links. The CLI prepares evidence, verifies the current quote, and fills Engage. The bill and purchase guides contain the full steps.”

Link [Bill requests](BILL_REQUEST_GUIDE.md), [Purchase requests](PURCHASE_GUIDE.md), and [CLI usage](CLI_GUIDE.md) in the video description.

## If a step needs attention

- **CAPTCHA:** solve it in the visible Chrome window, then Enter to retry. Challenge screenshots stay under `challenges/`, separate from usable evidence. If it keeps looping, cancel and resolve access before filming that segment.
- **Cart mismatch/addition failure:** keep Chrome open, correct products/quantities, and retry. Check whether an item was already added; do not duplicate it. Seller limits must be respected.
- **Share-A-Cart missing:** while the CLI waits, open the [official Chrome extension listing](https://chromewebstore.google.com/detail/share-a-cart-%E2%80%93-easily-sha/hcjohblbkdgcoikaedjndgbcgcfoojmj) in a new tab in the **vendor cart window**. Add the extension, return to the cart, and create its Cart ID. Install once per vendor profile; it persists across runs. The separate incognito Engage window is not the installation target. DigiKey recipients also need the extension to load the shared cart. [DigiKey support](https://share-a-cart.com/supported/digikey)
- **Workbook save fails:** close Excel, let OneDrive finish, then retry in the waiting CLI. Keep the URL; `share_a_cart.json` is the recovery copy. Do not continue without a saved link.
- **Engage lookup/form problem:** both windows stay open. Correct the current page/selection and retry. Open Menu → Budget if needed; manual references accept `B03 Line 1`. Diagnostics are in the printed order folder. Changed payable prices require a refreshed quote.

Cart profiles live under `~/Library/Application Support/mrg-finance/chrome/<vendor>/` on Mac. Screenshot sessions use `.mrg-finance-browser/evidence/` in the working directory. These are separate from ordinary Chrome.

## Optional extras — record only after the main clips

Pick **one** 30-second feature if time allows:

- **Product replacement:** answer `y` at Change product links, choose the item number, paste a replacement URL, then Enter when done. Show the saved Ordering Link/Vendor and new cart. All links in an order must identify one vendor; otherwise replace the remaining links or split the order. Approved Bills costs stay unchanged.
- **Price audit:** run `mrg-finance price-check`, select the bill, and decline opening the add-to-cart link. This is an estimate; failed reads can use allocation fallbacks. Keep its cart additions separate from the verified purchase.
- **DigiKey:** show automatic quote reading and the comparison's GT free-shipping adjustment if the main purchase used Amazon.

A standalone `mrg-finance report --order <ID>` can overwrite that order's verified report filenames. Use another order or record it **before** purchase. Developer installation/tests and offline modes belong in separate videos.

## Editing handoff — do this after recording

Keep the original `.mov` files in `scratch/video/raw`. No overlays need to be added while recording. Use short chapter cards, one callout at a time, and close-up zooms for totals and field names. Cut waits and repeated entries while keeping meaningful choices/results. Do not imply instant approval.

FFmpeg is optional for recording; install it for command-based editing afterward:

```bash
brew install ffmpeg
```

In `scratch/video/edit-notes.txt`, list preferred takes and sensitive timestamps using:

```text
<filename> | <mm:ss–mm:ss> | cut / blur / use this retake
Funding result: prepared draft / submitted draft
Purchase result: prepared form / submitted request
```

Then give the editing agent this instruction:

> Edit `scratch/video/raw` using `docs/user/VIDEO_RUNBOOK.md` and `scratch/video/edit-notes.txt`. Join the six chapters into an 8–10 minute walkthrough including installation and rclone. Keep my narration, cut waits/retakes, add the chapter and field/total overlays, and remove or blur sensitive material. Preserve raw files. Export H.264/AAC at 1920 × 1080 to `scratch/video/exports/mrg-finance-walkthrough.mp4` and include chapter timestamps. Label the actual demonstrated result accurately.

To film a fresh rclone wizard while keeping an existing connection, choose a separate config **before** that take:

```bash
mkdir -p "$HOME/mrg/finance/scratch/video/rclone-demo"
export RCLONE_CONFIG="$HOME/mrg/finance/scratch/video/rclone-demo/rclone.conf"
rclone config
```

The CLI uses this config in the same Terminal session. `unset RCLONE_CONFIG` returns to your normal config. Keep either config private.
