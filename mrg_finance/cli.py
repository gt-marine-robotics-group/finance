#!/usr/bin/env python3
"""
mrg.py — MRG Finance CLI Tool

Usage:
    mrg-finance report [--fresh] [--order ORDER_ID]
    mrg-finance doctor [--fresh]
    mrg-finance bill-request [--fresh] [--bill TITLE]
    mrg-finance purchase [--fresh] [--order ORDER_ID]
    mrg-finance price-check [--fresh] [--bill TITLE] [--cart]
    mrg-finance screenshots [--fresh] [--bill TITLE]

Commands:
    report           Generate Budget vs Quoted Full Detail Excel (.xlsx) & CSV reports
    doctor           Run diagnostic health check on FY27_Bills_Budget.xlsx
    bill-request     Submit a bill to CampusLabs Engage
    purchase         Create purchase requests on Engage (grouped by vendor from OrderT)
    price-check      Check current prices vs allocation, warn on overrun
    screenshots      Scrape prices + take screenshots for items in a bill

Options:
    --fresh          Download latest xlsx + screenshots from SharePoint before running
    --bill TITLE     Specify bill title (skips interactive selection)
    --order ID       Specify order ID (skips interactive selection)
    --cart           Generate Amazon cart link after price check
"""

import os
import sys
import subprocess
import argparse

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from mrg_finance import price_scraper
except ImportError:
    import price_scraper
CWD_XLSX = os.path.join(os.getcwd(), "FY27_Bills_Budget.xlsx")
REPO_XLSX = os.path.expanduser("~/mrg/finance/FY27_Bills_Budget.xlsx")
ONEDRIVE_XLSX = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)

def get_xlsx_path():
    """Get the path to the Excel file, dynamically checking environment and defaults."""
    env_path = os.environ.get("FINANCE_XLSX_PATH")
    if env_path:
        return env_path
    if os.path.exists(CWD_XLSX):
        return CWD_XLSX
    if os.path.exists(REPO_XLSX):
        return REPO_XLSX
    if os.path.exists(ONEDRIVE_XLSX):
        return ONEDRIVE_XLSX
    return REPO_XLSX


XLSX_PATH = get_xlsx_path()
SHEET_NAME = "Bills"
ORDERING_SHEET = "Ordering"
SCREENSHOT_DIR = os.path.abspath("screenshots")
SKIP_TITLES = ("nan", "request", "liquid", "misc")


def get_python_executable():
    """Get the appropriate Python executable, preferring virtualenv if present."""
    venv_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    venv_win = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python.exe")
    if os.path.exists(venv_win):
        return venv_win
    return sys.executable


def download_xlsx_via_graph_api(target_path):
    """Download fresh FY27_Bills_Budget.xlsx directly from SharePoint via Graph API."""
    import requests
    try:
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "web-app"))
        import xlsx_manager
        creds = xlsx_manager._get_graph_token()
        if not creds:
            return False
        access_token, drive_id, file_id = creds
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"  ⚠️ Graph API download failed: {e}")
    return False


def fresh_sync():
    """Download latest xlsx + screenshots from SharePoint."""
    print("Syncing from SharePoint...")
    xlsx_path = get_xlsx_path()
    xlsx_dir = os.path.dirname(xlsx_path)
    r1 = subprocess.run(
        ["rclone", "copy", "--ignore-checksum", "--ignore-size", "--update",
         "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
         xlsx_dir],
        capture_output=True, text=True, timeout=30
    )
    if r1.returncode == 0:
        print("  ✅ xlsx synced via rclone")
    else:
        err_brief = r1.stderr.strip().split("\n")[0] if r1.stderr else "rclone not configured"
        print(f"  ℹ️ rclone ({err_brief}). Trying Graph API fallback...")
        if download_xlsx_via_graph_api(xlsx_path):
            print("  ✅ xlsx synced via Microsoft Graph API!")
        else:
            print("  ⚠️ Could not sync xlsx file")

    r2 = subprocess.run(
        ["rclone", "copy", "--ignore-checksum", "--ignore-size", "--update",
         "onedrive:OPS-1 Operations/FY27 Finances/screenshots",
         SCREENSHOT_DIR],
        capture_output=True, text=True, timeout=60
    )
    if r2.returncode == 0:
        print("  ✅ screenshots synced")
    else:
        print(f"  ℹ️ screenshots sync skipped (rclone not configured)")
    print()


def load_xlsx():
    """Load the xlsx and return filtered dataframe."""
    import spreadsheet_utils
    import warnings
    warnings.filterwarnings('ignore')

    df = spreadsheet_utils.read_sheet_robust(get_xlsx_path(), [SHEET_NAME, "Bill", "Budget"])
    if df.empty:
        return df

    # Filter to real items
    df_valid = df[
        (df["Bill Title"].astype(str).str.strip() != "") &
        (df["Item Name"].astype(str).str.strip() != "")
    ].copy()
    df_valid = df_valid[~df_valid["Bill Title"].astype(str).str.strip().str.lower().apply(
        lambda t: any(t.startswith(s) for s in SKIP_TITLES)
    )]
    return df_valid


def load_ordering():
    """Load the Ordering sheet from local xlsx."""
    import spreadsheet_utils
    import warnings
    warnings.filterwarnings('ignore')

    return spreadsheet_utils.read_sheet_robust(get_xlsx_path(), [ORDERING_SHEET, "Orders", "OrderT"])


def select_bill(df, bill_title=None):
    """Interactive bill selection or use provided title."""
    titles = df["Bill Title"].astype(str).str.strip().unique()

    if bill_title:
        match = [t for t in titles if bill_title.lower() in t.lower()]
        if match:
            return match[0]
        print(f"⚠️ Bill '{bill_title}' not found. Choose from list below:")

    print("\nAvailable Bills:")
    titles_list = list(titles)
    for i, t in enumerate(titles_list, 1):
        print(f"  {i}. {t}")

    while True:
        try:
            choice = input(f"\nSelect bill (1-{len(titles_list)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(titles_list):
                return titles_list[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid selection, try again.")


# ============================================================
# COMMAND: screenshots
# ============================================================
def cmd_screenshots(args):
    """Scrape prices and capture full-page product screenshots for a bill."""
    py_exe = get_python_executable()
    cmd = [py_exe, os.path.join(SCRIPT_DIR, "automation_screenshots.py"), "--excel-path", get_xlsx_path()]
    if getattr(args, "bill", None):
        cmd.extend(["--bill", args.bill])
    if getattr(args, "interactive", False):
        cmd.append("--interactive")
    if getattr(args, "no_review", False):
        cmd.append("--no-review")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


# ============================================================
# COMMAND: bill-request
# ============================================================
def cmd_bill_request(args):
    """Submit a bill to CampusLabs Engage."""
    # This wraps the existing automation.py
    py_exe = get_python_executable()
    cmd = [py_exe, os.path.join(SCRIPT_DIR, "automation.py"), "--excel-path", get_xlsx_path()]
    if getattr(args, "bill", None):
        cmd.extend(["--bill", args.bill])
    if getattr(args, "fresh", False):
        cmd.append("--fresh")
    if getattr(args, "no_review", False):
        cmd.append("--no-review")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


# ============================================================
# COMMAND: purchase
# ============================================================
def cmd_purchase(args):
    """Create purchase requests on Engage from the Ordering sheet."""
    import spreadsheet_utils

    df_order = load_ordering()

    if df_order.empty:
        print("No pending orders found in the Ordering sheet.")
        print("Use the web app to create orders first (Create New Order → select items → Submit)")
        sys.exit(0)

    # Load Bills sheet to resolve missing/uncalculated formula fields
    df_bills = load_xlsx()
    bill_item_map = {}
    if not df_bills.empty:
        for _, b_row in df_bills.iterrows():
            b_dict = b_row.to_dict()
            b_id = spreadsheet_utils.clean_id(spreadsheet_utils.get_col_val(b_dict, "bill_item_id"))
            if b_id:
                bill_item_map[b_id] = b_dict

    oid_col = next((c for c in df_order.columns if isinstance(c, str) and "Order ID" in c), "Order ID")
    status_col = next((c for c in df_order.columns if c.strip().lower() == "status"), "Status")
    if status_col not in df_order.columns:
        df_order[status_col] = ""

    # Filter to rows with Order IDs but not yet purchased
    df_pending = df_order[
        (df_order[oid_col].astype(str).str.strip() != "") &
        (~df_order[oid_col].astype(str).str.strip().str.startswith("ungrouped_")) &
        (df_order[status_col].astype(str).str.strip().str.lower().isin(["", "pending", "pending purchase", "bill approved"]))
    ]

    if df_pending.empty:
        print("No pending orders found in the Ordering sheet.")
        print("Use the web app to create orders first (Create New Order → select items → Submit)")
        sys.exit(0)

    def _resolve_item(it_row):
        d = it_row.to_dict() if hasattr(it_row, "to_dict") else dict(it_row)
        b_id = spreadsheet_utils.clean_id(spreadsheet_utils.get_col_val(d, "bill_item_id"))
        b_dict = bill_item_map.get(b_id, {})

        name = (
            spreadsheet_utils.get_col_val(d, "item_name")
            or spreadsheet_utils.get_col_val(b_dict, "item_name")
            or ""
        )
        vendor = (
            spreadsheet_utils.get_col_val(d, "vendor")
            or spreadsheet_utils.get_col_val(b_dict, "vendor")
            or ""
        )
        qty = spreadsheet_utils.safe_float(
            spreadsheet_utils.get_col_val(d, "quantity")
            or spreadsheet_utils.get_col_val(b_dict, "quantity")
            or 1.0,
            default=1.0,
        )
        alloc_raw = spreadsheet_utils.get_col_val(d, "allocation")
        alloc_val = spreadsheet_utils.safe_float(alloc_raw, default=0.0) if alloc_raw else 0.0
        if alloc_val == 0.0:
            total_raw = spreadsheet_utils.get_col_val(d, "total_cost") or spreadsheet_utils.get_col_val(b_dict, "total_cost")
            total_val = spreadsheet_utils.safe_float(total_raw, default=0.0) if total_raw else 0.0
            if total_val > 0.0:
                alloc_val = total_val
            else:
                unit_cost_raw = spreadsheet_utils.get_col_val(d, "cost") or spreadsheet_utils.get_col_val(b_dict, "cost")
                unit_cost = spreadsheet_utils.safe_float(unit_cost_raw, default=0.0) if unit_cost_raw else 0.0
                alloc_val = unit_cost * qty

        return {
            "name": name,
            "vendor": vendor,
            "qty": qty,
            "allocation": alloc_val,
        }

    def _extract_vendor(oid, resolved_items):
        for it in resolved_items:
            if it["vendor"]:
                return it["vendor"]
        parts = oid.split("_")
        if len(parts) >= 3 and parts[1]:
            return parts[1].capitalize()
        return "Unknown"

    # Group by Order ID
    orders = {}
    for _, row in df_pending.iterrows():
        oid = str(row[oid_col]).strip()
        if oid not in orders:
            orders[oid] = []
        orders[oid].append(row)

    print(f"\nPending Orders ({len(orders)}):\n")
    order_list = list(orders.items())
    for i, (oid, items) in enumerate(order_list, 1):
        resolved = [_resolve_item(it) for it in items]
        vendor = _extract_vendor(oid, resolved)
        total = sum(it["allocation"] for it in resolved)
        print(f"  {i}. {oid} — {vendor} — {len(items)} items — ${total:.2f}")

    if args.order:
        selected_oid = args.order
    else:
        choice = input("\nSelect order (number or ID): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(order_list):
            selected_oid = order_list[int(choice) - 1][0]
        else:
            selected_oid = choice

    if selected_oid not in orders:
        print(f"Order '{selected_oid}' not found")
        sys.exit(1)

    order_items = orders[selected_oid]
    resolved_order_items = [_resolve_item(it) for it in order_items]
    vendor = _extract_vendor(selected_oid, resolved_order_items)

    print(f"\n{'='*60}")
    print(f"Purchase Request: {selected_oid}")
    print(f"Vendor: {vendor}")
    print(f"{'='*60}")
    print(f"\n{'Item':<35} {'Qty':<5} {'Allocation':<12}")
    print("-" * 55)
    total = 0.0
    for it in resolved_order_items:
        name = it["name"][:34]
        qty_str = str(int(it["qty"])) if it["qty"].is_integer() else f"{it['qty']:.1f}"
        alloc = it["allocation"]
        total += alloc
        print(f"  {name:<33} {qty_str:<5} ${alloc:.2f}")
    print(f"\n  Total: ${total:.2f}")

    confirm = input("\nPrepare this order and verify its vendor cart? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Cancelled.")
        sys.exit(0)

    # Run cart preparation and Engage automation with the selected order
    py_exe = get_python_executable()
    cmd = [py_exe, os.path.join(SCRIPT_DIR, "automation_purchase.py"), "--order", selected_oid, "--excel-path", get_xlsx_path(), "--cart-source", getattr(args, "cart_source", "automated")]
    if getattr(args, "no_review", False):
        cmd.append("--no-review")
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


# ============================================================
# COMMAND: price-check
# ============================================================
def cmd_price_check(args):
    """Check current prices vs allocation, generate Amazon cart."""
    import re
    import time
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    df = load_xlsx()
    bill_title = select_bill(df, args.bill)
    items = df[df["Bill Title"].astype(str).str.strip() == bill_title]

    print(f"\n💰 Price Check: {bill_title} ({len(items)} items)\n")

    # Setup Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(20)

    results = []
    total_allocated = 0
    total_current = 0
    total_overrun = 0

    print(f"{'Item':<30} {'Allocated':<12} {'Current':<12} {'Delta'}")
    print("-" * 70)

    for _, row in items.iterrows():
        item_name = str(row.get("Item Name", "")).strip()
        url = str(row.get("Link", "")).strip()
        try:
            allocated = float(str(row.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
        except (ValueError, TypeError):
            allocated = 0

        qty = 1
        try:
            qty = int(float(str(row.get("Quantity", 1)) or 1))
        except (ValueError, TypeError):
            pass

        current_price = None
        if url and url.startswith("http"):
            try:
                driver.get(url)
            except Exception:
                pass
            time.sleep(3)

            # Scrape price
            price_text = price_scraper.scrape_price_from_driver(driver)
            current_price = price_scraper.parse_price(price_text)

        total_allocated += allocated * qty
        delta_str = "—"
        if current_price is not None:
            delta = current_price - allocated
            total_current += current_price * qty
            total_overrun += max(0, delta * qty)
            if delta > 0:
                delta_str = f"\033[91m+${delta:.2f}\033[0m"  # Red
            elif delta < 0:
                delta_str = f"\033[92m-${abs(delta):.2f}\033[0m"  # Green
            else:
                delta_str = f"\033[92m$0.00\033[0m"
            current_str = f"${current_price:.2f}"
        else:
            current_str = "—"
            total_current += allocated * qty

        print(f"  {item_name[:28]:<28} ${allocated:<10.2f} {current_str:<12} {delta_str}")

        results.append({
            "name": item_name,
            "url": url,
            "allocated": allocated,
            "current": current_price,
            "qty": qty,
        })

    driver.quit()

    print(f"\n{'='*70}")
    print(f"  Total Allocated: ${total_allocated:.2f}")
    print(f"  Total Current:   ${total_current:.2f}")
    if total_overrun > 0:
        print(f"  \033[91mTotal Overrun:   +${total_overrun:.2f}\033[0m")
    else:
        print(f"  \033[92mNo overruns\033[0m")

    # Generate Amazon cart link for all Amazon items
    amazon_items = []
    for r in results:
        asin = price_scraper.extract_amazon_asin(str(r.get("url", "")))
        if asin:
            amazon_items.append((asin, r["qty"]))

    if amazon_items:
        params = [f"ASIN.{i}={asin}&Quantity.{i}={qty}" for i, (asin, qty) in enumerate(amazon_items, 1)]
        cart_url = "https://www.amazon.com/gp/aws/cart/add.html?" + "&".join(params)
        print(f"\n🛒 1-Click Amazon Multi-Item Cart ({len(amazon_items)} items):")
        print(f"   {cart_url}")
        
        open_cart = input("\nOpen Amazon Cart in browser now? (Y/n): ").strip().lower()
        if open_cart in ("", "y", "yes"):
            import webbrowser
            try:
                webbrowser.open(cart_url)
                print("   ✅ Opened Amazon Cart in default browser.")
            except Exception as e:
                print(f"   ⚠️ Could not launch browser: {e}")

    non_amazon_count = len(results) - len(amazon_items)
    if non_amazon_count > 0:
        print(f"\nℹ️ Non-Amazon Vendor Items Detected ({non_amazon_count} item(s)):")
        print("   Please create a shopping cart directly on the vendor website and take a cart screenshot before submitting your purchase request.")


# ============================================================
# MAIN
# ============================================================
def cmd_doctor(args):
    """Run diagnostic health check on FY27_Bills_Budget.xlsx."""
    import spreadsheet_utils
    target_xlsx = get_xlsx_path()
    print(f"\n🩺 Running MRG Finance Spreadsheet Diagnostic Doctor...")
    print(f"   Target file: {target_xlsx}\n")
    results = spreadsheet_utils.validate_budget_spreadsheet(target_xlsx)
    print("-" * 75)
    print(f"Summary: {results['summary']}")
    print("-" * 75)
    if results["errors"]:
        print(f"\n❌ ERRORS ({len(results['errors'])}):")
        for err in results["errors"]:
            print(f"  • {err}")
    if results["warnings"]:
        print(f"\n⚠️ WARNINGS ({len(results['warnings'])}):")
        for w in results["warnings"]:
            print(f"  • {w}")
    if not results["errors"] and not results["warnings"]:
        print("\n🎉 Spreadsheet is 100% healthy and ready for automation!")
    print()


def cmd_report(args):
    """Generate Budget vs Quoted Full Detail Excel and CSV comparison report for an order."""
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import order_excel_builder
    order_id = getattr(args, "order", None)
    target_xlsx = get_xlsx_path()

    if not order_id:
        # Prompt interactively if order ID not specified
        import pandas as pd
        import spreadsheet_utils
        if not os.path.exists(target_xlsx):
            print(f"❌ Spreadsheet not found at {target_xlsx}")
            return
        try:
            ef = pd.ExcelFile(target_xlsx)
            df_orders = spreadsheet_utils.read_sheet_robust(ef, ["Ordering", "Orders", "OrderT"])
            oid_col = next((c for c in df_orders.columns if "order" in str(c).lower()), "Order ID")
            order_ids = list(dict.fromkeys(str(r.get(oid_col, "")).strip() for _, r in df_orders.iterrows() if str(r.get(oid_col, "")).strip() and not str(r.get(oid_col, "")).strip().startswith("#")))

            if not order_ids:
                print("❌ No valid orders found in Ordering sheet.")
                return

            print("\n📋 Available Orders:")
            for idx, oid in enumerate(order_ids, 1):
                print(f"  {idx}. {oid}")
            try:
                choice = input(f"\nSelect order [1-{len(order_ids)}]: ").strip()
                order_id = order_ids[int(choice) - 1]
            except Exception:
                order_id = order_ids[0]
        except Exception as e:
            print(f"❌ Could not load order list: {e}")
            return

    sys.argv = ["order_excel_builder.py", "--order", order_id, "--excel-path", target_xlsx]
    order_excel_builder.main()


def main():
    parser = argparse.ArgumentParser(
        description="MRG Finance CLI — bill requests, purchases, price checking, and report generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mrg-finance report --order 260811_amazon_awu335
  mrg-finance screenshots --fresh --bill "FY27 Budget"
  mrg-finance bill-request --fresh
  mrg-finance purchase --fresh
  mrg-finance price-check --bill "FY27 Budget" --cart
  mrg-finance doctor --fresh
        """
    )
    sub = parser.add_subparsers(dest="command")

    # report
    p_rep = sub.add_parser("report", help="Generate Budget vs Quoted Full Detail Excel/CSV comparison report")
    p_rep.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_rep.add_argument("--order", "-o", help="Order ID (skips interactive selection)")

    # screenshots
    p_ss = sub.add_parser("screenshots", help="Scrape prices + take screenshots")
    p_ss.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_ss.add_argument("--bill", "-b", help="Bill title (skips interactive selection)")
    p_ss.add_argument("--interactive", action="store_true", help="Show Chrome and pause for CAPTCHA solving")
    p_ss.add_argument("--no-review", action="store_true", help=argparse.SUPPRESS)

    # bill-request
    p_br = sub.add_parser("bill-request", help="Submit bill to CampusLabs Engage")
    p_br.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_br.add_argument("--bill", "-b", help="Bill title (skips interactive selection)")
    p_br.add_argument("--no-review", action="store_true", help=argparse.SUPPRESS)

    # purchase
    p_pr = sub.add_parser("purchase", help="Submit purchase requests to Engage")
    p_pr.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_pr.add_argument("--order", "-o", help="Order ID (skips interactive selection)")
    p_pr.add_argument("--no-review", action="store_true", help=argparse.SUPPRESS)
    p_pr.add_argument("--cart-source", choices=("automated", "personal"), default="automated",
                      help="Build automatically or sign into your personal account and share the real cart")

    # price-check
    p_pc = sub.add_parser("price-check", help="Check current prices vs allocation")
    p_pc.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_pc.add_argument("--bill", "-b", help="Bill title (skips interactive selection)")
    p_pc.add_argument("--cart", "-c", action="store_true", help="Generate Amazon cart link")

    # doctor
    p_doc = sub.add_parser("doctor", help="Run diagnostic health check on FY27_Bills_Budget.xlsx")
    p_doc.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Fresh sync if requested
    if getattr(args, "fresh", False):
        fresh_sync()

    # Dispatch
    commands = {
        "report": cmd_report,
        "screenshots": cmd_screenshots,
        "bill-request": cmd_bill_request,
        "purchase": cmd_purchase,
        "price-check": cmd_price_check,
        "doctor": cmd_doctor,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
