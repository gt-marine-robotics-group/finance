#!/usr/bin/env python3
"""
mrg.py — MRG Finance CLI Tool

Usage:
    mrg.py screenshots [--fresh] [--bill TITLE]
    mrg.py bill-request [--fresh] [--bill TITLE]
    mrg.py purchase [--fresh] [--order ORDER_ID]
    mrg.py price-check [--fresh] [--bill TITLE] [--cart]

Commands:
    screenshots      Scrape prices + take screenshots for items in a bill
    bill-request     Submit a bill to CampusLabs Engage
    purchase         Create purchase requests on Engage (grouped by vendor from OrderT)
    price-check      Check current prices vs allocation, warn on overrun

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

import price_scraper

# === Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_XLSX = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
# Fallback for Linux (SIM PC)
if not os.path.exists(os.path.dirname(DEFAULT_XLSX)):
    DEFAULT_XLSX = os.path.expanduser("~/mrg/finance/FY27_Bills_Budget.xlsx")

XLSX_PATH = os.environ.get("FINANCE_XLSX_PATH", DEFAULT_XLSX)
SHEET_NAME = "Bills"
ORDERING_SHEET = "Ordering"
SCREENSHOT_DIR = os.path.join(SCRIPT_DIR, "screenshots")
SKIP_TITLES = ("nan", "request", "liquid", "misc")


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
    xlsx_dir = os.path.dirname(XLSX_PATH)
    r1 = subprocess.run(
        ["rclone", "copy", "--checksum",
         "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
         xlsx_dir],
        capture_output=True, text=True, timeout=30
    )
    if r1.returncode == 0:
        print("  ✅ xlsx synced via rclone")
    else:
        err_brief = r1.stderr.strip().split("\n")[0] if r1.stderr else "rclone not configured"
        print(f"  ℹ️ rclone ({err_brief}). Trying Graph API fallback...")
        if download_xlsx_via_graph_api(XLSX_PATH):
            print("  ✅ xlsx synced via Microsoft Graph API!")
        else:
            print("  ⚠️ Could not sync xlsx file")

    r2 = subprocess.run(
        ["rclone", "copy", "--checksum",
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
    import pandas as pd
    import warnings
    warnings.filterwarnings('ignore')

    df = pd.read_excel(XLSX_PATH, sheet_name=SHEET_NAME).astype(object).fillna("")
    df.columns = df.columns.str.strip()

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
    import pandas as pd
    import warnings
    warnings.filterwarnings('ignore')

    df = pd.read_excel(XLSX_PATH, sheet_name=ORDERING_SHEET, header=1).astype(object).fillna("")
    df.columns = df.columns.str.strip()
    return df


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
    df = load_xlsx()
    bill_title = select_bill(df, getattr(args, "bill", None))
    print(f"\n📸 Processing screenshots for: {bill_title}")

    bill_items = df[df["Bill Title"].astype(str).str.strip().str.lower() == bill_title.lower()]
    print(f"Found {len(bill_items)} items")

    bill_dir = os.path.join(SCREENSHOT_DIR, bill_title)
    os.makedirs(bill_dir, exist_ok=True)

    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"

        service = Service("/snap/chromium/current/usr/lib/chromium-browser/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)
    except Exception as e:
        print(f"⚠️ Headless Chrome driver initialization warning: {e}")
        driver = None

    for _, row in bill_items.iterrows():
        item_name = str(row.get("Item Name", "")).strip()
        url = str(row.get("Link", "")).strip()
        if not item_name or not url or not url.startswith("http"):
            continue

        if not driver:
            continue

        print(f"  {item_name}...", end=" ", flush=True)
        try:
            driver.get(url)
        except Exception:
            pass
        import time
        time.sleep(4)

        # Screenshot
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in item_name)
        filepath = os.path.join(bill_dir, f"{safe_name}.png")

        if not getattr(args, "force", False) and os.path.exists(filepath):
            print(f"  ℹ️ {item_name}: screenshot already exists (skipping to preserve ground truth)")
            continue

        driver.save_screenshot(filepath)

        # Scrape price
        price_text = price_scraper.scrape_price_from_driver(driver)
        print(f"✅ {price_text or 'no price'}")

    if driver:
        driver.quit()
    print(f"\n✅ Screenshots saved locally to: {bill_dir}")
    upload_screenshots_to_sharepoint(bill_title, bill_dir)


def upload_screenshots_to_sharepoint(bill_title, bill_dir):
    """Auto-upload newly captured local screenshots to SharePoint/OneDrive via rclone."""
    remote_path = f"onedrive:OPS-1 Operations/FY27 Finances/screenshots/{bill_title}"
    print(f"☁️ Syncing local screenshots to SharePoint ({remote_path})...")
    try:
        r = subprocess.run(
            ["rclone", "copy", "--checksum", bill_dir, remote_path],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            print(f"  ✅ Screenshots successfully synced to SharePoint!")
        else:
            print(f"  ℹ️ rclone upload notice: {r.stderr.strip()}")
    except Exception as e:
        print(f"  ℹ️ Screenshots saved locally. (SharePoint sync skipped: {e})")


# ============================================================
# COMMAND: bill-request
# ============================================================
def cmd_bill_request(args):
    """Submit a bill to CampusLabs Engage."""
    # This wraps the existing automation.py
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "automation.py")]
    if args.fresh:
        cmd.append("--fresh")
    os.execv(sys.executable, cmd)


# ============================================================
# COMMAND: purchase
# ============================================================
def cmd_purchase(args):
    """Create purchase requests on Engage from the Ordering sheet."""
    df_order = load_ordering()

    if df_order.empty:
        print("No pending orders found in the Ordering sheet.")
        print("Use the web app to create orders first (Create New Order → select items → Submit)")
        sys.exit(0)

    oid_col = next((c for c in df_order.columns if "Order ID" in c), "Order ID")
    status_col = next((c for c in df_order.columns if c.strip().lower() == "status"), "Status")

    # Filter to rows with Order IDs but not yet purchased
    df_pending = df_order[
        (df_order[oid_col].astype(str).str.strip() != "") &
        (~df_order[oid_col].astype(str).str.strip().str.startswith("ungrouped_")) &
        (df_order[status_col].astype(str).str.strip().str.lower().isin(["", "pending purchase", "bill approved"]))
    ]

    if df_pending.empty:
        print("No pending orders found in the Ordering sheet.")
        print("Use the web app to create orders first (Create New Order → select items → Submit)")
        sys.exit(0)

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
        vendor = str(items[0].get("Vendor", "")).strip() or "Unknown"
        total = sum(float(str(it.get("Allocation", 0)).replace("$", "").replace(",", "") or 0) for it in items)
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
    vendor = str(order_items[0].get("Vendor", "")).strip()

    print(f"\n{'='*60}")
    print(f"Purchase Request: {selected_oid}")
    print(f"Vendor: {vendor}")
    print(f"{'='*60}")
    print(f"\n{'Item':<35} {'Qty':<5} {'Allocation':<12}")
    print("-" * 55)
    total = 0
    for it in order_items:
        name = str(it.get("Item Name", ""))[:34]
        qty = str(it.get("Quantity", ""))
        alloc = float(str(it.get("Allocation", 0)).replace("$", "").replace(",", "") or 0)
        total += alloc
        print(f"  {name:<33} {qty:<5} ${alloc:.2f}")
    print(f"\n  Total: ${total:.2f}")

    confirm = input(f"\nSubmit purchase request to Engage? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Cancelled.")
        sys.exit(0)

    # Run the Engage automation
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "automation_purchase.py")]
    if args.fresh:
        cmd.append("--fresh")
    os.execv(sys.executable, cmd)


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
        url_str = str(r.get("url", "")).lower()
        if "amazon" in url_str:
            asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url_str)
            if asin_match:
                amazon_items.append((asin_match.group(1), r["qty"]))

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
def main():
    parser = argparse.ArgumentParser(
        description="MRG Finance CLI — bill requests, purchases, and price checking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mrg.py screenshots --fresh --bill "FY27 Budget"
  mrg.py bill-request --fresh
  mrg.py purchase --fresh
  mrg.py price-check --bill "FY27 Budget" --cart
        """
    )
    sub = parser.add_subparsers(dest="command")

    # screenshots
    p_ss = sub.add_parser("screenshots", help="Scrape prices + take screenshots")
    p_ss.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_ss.add_argument("--bill", "-b", help="Bill title (skips interactive selection)")

    # bill-request
    p_br = sub.add_parser("bill-request", help="Submit bill to CampusLabs Engage")
    p_br.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")

    # purchase
    p_pr = sub.add_parser("purchase", help="Submit purchase requests to Engage")
    p_pr.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_pr.add_argument("--order", "-o", help="Order ID (skips interactive selection)")

    # price-check
    p_pc = sub.add_parser("price-check", help="Check current prices vs allocation")
    p_pc.add_argument("--fresh", "-f", action="store_true", help="Sync from SharePoint first")
    p_pc.add_argument("--bill", "-b", help="Bill title (skips interactive selection)")
    p_pc.add_argument("--cart", "-c", action="store_true", help="Generate Amazon cart link")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Fresh sync if requested
    if getattr(args, "fresh", False):
        fresh_sync()

    # Dispatch
    commands = {
        "screenshots": cmd_screenshots,
        "bill-request": cmd_bill_request,
        "purchase": cmd_purchase,
        "price-check": cmd_price_check,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
