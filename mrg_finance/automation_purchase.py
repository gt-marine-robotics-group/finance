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
    TimeoutException,
)
try:
    from engage_bill_lookup import (lookup_bill_item_locations,
                                    prompt_verified_location, confirm_continue_to_engage, prompt_fee_reference,
                                    funding_kind_from_title)
except ModuleNotFoundError:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from engage_bill_lookup import (lookup_bill_item_locations,
                                    prompt_verified_location, confirm_continue_to_engage, prompt_fee_reference,
                                    funding_kind_from_title)
import getpass
from pathlib import Path

PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from mrg_finance.purchase_cart import prepare_cart, recheck_cart
from mrg_finance.purchase_validation import money, require_matching_total
from mrg_finance.engage_fields import fill_purchase_fields, run_engage_step, save_engage_diagnostic
from mrg_finance.vendor_payee import lookup_vendor_payee, vendor_key
from mrg_finance.screenshot_capture import save_page_screenshot
from mrg_finance.purchase_sources import (
    CartReplacement, OrderingLinkStore, edit_links_before_cart,
    offer_quote_replacements, purchase_source,
)

# === CONFIG & PATHS ===
CWD_XLSX = os.path.join(os.getcwd(), "FY27_Bills_Budget.xlsx")
REPO_XLSX = os.path.expanduser("~/mrg/finance/FY27_Bills_Budget.xlsx")
ONEDRIVE_XLSX = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)

if os.path.exists(CWD_XLSX):
    DEFAULT_XLSX = CWD_XLSX
elif os.path.exists(REPO_XLSX):
    DEFAULT_XLSX = REPO_XLSX
elif os.path.exists(ONEDRIVE_XLSX):
    DEFAULT_XLSX = ONEDRIVE_XLSX
else:
    DEFAULT_XLSX = REPO_XLSX

XLSX_PATH = os.environ.get("FINANCE_XLSX_PATH", DEFAULT_XLSX)
if "--excel-path" in sys.argv:
    idx = sys.argv.index("--excel-path")
    if idx + 1 < len(sys.argv):
        XLSX_PATH = sys.argv[idx + 1]

SHEET_NAME = "Bills"
DOWNLOAD_DIR = "downloads"
PURCHASE_URL = "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/Finance/CreatePurchaseRequest"
USERNAME = os.environ.get("ENGAGE_USERNAME", "")
PASSWORD = os.environ.get("ENGAGE_PASSWORD", "")



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



def main():
    global XLSX_PATH, USERNAME, PASSWORD

    # Dynamically resolve XLSX_PATH
    import sys
    if "--excel-path" in sys.argv:
        idx = sys.argv.index("--excel-path")
        if idx + 1 < len(sys.argv):
            XLSX_PATH = sys.argv[idx + 1]
    elif os.environ.get("FINANCE_XLSX_PATH"):
        XLSX_PATH = os.environ["FINANCE_XLSX_PATH"]
    else:
        cwd_xlsx = os.path.join(os.getcwd(), "FY27_Bills_Budget.xlsx")
        repo_xlsx = os.path.expanduser("~/mrg/finance/FY27_Bills_Budget.xlsx")
        onedrive_xlsx = os.path.expanduser(
            "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
            "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
        )
        if os.path.exists(cwd_xlsx):
            XLSX_PATH = cwd_xlsx
        elif os.path.exists(repo_xlsx):
            XLSX_PATH = repo_xlsx
        elif os.path.exists(onedrive_xlsx):
            XLSX_PATH = onedrive_xlsx
        else:
            XLSX_PATH = repo_xlsx

    if not USERNAME:
        USERNAME = os.environ.get("ENGAGE_USERNAME", "")
    if not PASSWORD:
        PASSWORD = os.environ.get("ENGAGE_PASSWORD", "")

    # --- Fresh sync from SharePoint ---
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
    excel_file.close()

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
    for position, (_, row) in enumerate(df_orders.iterrows()):
        r_dict = row.to_dict()
        r_dict["_ordering_row"] = df_orders.attrs["header_row"] + 1 + position
        order_id = str(spreadsheet_utils.get_col_val(r_dict, "order_id") or row.get(oid_col, "")).strip()
        item_name = str(spreadsheet_utils.get_col_val(r_dict, "item_name") or "").strip()
        bill_item_id = str(spreadsheet_utils.get_col_val(r_dict, "bill_item_id") or "").replace(".0", "").strip()

        # Skip header separators or empty rows
        if not order_id or order_id.startswith("Order ") or not (bill_item_id or item_name):
            continue
        status = str(spreadsheet_utils.get_col_val(r_dict, "status") or "").strip().lower()
        if status not in ("", "pending", "pending purchase", "bill approved"):
            continue

        if order_id not in order_groups:
            order_groups[order_id] = []
        order_groups[order_id].append(r_dict)

    if not order_groups:
        print("No active orders found in Ordering sheet.")
        print("Use the web app to create orders first (Orders page → Create Order)")
        exit(0)

    order_ids = list(order_groups.keys())
    if not pre_selected_order:
        print("\nAvailable Orders:")
    for i, oid in enumerate(order_ids if not pre_selected_order else [], 1):
        items_in_o = order_groups[oid]
        v_name = ""
        for itm in items_in_o:
            b_id = str(spreadsheet_utils.get_col_val(itm, "bill_item_id") or "").replace(".0", "").strip()
            b_row = bill_item_map.get(b_id, {})
            _, v = purchase_source(itm, b_row)
            if v:
                v_name = v
                break
        if not v_name:
            parts = oid.split("_")
            if len(parts) >= 3 and parts[1]:
                v_name = parts[1].capitalize()
        v_name = v_name or "Unknown"
        print(f"  {i}. {oid} ({v_name}, {len(items_in_o)} items)")

    if pre_selected_order:
        selected_order_id = pre_selected_order
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
        r_dict = row if isinstance(row, dict) else row.to_dict()
        b_id = str(spreadsheet_utils.get_col_val(r_dict, "bill_item_id") or "").replace(".0", "").strip()
        b_row = bill_item_map.get(b_id, {})
        _, v = purchase_source(r_dict, b_row)
        if v:
            vendor_name = v
            break
    if not vendor_name:
        parts = selected_order_id.split("_")
        if len(parts) >= 3 and parts[1]:
            vendor_name = parts[1].capitalize()
    vendor_name = vendor_name or "Vendor"

    purchase_date = date.today().strftime("%Y-%m-%d")

    for i, row in enumerate(order_rows):
        r_dict = row if isinstance(row, dict) else row.to_dict()
        b_id = str(spreadsheet_utils.get_col_val(r_dict, "bill_item_id") or "").replace(".0", "").strip()
        b_row = bill_item_map.get(b_id, {})
        has_bill_row = bool(b_row)

        item_bill_no = str(spreadsheet_utils.get_col_val(b_row, "bill_no") or spreadsheet_utils.get_col_val(r_dict, "bill_no") or "").replace(".0", "").strip()
        if item_bill_no and not bill_no:
            bill_no = item_bill_no

        item_name = str(spreadsheet_utils.get_col_val(r_dict, "item_name") or spreadsheet_utils.get_col_val(b_row, "item_name") or "").strip()
        description = str(spreadsheet_utils.get_col_val(r_dict, "description") or spreadsheet_utils.get_col_val(b_row, "description") or "").strip()
        link, item_vendor = purchase_source(r_dict, b_row, vendor_name)
        source_bill_title = str(spreadsheet_utils.get_col_val(b_row, "bill_title") or spreadsheet_utils.get_col_val(r_dict, "bill_title") or "").strip()

        approved_cost = spreadsheet_utils.get_col_val(b_row, "cost")
        if approved_cost in (None, ""):
            approved_cost = spreadsheet_utils.get_col_val(r_dict, "cost") or spreadsheet_utils.get_col_val(r_dict, "allocation") or 0.0
        cost = float(money(approved_cost))
        raw_qty = spreadsheet_utils.get_col_val(r_dict, "quantity")
        raw_qty = 1 if raw_qty in (None, "") else raw_qty
        qty = safe_int(raw_qty)
        if str(float(raw_qty)) != str(float(qty)):
            raise SystemExit(f"Quantity must be a whole number for {item_name}.")
        if vendor_key(item_vendor) != vendor_key(vendor_name):
            raise SystemExit("Each Order ID must contain only one vendor; split this order before purchasing.")
        if qty <= 0 or not item_bill_no or not item_name or not link:
            raise SystemExit(f"Invalid order row: {item_name or b_id}. Need positive quantity, bill number, and product link.")
        total = cost * qty

        funding_kind = funding_kind_from_title(source_bill_title)
        bill_line_ref = f"{funding_kind.title()} {item_bill_no or '?'}, Line {b_id or i+1}"

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
            "funding_kind": funding_kind,
            "link": link,
            "ordering_row": r_dict["_ordering_row"],
        })

    # === Build purchase request list ===
    # === Display summary ===
    print(f"\n{'='*60}")
    source_kinds = {r["funding_kind"] for r in requests_to_submit}
    source_label = next(iter(source_kinds)).title() if len(source_kinds) == 1 else "Funding request"
    print(f"📋 Purchase Request for: {bill_title} ({source_label} #{bill_no})")
    print(f"{'='*60}")
    print(f"\n{'Bill Item ID':<12} {'Item Name':<38} {'Qty':<5} {'Approved':<10} {'Allocation'}")
    print("-" * 75)

    for i, r in enumerate(requests_to_submit):
        engage_line = r["bill_item_id"]
        print(f"{engage_line:<12} {r['item_name']:<38} {r['quantity']:<5} ${r['cost']:<9.2f} ${r['total']:.2f}")

    grand_total = sum(r["total"] for r in requests_to_submit)
    print(f"\n  💰 Grand Total Allocation: ${grand_total:.2f}")

    # The approved allocation remains a baseline; the request uses the real cart.
    source = "automated"
    if "--cart-source" in sys.argv:
        source = sys.argv[sys.argv.index("--cart-source") + 1]
    print(f"\nWorkbook: {os.path.abspath(XLSX_PATH)}")
    print(f"Cart mode: {source}")
    print(f"Evidence directory: {Path('screenshots', selected_order_id).resolve()}")
    print("Review prices in the comparison spreadsheet; submission stays manual in Engage.")
    if input("\nPrepare and verify vendor cart? [Y/n]: ").strip().lower() in ("n", "no"):
        raise SystemExit(0)
    try:
        store = OrderingLinkStore(XLSX_PATH, selected_order_id, requests_to_submit, df_orders.attrs["header_row"])
        vendor_name = edit_links_before_cart(requests_to_submit, vendor_name, store)
        def save_cart_link(url):
            count = spreadsheet_utils.update_order_table_links(XLSX_PATH, selected_order_id,
                share_cart_url=url, expected_rows=len(requests_to_submit))
            if count != len(requests_to_submit):
                raise ValueError("The Share-A-Cart URL was not saved to every selected Ordering row.")
            print(f"Saved and verified Share-A-Cart URL in Ordering ({count} rows): {url}\n"
                  f"Workbook: {os.path.abspath(XLSX_PATH)}")
        while True:
            try:
                cart = prepare_cart(requests_to_submit, vendor_name, selected_order_id, source,
                                    quote_review=lambda items, vendor: offer_quote_replacements(items, vendor, store),
                                    save_share_url=save_cart_link)
                break
            except CartReplacement as replacement:
                vendor_name = replacement.vendor
    except Exception as error:
        print(f"\nPurchase stopped before Engage: {error}")
        raise SystemExit(1) from error
    driver = None
    try:
        share_cart_url = cart["share_url"]
        order_shot_dir = str(cart["folder"])
        grand_total = float(sum(money(r["cost"]) * r["quantity"] for r in requests_to_submit))
        order_amount = float(cart["total"])
        scraped_results = {r["item_name"]: r["quoted_unit_cost"] for r in requests_to_submit}
        for r in requests_to_submit:
            r["total"] = r["quoted_total"]
        payee = lookup_vendor_payee(vendor_name, requests_to_submit[0]["link"])
        print(f"\nApproved allocation: ${grand_total:.2f}")
        print(f"Verified merchandise: ${cart['subtotal']}")
        print(f"Shipping: ${cart['shipping']} | Tax: ${cart['tax']}")
        print(f"Engage requested amount: ${order_amount:.2f}")
        print(f"Change from allocation: ${order_amount - grand_total:+.2f}")
        print(f"\n{'Item':<35} {'Qty':>4} {'Approved/unit':>15} {'Cart/unit':>12}")
        for r in requests_to_submit:
            print(f"{r['item_name'][:35]:<35} {r['quantity']:>4} ${r['cost']:>14.2f} ${r['quoted_unit_cost']:>11.2f}")
        print(f"Payee: {payee['name']}\nAddress: {payee.get('address', 'Needs manual review')}")
        print(f"Payee source: {payee.get('source') or 'No structured contact data found on vendor site'}")
        import order_excel_builder
        preview_path, preview_csv = order_excel_builder.generate_order_budget_vs_quoted_excel(
            order_id=selected_order_id, requests_to_submit=requests_to_submit,
            scraped_results=scraped_results, output_dir=order_shot_dir,
            preliminary=True, cart_quote=cart,
        )
        print(f"Automatically filled comparison workbook: {os.path.abspath(preview_path)}\n"
              f"CSV: {os.path.abspath(preview_csv)}\n"
              "Cart prices and charges are saved. Funding line/section references will be completed after Engage lookup.\n"
              "Close the comparison workbook before continuing so those references can be updated.")
        print("Press Enter to open and fill Engage, or type 'n' to stop with the comparison workbook saved; "
              "final submission remains manual.")
        if not confirm_continue_to_engage():
            raise SystemExit(0)

        # Request credentials only after the cart and amount have been reviewed.
        if not USERNAME:
            USERNAME = input("Enter GT username: ").strip()
        if not PASSWORD:
            PASSWORD = getpass.getpass("Enter GT password (for CampusLabs + Duo MFA): ")

        # === Selenium Setup ===
        print("\n🌐 Launching Chrome browser...")
        options = webdriver.ChromeOptions()
        options.add_argument("--incognito")
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
            WebDriverWait(driver, 180).until(lambda d: bool(d.current_url and "gatech.campuslabs.com/engage" in d.current_url))
        except TimeoutException:
            print("  ⏳ Duo MFA wait timed out automatically.")
            input("  Press Enter after completing Duo MFA in your browser window → ")
        print("✅ Duo MFA Login verified!")

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
            while not lookup:
                diagnostic = Path(order_shot_dir) / "engage_diagnostics" / f"bill_{bill_number}.png"
                try:
                    save_page_screenshot(driver, diagnostic, full_page=False)
                    print(f"  Lookup diagnostic: {diagnostic}")
                except Exception:
                    pass
                print("  Open Menu → Budget in this Chrome window. No funding references have been guessed.")
                action = input("  Enter to retry this bill, 'manual' to enter verified references, or 'cancel': ").strip().lower()
                if action in ("cancel", "quit", "q"):
                    raise SystemExit("Engage lookup cancelled; comparison workbook is saved.")
                if action == "manual":
                    break
                if action:
                    print("  Press Enter, type 'manual', or type 'cancel'.")
                    continue
                lookup = lookup_bill_item_locations(driver, bill_number, item_names, navigate=False)
            bill_line_cache[bill_number] = lookup

        print("\n📋 Resolved Engage Line References:")
        for r in requests_to_submit:
            bill_no_for_item = str(r.get("bill_no") or bill_no or "").strip()
            cache_for_bill = bill_line_cache.get(bill_no_for_item) or {}
            location = cache_for_bill.get(r["item_name"])
            r["funding_kind"] = (location or {}).get("funding_kind") or r["funding_kind"]
            funding_label = r["funding_kind"].title()

            if location and location.get("section") not in (None, "", "Unknown Section") and (location.get("section_line_number") or location.get("line_number")):
                section_name = str(location.get("section") or "").strip()
                # Prioritize line position within section (section_line_number) over global bill count
                line_id = location.get("section_line_number") or location.get("line_number")
                r["resolved_location"] = location
                r["resolved_section"] = section_name
                r["resolved_line_id"] = line_id
                r["engage_line_ref"] = f"{funding_label} {bill_no_for_item}, {section_name}, Line {line_id}"
                r["sga_line_text"] = f"${r['total']:.2f}, Line {line_id}, {funding_label} {bill_no_for_item}, {section_name}"
                r["bill_line_ref"] = r["engage_line_ref"]
                print(f"  ✓ '{r['item_name']}' -> {r['engage_line_ref']}")
            else:
                print(f"  Engage could not match '{r['item_name']}' in Bill {bill_no_for_item}.")
                line_id, section_name = prompt_verified_location()
                if not bill_no_for_item:
                    raise SystemExit("Missing verified bill number; request stopped.")
                r["resolved_line_id"] = line_id
                r["resolved_section"] = section_name
                r["engage_line_ref"] = f"{funding_label} {bill_no_for_item}, {section_name}, Line {line_id}"
                r["bill_line_ref"] = r["engage_line_ref"]
                r["sga_line_text"] = f"${r['total']:.2f}, Line {line_id}, {funding_label} {bill_no_for_item}, {section_name}"

        # === Submit Purchase Requests ===

        # Subject line format: Marine Robotics Group "Vendor" Purchase Request YYYY-MM-DD
        order_subject = f"Marine Robotics Group {vendor_name} Purchase Request {purchase_date}"


        # Single source of truth for Engage form texts
        funding_lines = {}
        for r in requests_to_submit:
            kind = r["funding_kind"]
            funding_lines[kind] = "\n".join(filter(None, (funding_lines.get(kind), r["sga_line_text"])))
        order_bill_refs = "\n".join(r["engage_line_ref"] for r in requests_to_submit)
        for fee, value in (("Shipping", cart["shipping"]), ("Tax", cart["tax"])):
            if value:
                while True:
                    ref = prompt_fee_reference(fee, value)
                    if len(funding_lines) == 1 or "budget" in ref.lower() or "bill" in ref.lower():
                        break
                    print("This order uses both Budget and Bill funding. Include Budget or Bill in the fee reference.")
                kind = funding_kind_from_title(ref) if "bill" in ref.lower() or "budget" in ref.lower() else next(iter(funding_lines))
                funding_lines[kind] = "\n".join(filter(None, (funding_lines.get(kind), f"${value}, {fee}, {ref}")))
                order_bill_refs += f"\n{ref}"

        # === Generate Budget vs Quoted Full Detail Excel & CSV Comparison Reports ===
        os.makedirs(order_shot_dir, exist_ok=True)

        excel_detail_path, csv_detail_path = order_excel_builder.generate_order_budget_vs_quoted_excel(
            order_id=selected_order_id,
            requests_to_submit=requests_to_submit,
            bill_line_cache=bill_line_cache,
            scraped_results=scraped_results,
            output_dir=order_shot_dir, cart_quote=cart,
        )
        print(f"  Comparison spreadsheet: {os.path.abspath(excel_detail_path)}")
        print(f"  CSV: {os.path.abspath(csv_detail_path)}")
        print(f"  Cart screenshot: {cart['screenshot']}")
        input("Review the comparison spreadsheet, then Enter to fill Engage: ")

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

            # Fill Description
            try:
                desc_field = driver.find_element(By.ID, "Description")
                desc_field.clear()
                if share_cart_url:
                    desc_field.send_keys(f"Share-A-Cart Link:\n{share_cart_url}")
                    print(f"  📝 Injected Share-A-Cart link into Description field: {share_cart_url}")
                else:
                    print("  📝 Description field left blank as requested")
            except Exception:
                pass

            # Verify precise custom fields before attaching any documentation.
            expected_funding = " and ".join("SGA " + kind.title() for kind in funding_lines)
            input(f"Select the funding Category/Account and {expected_funding} option in Engage, then Enter: ")
            amount_field = run_engage_step(driver, order_shot_dir, "Engage form filling", lambda: fill_purchase_fields(
                driver, amount=order_amount, cart_total=cart["total"],
                bill_refs=order_bill_refs, payee=payee,
                funding_lines=funding_lines,
            ))
            def verify_before_upload():
                recheck_cart(cart, requests_to_submit)
                require_matching_total(cart["total"], amount_field.get_attribute("value"))
            run_engage_step(driver, order_shot_dir, "Cart/Engage amount verification", verify_before_upload)
            # Add a reconciliation sheet so fees and total charged remain explicit.
            import openpyxl
            report = openpyxl.load_workbook(excel_detail_path)
            order_excel_builder.write_cart_reconciliation(
                report, selected_order_id, cart, approved_allocation=grand_total,
                engage_amount=money(amount_field.get_attribute("value")), payee=payee,
            )
            report.save(excel_detail_path)
            report.close()
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if len(file_inputs) < 2:
                raise RuntimeError("Two Engage attachment controls were not found; no files uploaded.")
            for field, path in zip(file_inputs, (cart["screenshot"], excel_detail_path)):
                if not os.path.isfile(path):
                    raise RuntimeError(f"Required attachment missing: {path}")
                field.send_keys(os.path.abspath(path))
                print(f"  Attached: {os.path.abspath(path)}")

            # PAUSE — let user review and submit manually
            print(f"\n  ⏸️  Form pre-filled with {len(requests_to_submit)} items totaling ${order_amount:.2f}")
            print(f"     Review and fill remaining fields (Category, Account, etc.)")
            print(f"     Funding: {', '.join(sorted({r['funding_kind'].title() + ' ' + r['bill_no'] for r in requests_to_submit}))}")
            input(f"     Press Enter after you submit this purchase request → ")

            # Capture Engage Purchase Request URL
            engage_url = None
            try:
                if driver:
                    curr = driver.current_url
                    if curr and "CreatePurchaseRequest" not in curr and "campuslabs.com/engage" in curr:
                        engage_url = curr
            except Exception:
                pass

            user_engage = input(f"  👉 Enter submitted Engage Request URL (or Enter to {f'use {engage_url}' if engage_url else 'skip'}): ").strip()
            if user_engage:
                engage_url = user_engage

            from urllib.parse import urlparse
            submitted = urlparse(engage_url or "")
            if (submitted.hostname != "gatech.campuslabs.com" or "/engage/" not in submitted.path
                    or "createpurchaserequest" in submitted.path.lower()):
                raise RuntimeError("No submitted Engage request URL was confirmed; request completion was not recorded.")
            print(f"  Submitted request confirmed: {engage_url}")

            if engage_url:
                try:
                    cnt = spreadsheet_utils.update_order_table_links(XLSX_PATH, selected_order_id, engage_request_url=engage_url)
                    if cnt > 0:
                        print(f"  📝 Saved Engage Request link to Ordering sheet ({cnt} rows): {engage_url}")
                except Exception as e:
                    print(f"  ⚠️ Could not save Engage link to spreadsheet: {e}")

            # Sync updated spreadsheet to SharePoint via rclone
            try:
                import subprocess
                print("☁️ Syncing updated spreadsheet to SharePoint...")
                sync_result = subprocess.run(
                    ["rclone", "copy", "--ignore-checksum", "--ignore-size", "--update",
                     XLSX_PATH, "onedrive:OPS-1 Operations/FY27 Finances"],
                    capture_output=True, text=True, timeout=30
                )
                if sync_result.returncode == 0:
                    print("  Spreadsheet synced to SharePoint.")
                else:
                    print(f"  Spreadsheet sync failed: {sync_result.stderr.strip()}")
            except Exception as e:
                print(f"  ℹ️ SharePoint sync notice: {e}")

        except Exception as e:
            print(f"\nPurchase stopped: {e}")
            save_engage_diagnostic(driver, order_shot_dir)
            input("Both Chrome windows remain open. Inspect or finish the form manually; "
                  "press Enter only when you are ready to end this run and close them: ")
            raise SystemExit(1) from e

    finally:
        cart["driver"].quit()
        if driver is not None:
            driver.quit()

    # === Final Report ===
    print(f"\n{'='*60}")
    print(f"🎉 COMPLETED — Purchase Request for {bill_title}")
    print(f"{'='*60}")
    print(f"  Order: {bill_title}")
    print(f"  Items: {len(requests_to_submit)}")
    print(f"  Verified request amount: ${order_amount:.2f}")
    print()


if __name__ == "__main__":
    main()
