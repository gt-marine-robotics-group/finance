import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select
import getpass

# === CONFIG ===
XLSX_PATH = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
SHEET_NAME = "Bills"
DOWNLOAD_DIR = "downloads"
PURCHASE_URL = "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest"
USERNAME = "awu335"
PASSWORD = ""

# --- Fresh sync from SharePoint ---
import sys
if "--fresh" in sys.argv or "-f" in sys.argv:
    print("Downloading fresh xlsx from SharePoint...")
    import subprocess
    result = subprocess.run(
        ["rclone", "copy", "--checksum",
         "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
         os.path.dirname(XLSX_PATH)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("✅ Fresh copy downloaded")
    else:
        print(f"⚠️ rclone failed: {result.stderr.strip()}")
        print("Continuing with local copy...")

# Prompt
if not PASSWORD:
    PASSWORD = getpass.getpass("Enter your password: ")


def safe_float(val, default=0.0):
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


# === Load spreadsheet ===
import warnings
warnings.filterwarnings('ignore')

df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME)
df.fillna("", inplace=True)
df.columns = df.columns.str.strip()

# Filter to actual bill items
SKIP_TITLES = ("nan", "request", "liquid", "misc")
df_valid = df[
    (df["Bill Title"].astype(str).str.strip() != "") &
    (df["Item Name"].astype(str).str.strip() != "")
].copy()
df_valid = df_valid[~df_valid["Bill Title"].astype(str).str.strip().str.lower().apply(
    lambda t: any(t.startswith(s) for s in SKIP_TITLES)
)]

# Show available bills
titles = df_valid["Bill Title"].astype(str).str.strip().unique()
print("\nAvailable Bills:")
for i, t in enumerate(titles, 1):
    bill_nos = df_valid[df_valid["Bill Title"].astype(str).str.strip() == t]["Bill No."].unique()
    bill_no_str = str(bill_nos[0]).replace(".0", "") if len(bill_nos) > 0 and str(bill_nos[0]) else "?"
    count = (df_valid["Bill Title"].astype(str).str.strip() == t).sum()
    print(f"  {i}. {t} (Bill #{bill_no_str}, {count} items)")

choice = input("\nSelect bill (number or name): ").strip()
if choice.isdigit() and 1 <= int(choice) <= len(titles):
    bill_title = titles[int(choice) - 1]
else:
    bill_title = choice

# Filter items for this bill
mask = df_valid["Bill Title"].astype(str).str.strip().str.lower() == bill_title.lower()
bill_items = df_valid[mask].copy()

if bill_items.empty:
    print(f"No items found for '{bill_title}'")
    exit(0)

# Get bill number
bill_no = str(bill_items["Bill No."].iloc[0]).replace(".0", "").strip()

# === Build purchase request list ===
import webbrowser
review_url = f"http://localhost:5000/bill/{bill_title}"
print(f"🌐 Launching Review Window in browser: {review_url}")
try:
    webbrowser.open(review_url)
except Exception:
    pass

print(f"\n{'='*60}")
print(f"📋 Purchase Requests for: {bill_title} (Bill #{bill_no})")
print(f"{'='*60}")
print(f"\n{'#':<4} {'Line':<6} {'Item Name':<35} {'Qty':<5} {'Cost':<10} {'Total'}")
print("-" * 75)

requests_to_submit = []
for i, (_, row) in enumerate(bill_items.iterrows()):
    item_name = str(row.get("Item Name", "")).strip()
    bill_item_id = str(row.get("Bill Item ID", i+1)).replace(".0", "").strip()
    cost = safe_float(row.get("Cost", 0))
    qty = safe_int(row.get("Quantity", 1))
    total = cost * qty
    description = str(row.get("Description", "")).strip()

    bill_line_ref = f"Bill {bill_no}, Line {bill_item_id}"

    requests_to_submit.append({
        "item_name": item_name,
        "description": description,
        "cost": cost,
        "quantity": qty,
        "total": total,
        "bill_line_ref": bill_line_ref,
        "bill_item_id": bill_item_id,
        "link": str(row.get("Link", "")).strip(),
    })

    print(f"{i+1:<4} {bill_item_id:<6} {item_name:<35} {qty:<5} ${cost:<9.2f} ${total:.2f}")

grand_total = sum(r["total"] for r in requests_to_submit)
print(f"\n  💰 Grand Total Allocation: ${grand_total:.2f}")

# === Live Price Check Audit (Interactive Option) ===
run_check = input("\nRun live price check audit against online product links? (Y/n): ").strip().lower()
if run_check in ("", "y", "yes"):
    import price_scraper
    print(f"\n🔍 Running Live Price Check Audit against online product links...")
    total_scraped_live = 0.0
    has_scraped_data = False
    has_overrun = False

    print(f"\n{'Item Name':<35} {'Allocated':<12} {'Live Price':<12} {'Status'}")
    print("-" * 75)

    for r in requests_to_submit:
        url = r.get("link", "")
        alloc_unit = r["cost"]
        live_unit = None

        if url and url.startswith("http"):
            try:
                scraped = price_scraper.scrape_item_price(url)
                if scraped and scraped.get("current_price") is not None:
                    live_unit = float(scraped["current_price"])
                    has_scraped_data = True
            except Exception:
                pass

        unit_delta = (live_unit - alloc_unit) if live_unit is not None else 0.0

        if live_unit is not None:
            total_scraped_live += (live_unit * r["quantity"])
            if unit_delta > 0.01:
                has_overrun = True
                status_str = f"+${unit_delta:.2f} (OVER BUDGET)"
            elif unit_delta < -0.01:
                status_str = f"-${-unit_delta:.2f} (SAVINGS)"
            else:
                status_str = "✅ Match"
            print(f"{r['item_name']:<35} ${alloc_unit:<11.2f} ${live_unit:<11.2f} {status_str}")
        else:
            total_scraped_live += r["total"]
            print(f"{r['item_name']:<35} ${alloc_unit:<11.2f} {'—':<11} ℹ️ Scrape unavailable")

    print("-" * 75)
    if has_scraped_data:
        total_delta = total_scraped_live - grand_total
        if total_delta > 0.01:
            print(f"⚠️ OVERRUN WARNING: Total live cost is +${total_delta:.2f} higher than approved allocation!")
        elif total_delta < -0.01:
            print(f"🎉 SAVINGS NOTICE: Total live cost is -${-total_delta:.2f} lower than approved allocation!")
        else:
            print("✅ Live prices match approved bill allocations 100%.")
else:
    print("  ⏩ Skipped live price check audit.")

print(f"  📝 Each item will be a separate purchase request")
print(f"  📝 Bill/Line reference auto-generated (e.g. '{requests_to_submit[0]['bill_line_ref']}')")

# Ask about shipping/tax overflow
print(f"\n  Do any items have shipping/tax overflow?")
add_overflow = input("  Add overflow requests? [y/N]: ").strip().lower()
if add_overflow == "y":
    while True:
        overflow_line = input("    Line # for overflow (or Enter to stop): ").strip()
        if not overflow_line:
            break
        overflow_amount = input("    Overflow amount (shipping/tax): $").strip()
        overflow_desc = input("    Description (e.g. 'shipping', 'tax'): ").strip()
        try:
            amt = float(overflow_amount)
            ref_item = next((r for r in requests_to_submit if r["bill_item_id"] == overflow_line), None)
            item_name = ref_item["item_name"] if ref_item else f"Line {overflow_line}"
            requests_to_submit.append({
                "item_name": f"{item_name} - {overflow_desc}",
                "description": f"{overflow_desc} for {item_name}",
                "cost": amt,
                "quantity": 1,
                "total": amt,
                "bill_line_ref": f"Bill {bill_no}, Line {overflow_line}",
                "bill_item_id": overflow_line,
                "is_overflow": True,
            })
            print(f"    ✅ Added: ${amt:.2f} {overflow_desc} for Line {overflow_line}")
        except ValueError:
            print(f"    ⚠️ Invalid amount")

confirm = input(f"\nSubmit {len(requests_to_submit)} purchase request(s)? [Y/n]: ").strip().lower()
if confirm == "n":
    print("Cancelled.")
    exit(0)

# === Selenium Setup ===
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)
driver = webdriver.Chrome(options=options)
driver.get("https://gatech.campuslabs.com/engage/")

# Login
discovery_bar = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "discovery-bar"))
)
parent_root = discovery_bar.find_element(By.ID, "parent-root")
shadow_root = driver.execute_script("return arguments[0].shadowRoot", parent_root)
sign_in_button = shadow_root.find_element(By.CSS_SELECTOR, "a[href*='/engage/account/login']")
sign_in_button.click()

username_input = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "username"))
)
username_input.send_keys(USERNAME)
password_input = driver.find_element(By.ID, "password")
password_input.send_keys(PASSWORD)
login_button = driver.find_element(By.NAME, "submitbutton")
login_button.click()
print("\nComplete Duo MFA if prompted...")
WebDriverWait(driver, 60).until(EC.url_contains("gatech.campuslabs.com/engage"))
print("✅ Logged in\n")

# === Submit Purchase Requests ===
results = {"success": [], "failed": []}

for i, req in enumerate(requests_to_submit):
    print(f"\n{'='*50}")
    print(f"[{i+1}/{len(requests_to_submit)}] {req['item_name']}")
    print(f"  Amount: ${req['total']:.2f} | Ref: {req['bill_line_ref']}")
    print(f"{'='*50}")

    try:
        # Navigate to create purchase request page
        driver.get(PURCHASE_URL)
        time.sleep(3)

        # Wait for form to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "Subject"))
        )

        # Fill Subject
        subject = driver.find_element(By.ID, "Subject")
        subject.clear()
        subject.send_keys(req["item_name"])

        # Fill Description
        try:
            desc_field = driver.find_element(By.ID, "Description")
            desc_field.clear()
            desc_field.send_keys(req["description"] or req["item_name"])
        except Exception:
            pass

        # Fill Requested Amount
        try:
            amount_field = driver.find_element(By.ID, "Amount")
            amount_field.clear()
            amount_field.send_keys(f"{req['total']:.2f}")
        except Exception:
            try:
                amount_field = driver.find_element(By.CSS_SELECTOR, '[ng-model*="amount"], [ng-model*="Amount"]')
                amount_field.clear()
                amount_field.send_keys(f"{req['total']:.2f}")
            except Exception:
                print("  ⚠️ Could not find Amount field")

        # Fill Bill # and Line # field
        try:
            # Look for the write-in answer field about Budget/Bill #
            bill_line_fields = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], textarea')
            for field in bill_line_fields:
                placeholder = (field.get_attribute("placeholder") or "").lower()
                label_for = field.get_attribute("id") or ""
                # Find the field asking about Bill # and Line #
                if "bill" in placeholder or "budget" in placeholder:
                    field.clear()
                    field.send_keys(req["bill_line_ref"])
                    print(f"  ✅ Filled Bill/Line ref: {req['bill_line_ref']}")
                    break
            else:
                # Try by looking for nearby label text
                labels = driver.find_elements(By.XPATH, "//*[contains(text(), 'Budget/Bill')]")
                if labels:
                    # Find the next input after that label
                    parent = labels[0].find_element(By.XPATH, "./ancestor::div[contains(@class,'form-group')]")
                    inp = parent.find_element(By.CSS_SELECTOR, "input, textarea")
                    inp.clear()
                    inp.send_keys(req["bill_line_ref"])
                    print(f"  ✅ Filled Bill/Line ref: {req['bill_line_ref']}")
        except Exception as e:
            print(f"  ⚠️ Could not fill Bill/Line field: {e}")

        # Upload receipt/screenshot if available
        local_path = None
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in req['item_name'])
        safe_bill = "".join(c if c.isalnum() or c in " -_" else "_" for c in bill_title)

        candidates = [
            os.path.join(os.path.dirname(__file__), "web-app", "screenshots", safe_bill, f"{safe_name}.png"),
            os.path.join(os.path.dirname(__file__), "web-app", "screenshots", "_queue", f"{safe_name}.png"),
            os.path.join(DOWNLOAD_DIR, f"{req['item_name']}.png"),
        ]
        for ext in ["", ".png", ".jpg", ".jpeg", ".pdf"]:
            for candidate in candidates:
                test_path = candidate + ext if not candidate.endswith(ext) else candidate
                if os.path.exists(test_path):
                    local_path = test_path
                    break
            if local_path:
                break

        if local_path:
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                if file_inputs:
                    driver.execute_script("arguments[0].style.display='block';", file_inputs[0])
                    file_inputs[0].send_keys(os.path.abspath(local_path))
                    print(f"  📎 Uploaded ground-truth screenshot: {os.path.basename(local_path)}")
                    time.sleep(2)
            except Exception as e:
                print(f"  ⚠️ Upload failed: {e}")
        else:
            print(f"  ⚠️ No ground-truth screenshot found for '{req['item_name']}' (run bill-request or web app screenshot first)")

        # PAUSE — let user review and submit manually
        print(f"\n  ⏸️  Form pre-filled. Review and fill remaining fields (Category, Account).")
        print(f"     Fill in the SGA Bill section: Bill #{bill_no}, ${req['total']:.2f}")
        input(f"     Press Enter after you submit this request → ")

        results["success"].append(req["item_name"])
        print(f"  ✅ Done")

    except Exception as e:
        print(f"  ❌ Error: {e}")
        results["failed"].append(req["item_name"])
        input("  Press Enter to continue to next item → ")

# === Final Report ===
print(f"\n{'='*60}")
print(f"🎉 COMPLETED — Purchase Requests for Bill #{bill_no}")
print(f"{'='*60}")
print(f"  ✅ Submitted: {len(results['success'])}")
print(f"  ❌ Failed: {len(results['failed'])}")
if results["failed"]:
    print(f"\n  Failed items:")
    for name in results["failed"]:
        print(f"    - {name}")
print()
