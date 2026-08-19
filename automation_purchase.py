import os
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import time
from datetime import date
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
try:
    from engage_bill_lookup import build_bill_url, lookup_bill_item_locations
except ModuleNotFoundError:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from engage_bill_lookup import build_bill_url, lookup_bill_item_locations
import getpass

# === CONFIG ===
XLSX_PATH = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
SHEET_NAME = "Bills"
DOWNLOAD_DIR = "downloads"
PURCHASE_URL = "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest"
USERNAME = os.environ.get("ENGAGE_USERNAME", "")
PASSWORD = ""

# --- Fresh sync from SharePoint ---
import sys
if "--fresh" in sys.argv or "-f" in sys.argv:
    print("Downloading fresh xlsx from SharePoint...")
    import subprocess
    result = subprocess.run(
        ["rclone", "copy", "--ignore-checksum", "--ignore-size", "--update",
         "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
         os.path.dirname(XLSX_PATH)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("✅ Fresh copy downloaded")
    else:
        print(f"⚠️ rclone failed: {result.stderr.strip()}")
        print("Continuing with local copy...")

# Prompt for credentials if empty
if not USERNAME:
    USERNAME = input("Enter GT username: ").strip()
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
import spreadsheet_utils

excel_file = pd.ExcelFile(XLSX_PATH)
df_bills = spreadsheet_utils.read_sheet_robust(excel_file, ["Bills", "Bill", "Budget"])

# Build mapping of Bill Item ID -> Bill Row info
bill_item_map = {}
if not df_bills.empty:
    for _, row in df_bills.iterrows():
        r_dict = row.to_dict()
        b_id = spreadsheet_utils.get_col_val(r_dict, "bill_item_id")
        if b_id:
            bill_item_map[b_id] = r_dict

df_orders = spreadsheet_utils.read_sheet_robust(excel_file, ["Ordering", "Orders", "OrderT"])

# Check for Order ID column name
oid_col = "Order ID"
if not df_orders.empty:
    for c in df_orders.columns:
        if "order" in str(c).lower():
            oid_col = c
            break

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
vendor_name = ""
for row in order_rows:
    v = str(row.get("Vendor", "") or "").strip()
    if v:
        vendor_name = v
        break
vendor_name = vendor_name or "Vendor"

purchase_date = date.today().strftime("%Y-%m-%d")

for i, row in enumerate(order_rows):
    b_id = str(row.get("Bill Item ID", "")).replace(".0", "").strip()
    b_row = bill_item_map.get(b_id, None)
    has_bill_row = b_row is not None

    item_bill_no = ""
    if has_bill_row:
        item_bill_no = str(b_row.get("Bill No.", "")).replace(".0", "").strip()
    if not item_bill_no or item_bill_no == "nan":
        item_bill_no = str(row.get("Bill No.", "")).replace(".0", "").strip()
    if not item_bill_no or item_bill_no == "nan":
        item_bill_no = bill_no

    if item_bill_no and not bill_no:
        bill_no = item_bill_no

    item_name = str(row.get("Item Name", "") or (b_row.get("Item Name", "") if has_bill_row else "")).strip()
    description = str(row.get("Description", "") or (b_row.get("Description", "") if has_bill_row else "")).strip()
    link = str(row.get("Link", "") or (b_row.get("Link", "") if has_bill_row else "")).strip()
    source_bill_title = str(b_row.get("Bill Title", "") if has_bill_row else "").strip() or str(row.get("Bill Title", "") or "").strip()

    cost = safe_float(b_row.get("Cost", 0) if has_bill_row else row.get("Allocation", 0))
    qty = safe_int(row.get("Quantity", 1))
    total = cost * qty

    bill_line_ref = f"Bill {item_bill_no or '?'}, Line {b_id or i+1}"

    requests_to_submit.append({
        "item_name": item_name,
        "description": description,
        "cost": cost,
        "quantity": qty,
        "total": total,
        "bill_no": item_bill_no,
        "bill_line_ref": bill_line_ref,
        "engage_line_ref": None,
        "bill_item_id": b_id,
        "source_bill_title": source_bill_title,
        "link": link,
    })

# === Build purchase request list ===
# === Display summary ===
print(f"\n{'='*60}")
print(f"📋 Purchase Request for: {bill_title} (Bill #{bill_no})")
print(f"{'='*60}")
print(f"\n{'Engage Line':<12} {'Item Name':<38} {'Qty':<5} {'Cost':<10} {'Total'}")
print("-" * 75)

for i, r in enumerate(requests_to_submit):
    engage_line = r.get("engage_line_ref") or f"Line {i+1}"
    print(f"{engage_line:<12} {r['item_name']:<38} {r['quantity']:<5} ${r['cost']:<9.2f} ${r['total']:.2f}")

grand_total = sum(r["total"] for r in requests_to_submit)
print(f"\n  💰 Grand Total Allocation: ${grand_total:.2f}")

# === Live Price Check Audit (Interactive Option) ===
print(f"\nℹ️  Purchase Audit Notice: Approved bill screenshots are fixed on Engage and cannot be modified.")
print(f"   Live price check verifies whether online prices have changed since bill approval.")

has_scraped_data = False
total_scraped_live = 0.0
scraped_results = {}

run_check = input("\n🔍 Check live online prices against approved budget allocations? (Y/n): ").strip().lower()
if run_check in ("", "y", "yes"):
    import price_scraper
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    print(f"\n🔍 Checking live online prices and capturing current product screenshots...")
    total_scraped_live = 0.0
    has_scraped_data = False
    has_overrun = False

    c_opts = Options()
    c_opts.add_argument("--headless=new")
    c_opts.add_argument("--window-size=1920,1080")
    c_opts.add_argument("--no-sandbox")
    c_opts.add_argument("--disable-dev-shm-usage")

    try:
        c_driver = webdriver.Chrome(service=Service(), options=c_opts)
        c_driver.set_page_load_timeout(20)
    except Exception:
        c_driver = None

    order_shot_dir = os.path.join("screenshots", selected_order_id)
    os.makedirs(order_shot_dir, exist_ok=True)

    print(f"\n{'Item Name':<35} {'Allocated':<12} {'Live Price':<12} {'Status'}")
    print("-" * 75)

    for r in requests_to_submit:
        url = r.get("link", "")
        item_name = r["item_name"]
        alloc_unit = r["cost"]
        live_unit = None

        if url and url.startswith("http"):
            try:
                scraped = price_scraper.scrape_item_price(url)
                if scraped and scraped.get("current_price") is not None:
                    live_unit = float(scraped["current_price"])
                    has_scraped_data = True
                    scraped_results[item_name] = live_unit
            except Exception:
                pass

            if c_driver:
                try:
                    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in item_name)
                    shot_path = os.path.join(order_shot_dir, f"{safe_name}.png")
                    c_driver.get(url)
                    time.sleep(2)
                    price_scraper.dismiss_popups_and_interstitials(c_driver)
                    c_driver.save_screenshot(shot_path)
                    print(f"  📸 Saved screenshot for '{item_name}' -> {shot_path}")

                    # Automatically add Amazon items to shopping cart
                    if "amazon" in url.lower():
                        try:
                            # Adjust quantity if > 1
                            if r.get("quantity", 1) > 1:
                                try:
                                    qty_select = c_driver.find_elements(By.ID, "quantity")
                                    if qty_select:
                                        Select(qty_select[0]).select_by_value(str(r["quantity"]))
                                        time.sleep(0.5)
                                except Exception:
                                    pass

                            add_btns = c_driver.find_elements(
                                By.XPATH,
                                "//input[@id='add-to-cart-button' or @name='submit.add-to-cart'] | "
                                "//button[contains(text(), 'Add to Cart')] | "
                                "//input[@value='Add to Cart']"
                            )
                            if add_btns:
                                c_driver.execute_script("arguments[0].click();", add_btns[0])
                                time.sleep(1)
                                print(f"  🛒 Added '{item_name}' (x{r['quantity']}) to Amazon cart")
                        except Exception:
                            pass
                except Exception as exc:
                    print(f"  ⚠️ Failed to capture screenshot for '{item_name}' ({url}): {exc}")

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

    # Navigate to Amazon Cart View and capture cart.png
    if c_driver:
        has_amazon = any("amazon" in r.get("link", "").lower() for r in requests_to_submit)
        if has_amazon:
            try:
                print("\n🛒 Navigating to Amazon Cart View & capturing cart.png screenshot...")
                c_driver.get("https://www.amazon.com/gp/cart/view.html")
                time.sleep(3)
                cart_shot_path = os.path.join(order_shot_dir, "cart.png")
                c_driver.save_screenshot(cart_shot_path)
                print(f"  📸 Saved Amazon cart screenshot -> {cart_shot_path}")
            except Exception as e:
                print(f"  ⚠️ Could not capture cart screenshot: {e}")

        c_driver.quit()

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
    print("  ⏩ Skipped live price check.")

# === Launch Side-by-Side Order Review GUI ===
try:
    from automation_screenshots import generate_review_html, parse_price, REVIEW_HTML, resolve_review_screenshot_paths, calculate_review_status
    from review_server import launch_review_server_and_browser
    review_data = []
    for item in requests_to_submit:
        item_name = str(item.get("item_name", "")).strip()
        url = str(item.get("link", "")).strip()
        cost = str(item.get("cost", "")).strip()
        source_bill_title = str(item.get("source_bill_title", "") or bill_title).strip()
        old_shot, new_shot = resolve_review_screenshot_paths(item_name, source_bill_title=source_bill_title, order_id=selected_order_id)
        live_price_val = scraped_results.get(item_name)
        if live_price_val is None and url and url.startswith("http"):
            try:
                import price_scraper
                scraped = price_scraper.scrape_item_price(url)
                if scraped and scraped.get("current_price") is not None:
                    live_price_val = float(scraped["current_price"])
                    scraped_results[item_name] = live_price_val
            except Exception:
                pass

        parsed = live_price_val if live_price_val is not None else parse_price(cost)
        scraped_str = f"${parsed:.2f}" if parsed is not None else f"${safe_float(cost):.2f}"
        review_status = calculate_review_status(cost, parsed, screenshot_file=os.path.basename(new_shot) if new_shot else None)
        review_data.append({
            "item_name": item_name, "url": url, "csv_cost": cost,
            "scraped_price": scraped_str, "parsed_price": parsed,
            "confidence": "high", "screenshot": os.path.basename(new_shot) if new_shot else None,
            "old_screenshot": old_shot, "new_screenshot": new_shot,
            "status": review_status,
        })
    generate_review_html(review_data, f"Order: {selected_order_id}", REVIEW_HTML)
    launch_review_server_and_browser(REVIEW_HTML)
    input("\n   Press Enter after reviewing & saving prices on the review page → ")
except Exception as ex:
    print(f"  ⚠️ Review GUI notice: {ex}")

non_amazon_count = sum(1 for r in requests_to_submit if "amazon" not in str(r.get("link", "")).lower())
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
print("\n🌐 Launching Chrome browser...")
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)
driver = webdriver.Chrome(options=options)

print("🌐 Navigating to Georgia Tech Engage portal...")
driver.get("https://gatech.campuslabs.com/engage/")

# Login
WebDriverWait(driver, 20).until(
    lambda d: d.execute_script("return !!document.getElementById('discovery-bar')")
)

sign_in_button = None
try:
    discovery_bar = driver.find_element(By.ID, "discovery-bar")
    parent_root = discovery_bar.find_element(By.ID, "parent-root")
    shadow_root = driver.execute_script("return arguments[0].shadowRoot", parent_root)
    sign_in_candidates = shadow_root.find_elements(By.CSS_SELECTOR, "a[href*='/engage/account/login'], a[href*='account/login'], button, [role='button']")
    for candidate in sign_in_candidates:
        href = (candidate.get_attribute("href") or "").lower()
        text = (candidate.text or "").lower()
        if "account/login" in href or "sign in" in text or "log in" in text:
            sign_in_button = candidate
            break
except Exception:
    sign_in_button = None

if sign_in_button is None:
    try:
        sign_in_button = driver.find_element(By.CSS_SELECTOR, "a[href*='/engage/account/login']")
    except Exception:
        sign_in_button = driver.find_element(By.XPATH, "//a[contains(@href, '/engage/account/login') or contains(normalize-space(.), 'Sign In') or contains(normalize-space(.), 'Log In')][1]")

if sign_in_button is None:
    raise RuntimeError("Could not locate the Engage sign-in link")

print("🔑 Clicking Sign In link...")
try:
    sign_in_button.click()
except Exception:
    driver.execute_script("arguments[0].click();", sign_in_button)

print(f"🔑 Submitting credentials for GT user: {USERNAME}...")
username_input = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "username"))
)
username_input.send_keys(USERNAME)
password_input = driver.find_element(By.ID, "password")
password_input.send_keys(PASSWORD)
login_button = driver.find_element(By.NAME, "submitbutton")
login_button.click()
print("📲 Complete Duo MFA on your device if prompted...")
try:
    WebDriverWait(driver, 180).until(EC.url_contains("gatech.campuslabs.com/engage"))
except TimeoutException:
    print("  ⏳ Duo MFA wait timed out automatically.")
    input("  Press Enter after completing Duo MFA in your browser window → ")
print("✅ Duo MFA Login verified!")

# Navigate to the budget requests area and click the Budget tab so the item bill edit pages
# are actually available in the DOM before we look up section/line numbers.
print("\n🌐 Navigating to Engage budgeting requests area...")
driver.get("https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests")
try:
    budget_tab = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@analytics-event, 'Tab Budget')]"))
    )
    budget_tab.click()
    time.sleep(3)
except Exception:
    pass

bill_line_cache = {}
# Group items by bill number so we visit each bill page only once.
bills_to_lookup = {}
for r in requests_to_submit:
    bill_number = str(r.get("bill_no") or bill_no or "").strip()
    if bill_number:
        bills_to_lookup.setdefault(bill_number, []).append(r["item_name"])

print(f"🔍 Starting live bill line location lookup for {len(bills_to_lookup)} bill(s)...")
for bill_number, item_names in bills_to_lookup.items():
    lookup = lookup_bill_item_locations(driver, bill_number, item_names)
    if lookup:
        bill_line_cache[bill_number] = lookup
    else:
        print(f"  ⚠️ Could not resolve live Engage bill sections/line numbers from bill {bill_number}; using spreadsheet reference fallback.")

print("\n📋 Resolved Engage Line References:")
for r in requests_to_submit:
    bill_no_for_item = str(r.get("bill_no") or bill_no or "").strip()
    b_id = str(r.get("bill_item_id") or "").strip()
    location = (bill_line_cache.get(bill_no_for_item) or {}).get(r["item_name"])
    if location:
        section_name = str(location.get("section") or "").strip()
        # Prioritize line position within section (section_line_number) over global bill count
        line_id = location.get("section_line_number") or location.get("line_number") or b_id or str(requests_to_submit.index(r) + 1)
        if section_name and section_name != "Unknown Section":
            r["engage_line_ref"] = f"Bill {bill_no_for_item}, {section_name}, Line {line_id}"
        else:
            r["engage_line_ref"] = f"Bill {bill_no_for_item}, Line {line_id}"
        r["bill_line_ref"] = r["engage_line_ref"]
        print(f"  ✓ '{r['item_name']}' -> {r['engage_line_ref']}")
    else:
        # Keep original spreadsheet-derived bill_line_ref as fallback
        r["engage_line_ref"] = None
        fallback_ref = f"Bill {bill_no_for_item}, Line {b_id}" if b_id else f"Bill {bill_no_for_item}"
        print(f"  ⚠️ '{r['item_name']}' -> Not matched on Engage (Fallback: {fallback_ref})")

# === Submit Purchase Requests ===
results = {"success": [], "failed": []}

# Subject line format: Marine Robotics Group "Vendor" Purchase Request YYYY-MM-DD
order_subject = f"Marine Robotics Group {vendor_name} Purchase Request {purchase_date}"

# Description field is left completely blank
order_description = ""
order_amount = grand_total

# SGA Bill Box text: Each item with Price, Line Number, Bill Number, Section Name (NO item name included)
sga_box_lines = []
ref_list = []
for r in requests_to_submit:
    bill_no_val = str(r.get("bill_no") or bill_no or "").strip()
    loc = (bill_line_cache.get(bill_no_val) or {}).get(r["item_name"])
    line_id = loc.get("section_line_number") or loc.get("line_number") or r.get("bill_item_id") or "" if loc else r.get("bill_item_id") or ""
    sec = str(loc.get("section") or "").strip() if loc else ""

    line_str = f"Line {line_id}" if line_id else ""
    bill_str = f"Bill {bill_no_val}" if bill_no_val else ""

    # SGA Box item text (price, line, bill, section — NO item name)
    sga_parts = [f"${r['total']:.2f}"]
    if line_str:
        sga_parts.append(line_str)
    if bill_str:
        sga_parts.append(bill_str)
    if sec and sec != "Unknown Section":
        sga_parts.append(sec)
    sga_box_lines.append(", ".join(sga_parts))

    # Line, Bill, Section ref for Budget/Bill & Line # box
    if sec and sec != "Unknown Section":
        ref_list.append(f"Bill {bill_no_val}, {sec}, Line {line_id}")
    else:
        ref_list.append(f"Bill {bill_no_val}, Line {line_id}")

sga_bill_box_text = "\n".join(sga_box_lines)
order_bill_refs = ", ".join(ref_list)

# === Generate Budget vs Quoted Full Detail Excel & CSV Comparison Reports ===
import order_excel_builder
order_shot_dir = os.path.join("screenshots", selected_order_id)
os.makedirs(order_shot_dir, exist_ok=True)

excel_detail_path, csv_detail_path = order_excel_builder.generate_order_budget_vs_quoted_excel(
    order_id=selected_order_id,
    requests_to_submit=requests_to_submit,
    bill_line_cache=bill_line_cache,
    scraped_results=scraped_results,
    output_dir=order_shot_dir
)
print(f"  📊 Generated Excel comparison report -> {excel_detail_path}")

print(f"\n{'='*60}")
print(f"Submitting 1 purchase request with {len(requests_to_submit)} line items")
print(f"  Subject: {order_subject}")
print(f"  Amount: ${order_amount:.2f}")
print(f"  Bill refs: {order_bill_refs}")
print(f"{'='*60}")

try:
    # Navigate to create purchase request page
    print(f"\n🌐 Navigating to Create Purchase Request form: {PURCHASE_URL}")
    driver.get(PURCHASE_URL)
    time.sleep(3)

    # Wait for form to load
    print("⏳ Waiting for Purchase Request form to load...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "Subject"))
    )

    # Fill Subject
    print(f"  📝 Filled Subject -> '{order_subject}'")
    subject = driver.find_element(By.ID, "Subject")
    subject.clear()
    subject.send_keys(order_subject)

    # Fill Description (left completely blank as requested)
    try:
        desc_field = driver.find_element(By.ID, "Description")
        desc_field.clear()
        print("  📝 Description field left blank as requested")
    except Exception:
        pass

    # Fill Requested Amount (grand total)
    amount_filled = False
    for selector in [
        By.ID,
        By.NAME,
        By.CSS_SELECTOR,
    ]:
        candidate = None
        try:
            if selector == By.ID:
                candidate = driver.find_element(By.ID, "Amount")
            elif selector == By.NAME:
                candidate = driver.find_element(By.NAME, "Amount")
            else:
                candidate = driver.find_element(By.CSS_SELECTOR, 'input[ng-model*="amount"], input[ng-model*="Amount"], input[name*="amount"], [data-testid*="amount"], input[type="number"]')
            if candidate:
                candidate.clear()
                candidate.send_keys(f"{order_amount:.2f}")
                amount_filled = True
                print("  ✅ Filled Amount field")
                break
        except Exception:
            pass
    if not amount_filled:
        print("  ⚠️ Could not find Amount field")

    # Fill 'What is the Budget/Bill # and Request Line #? (Ex. Bill 376582, Line 4)' field
    bill_line_filled = False
    bill_line_queries = [
        "//*[contains(normalize-space(.), 'What is the Budget/Bill # and Request Line #')]/following::textarea[1] | //*[contains(normalize-space(.), 'What is the Budget/Bill # and Request Line #')]/following::input[1]",
        "//*[contains(normalize-space(.), 'Bill 376582')]/following::textarea[1] | //*[contains(normalize-space(.), 'Bill 376582')]/following::input[1]",
        "//*[contains(normalize-space(.), 'Request Line #')]/following::textarea[1] | //*[contains(normalize-space(.), 'Request Line #')]/following::input[1]",
        "//*[contains(normalize-space(.), 'Budget/Bill')]/following::textarea[1] | //*[contains(normalize-space(.), 'Budget/Bill')]/following::input[1]",
    ]
    for query in bill_line_queries:
        try:
            elems = driver.find_elements(By.XPATH, query)
            if elems:
                field = elems[0]
                if field.get_attribute("readonly") or field.get_attribute("disabled"):
                    driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles: true})); arguments[0].dispatchEvent(new Event('change', {bubbles: true}));", field, order_bill_refs)
                else:
                    field.clear()
                    field.send_keys(order_bill_refs)
                bill_line_filled = True
                print(f"  ✅ Filled 'What is the Budget/Bill # and Request Line #' field: {order_bill_refs}")
                break
        except Exception:
            pass

    # Fill SGA Bill Box: 'Include Bill # and total reimbursement amount below ($ Per line item)' under SGA Bill
    sga_filled = False
    sga_queries = [
        "//*[contains(normalize-space(.), 'Include Bill # and total reimbursement amount below')]/following::textarea[1] | //*[contains(normalize-space(.), 'Include Bill # and total reimbursement amount below')]/following::input[1]",
        "//*[contains(normalize-space(.), 'SGA Bill')]/following::textarea[1] | //*[contains(normalize-space(.), 'SGA Bill')]/following::input[1]",
        "//*[contains(normalize-space(.), 'Bill Details')]/following::textarea[1] | //*[contains(normalize-space(.), 'Bill Details')]/following::input[1]",
    ]
    for query in sga_queries:
        try:
            elems = driver.find_elements(By.XPATH, query)
            if elems:
                field = elems[0]
                field.clear()
                field.send_keys(sga_bill_box_text)
                sga_filled = True
                print("  ✅ Filled SGA Bill Box with item details (Item names excluded)")
                break
        except Exception:
            pass

    # Fallback to Description Box if custom form fields could not be populated
    if not sga_filled or not bill_line_filled:
        try:
            desc_field = driver.find_element(By.ID, "Description")
            fallback_parts = []
            if sga_bill_box_text:
                fallback_parts.append(f"SGA Bill Item Details:\n{sga_bill_box_text}")
            if order_bill_refs:
                fallback_parts.append(f"Budget/Bill References:\n{order_bill_refs}")
            fallback_text = "\n\n".join(fallback_parts)
            desc_field.clear()
            desc_field.send_keys(fallback_text)
            print("  📝 Loaded details into Description box (Fallback)")
        except Exception:
            pass

    # Upload documentation files (Cart Screenshot & Budget vs Quoted Detail Excel)
    cart_screenshot = os.path.join("screenshots", selected_order_id, "cart.png")
    if not os.path.exists(cart_screenshot):
        safe_bill = "".join(c if c.isalnum() or c in " -_" else "_" for c in bill_title)
        cart_screenshot = os.path.join(os.path.dirname(__file__), "web-app", "screenshots", safe_bill, "cart.png")
    if not os.path.exists(cart_screenshot):
        cart_screenshot = os.path.join(DOWNLOAD_DIR, "cart.png")

    file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    if file_inputs:
        # Upload #1: Cart screenshot
        if os.path.exists(cart_screenshot):
            try:
                driver.execute_script("arguments[0].style.display='block';", file_inputs[0])
                file_inputs[0].send_keys(os.path.abspath(cart_screenshot))
                print(f"  📎 Upload #1: Uploaded cart screenshot ({os.path.basename(cart_screenshot)})")
                time.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️ Upload #1 failed: {e}")

        # Upload #2: Budget vs Quoted Detail Excel file
        if len(file_inputs) > 1 and excel_detail_path and os.path.exists(excel_detail_path):
            try:
                driver.execute_script("arguments[0].style.display='block';", file_inputs[1])
                file_inputs[1].send_keys(os.path.abspath(excel_detail_path))
                print(f"  📎 Upload #2: Uploaded Budget vs Quoted Excel detail ({os.path.basename(excel_detail_path)})")
                time.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️ Upload #2 failed: {e}")
    else:
        print("  ℹ️ File upload inputs not found on current form page.")

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
