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
    PASSWORD = getpass.getpass("Enter GT password (for CampusLabs + Duo MFA): ")


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


# === Load spreadsheet sheets ===
import warnings
warnings.filterwarnings('ignore')

excel_file = pd.ExcelFile(XLSX_PATH)
df_bills = pd.read_excel(excel_file, sheet_name="Bills").astype(object).fillna("")
df_bills.columns = df_bills.columns.str.strip()

# Build mapping of Bill Item ID -> Bill Row info (as dict for reliable .get())
bill_item_map = {}
for _, row in df_bills.iterrows():
    b_id = str(row.get("Bill Item ID", "")).replace(".0", "").strip()
    if b_id and b_id != "nan":
        bill_item_map[b_id] = row.to_dict()

df_orders = pd.DataFrame()
if "Ordering" in excel_file.sheet_names:
    df_orders = pd.read_excel(excel_file, sheet_name="Ordering", header=1).astype(object).fillna("")
    df_orders.columns = [str(c).strip() for c in df_orders.columns]

# Check for Order ID column name
oid_col = next((c for c in df_orders.columns if isinstance(c, str) and "Order ID" in c), "Order ID") if not df_orders.empty else "Order ID"

# Check for --order flag (passed from mrg.py)
pre_selected_order = None
if "--order" in sys.argv:
    idx = sys.argv.index("--order")
    if idx + 1 < len(sys.argv):
        pre_selected_order = sys.argv[idx + 1]

# === Read from Ordering sheet (OrderT) ===
if df_orders.empty:
    print("No orders found in Ordering sheet.")
    print("Use the web app to create orders first (Orders page → Create Order)")
    exit(0)

requests_to_submit = []
bill_title = ""
bill_no = ""

order_groups = {}
for _, row in df_orders.iterrows():
    order_id = str(row.get(oid_col, "")).strip()
    item_name = str(row.get("Item Name", "")).strip()
    bill_item_id = str(row.get("Bill Item ID", "")).replace(".0", "").strip()

    # Skip header separators or empty rows
    if not order_id or order_id.startswith("Order ") or not (bill_item_id or item_name):
        continue

    if order_id not in order_groups:
        order_groups[order_id] = []
    order_groups[order_id].append(row)

if not order_groups:
    print("No active orders found in Ordering sheet.")
    print("Use the web app to create orders first (Orders page → Create Order)")
    exit(0)

order_ids = list(order_groups.keys())
print("\nAvailable Orders:")
for i, oid in enumerate(order_ids, 1):
    items_in_o = order_groups[oid]
    v_name = items_in_o[0].get("Vendor", "Unknown") if items_in_o else "Unknown"
    print(f"  {i}. {oid} ({v_name}, {len(items_in_o)} items)")

if pre_selected_order:
    selected_order_id = pre_selected_order
    print(f"\nUsing order: {selected_order_id}")
else:
    choice = input("\nSelect order (number or Order ID): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(order_ids):
        selected_order_id = order_ids[int(choice) - 1]
    else:
        selected_order_id = choice

order_rows = order_groups.get(selected_order_id, [])
if not order_rows:
    print(f"No order found for '{selected_order_id}'")
    exit(0)

bill_title = selected_order_id

for i, row in enumerate(order_rows):
    b_id = str(row.get("Bill Item ID", "")).replace(".0", "").strip()
    b_row = bill_item_map.get(b_id, None)
    has_bill_row = b_row is not None

    item_name = str(row.get("Item Name", "") or (b_row.get("Item Name", "") if has_bill_row else "")).strip()
    description = str(row.get("Description", "") or (b_row.get("Description", "") if has_bill_row else "")).strip()
    link = str(row.get("Link", "") or (b_row.get("Link", "") if has_bill_row else "")).strip()

    cost = safe_float(b_row.get("Cost", 0) if has_bill_row else row.get("Allocation", 0))
    qty = safe_int(row.get("Quantity", 1))
    total = cost * qty

    if has_bill_row and not bill_no:
        bill_no = str(b_row.get("Bill No.", "")).replace(".0", "").strip()

    bill_line_ref = f"Bill {bill_no or '?'}, Line {b_id or i+1}"

    requests_to_submit.append({
        "item_name": item_name,
        "description": description,
        "cost": cost,
        "quantity": qty,
        "total": total,
        "bill_line_ref": bill_line_ref,
        "bill_item_id": b_id,
        "link": link,
    })

# === Build purchase request list ===
# === Display summary ===
print(f"\n{'='*60}")
print(f"📋 Purchase Request for: {bill_title} (Bill #{bill_no})")
print(f"{'='*60}")
print(f"\n{'#':<4} {'Line':<6} {'Item Name':<35} {'Qty':<5} {'Cost':<10} {'Total'}")
print("-" * 75)

for i, r in enumerate(requests_to_submit):
    print(f"{i+1:<4} {r['bill_item_id']:<6} {r['item_name']:<35} {r['quantity']:<5} ${r['cost']:<9.2f} ${r['total']:.2f}")

grand_total = sum(r["total"] for r in requests_to_submit)
print(f"\n  💰 Grand Total Allocation: ${grand_total:.2f}")

# === Live Price Check Audit (Interactive Option) ===
has_scraped_data = False
total_scraped_live = 0.0
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

non_amazon_count = sum(1 for r in requests_to_submit if "amazon" not in r.get("link", "").lower())
if non_amazon_count > 0:
    print(f"\nℹ️ Non-Amazon Vendor Items Detected ({non_amazon_count} item(s)):")
    print("   Please create a shopping cart directly on the vendor website and take a cart screenshot before submitting your purchase request.")


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

confirm = input(f"\nSubmit purchase request to Engage? ({len(requests_to_submit)} items, ${grand_total:.2f}) [Y/n]: ").strip().lower()
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
try:
    WebDriverWait(driver, 180).until(EC.url_contains("gatech.campuslabs.com/engage"))
except TimeoutException:
    print("  ⏳ Duo MFA wait timed out automatically.")
    input("  Press Enter after completing Duo MFA in your browser window → ")
print("✅ Logged in\n")

# === Submit Purchase Requests ===
results = {"success": [], "failed": []}

# Build a single purchase request with all items
order_subject = f"Order: {bill_title}"
order_description = "\n".join(
    f"- {r['item_name']} (x{r['quantity']}) — ${r['total']:.2f} [{r['bill_line_ref']}]"
    for r in requests_to_submit
)
order_amount = grand_total
order_bill_refs = ", ".join(set(r['bill_line_ref'] for r in requests_to_submit))

print(f"\n{'='*50}")
print(f"Submitting 1 purchase request with {len(requests_to_submit)} line items")
print(f"  Subject: {order_subject}")
print(f"  Amount: ${order_amount:.2f}")
print(f"  Bill refs: {order_bill_refs}")
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
    subject.send_keys(order_subject)

    # Fill Description (all items listed)
    try:
        desc_field = driver.find_element(By.ID, "Description")
        desc_field.clear()
        desc_field.send_keys(order_description)
    except Exception:
        pass

    # Fill Requested Amount (grand total)
    try:
        amount_field = driver.find_element(By.ID, "Amount")
        amount_field.clear()
        amount_field.send_keys(f"{order_amount:.2f}")
    except Exception:
        try:
            amount_field = driver.find_element(By.CSS_SELECTOR, '[ng-model*="amount"], [ng-model*="Amount"]')
            amount_field.clear()
            amount_field.send_keys(f"{order_amount:.2f}")
        except Exception:
            print("  ⚠️ Could not find Amount field")

    # Fill Bill # and Line # field
    try:
        bill_line_fields = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], textarea')
        for field in bill_line_fields:
            placeholder = (field.get_attribute("placeholder") or "").lower()
            if "bill" in placeholder or "budget" in placeholder:
                field.clear()
                field.send_keys(order_bill_refs)
                print(f"  ✅ Filled Bill/Line ref: {order_bill_refs}")
                break
        else:
            labels = driver.find_elements(By.XPATH, "//*[contains(text(), 'Budget/Bill')]")
            if labels:
                parent = labels[0].find_element(By.XPATH, "./ancestor::div[contains(@class,'form-group')]")
                inp = parent.find_element(By.CSS_SELECTOR, "input, textarea")
                inp.clear()
                inp.send_keys(order_bill_refs)
                print(f"  ✅ Filled Bill/Line ref: {order_bill_refs}")
    except Exception as e:
        print(f"  ⚠️ Could not fill Bill/Line field: {e}")

    # Upload cart screenshot if available
    safe_bill = "".join(c if c.isalnum() or c in " -_" else "_" for c in bill_title)
    cart_screenshot = os.path.join(os.path.dirname(__file__), "web-app", "screenshots", safe_bill, "cart.png")
    if not os.path.exists(cart_screenshot):
        cart_screenshot = os.path.join(DOWNLOAD_DIR, "cart.png")

    if os.path.exists(cart_screenshot):
        try:
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if file_inputs:
                driver.execute_script("arguments[0].style.display='block';", file_inputs[0])
                file_inputs[0].send_keys(os.path.abspath(cart_screenshot))
                print(f"  📎 Uploaded cart screenshot: {os.path.basename(cart_screenshot)}")
                time.sleep(2)
        except Exception as e:
            print(f"  ⚠️ Upload failed: {e}")
    else:
        print(f"  ℹ️ No cart screenshot found. Take one of your Amazon cart before submitting.")

    # PAUSE — let user review and submit manually
    print(f"\n  ⏸️  Form pre-filled with {len(requests_to_submit)} items totaling ${order_amount:.2f}")
    print(f"     Review and fill remaining fields (Category, Account, etc.)")
    print(f"     Bill #{bill_no}")
    input(f"     Press Enter after you submit this purchase request → ")
    print(f"  ✅ Purchase request submitted")

except Exception as e:
    print(f"  ❌ Error: {e}")

# === Overflow Request (if price check found overrun) ===
if has_scraped_data and total_scraped_live > grand_total + 0.01:
    overflow_amount = total_scraped_live - grand_total
    print(f"\n{'='*50}")
    print(f"⚠️ Cost overflow detected: +${overflow_amount:.2f}")
    print(f"  Allocated: ${grand_total:.2f}")
    print(f"  Live cost: ${total_scraped_live:.2f}")
    create_overflow = input(f"\nCreate a separate overflow purchase request for ${overflow_amount:.2f}? [Y/n]: ").strip().lower()

    if create_overflow in ("", "y", "yes"):
        try:
            driver.get(PURCHASE_URL)
            time.sleep(3)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "Subject")))

            subject = driver.find_element(By.ID, "Subject")
            subject.clear()
            subject.send_keys(f"Overflow: {bill_title}")

            try:
                desc_field = driver.find_element(By.ID, "Description")
                desc_field.clear()
                desc_field.send_keys(f"Price increase overflow for order {bill_title}. Original allocation: ${grand_total:.2f}, Current cost: ${total_scraped_live:.2f}")
            except Exception:
                pass

            try:
                amount_field = driver.find_element(By.ID, "Amount")
                amount_field.clear()
                amount_field.send_keys(f"{overflow_amount:.2f}")
            except Exception:
                pass

            print(f"\n  ⏸️  Overflow request pre-filled: ${overflow_amount:.2f}")
            input(f"     Press Enter after you submit the overflow request → ")
            print(f"  ✅ Overflow request submitted")
        except Exception as e:
            print(f"  ❌ Overflow request error: {e}")

# === Final Report ===
print(f"\n{'='*60}")
print(f"🎉 COMPLETED — Purchase Request for {bill_title}")
print(f"{'='*60}")
print(f"  Order: {bill_title}")
print(f"  Items: {len(requests_to_submit)}")
print(f"  Total: ${grand_total:.2f}")
print()
