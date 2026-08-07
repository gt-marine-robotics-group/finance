"""
screenshot_worker.py - Background thread that takes headless Chrome screenshots of item URLs.

Queue-based: add URLs, worker processes them one at a time.
Screenshots saved as: screenshots/<bill_title>/<item_name>.png
After capture, pushes to SharePoint via rclone so OneDrive-synced laptops get them.
"""

import os
import re
import time
import threading
from queue import Queue, Empty
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
DELAY = 5  # seconds to wait after page load

# rclone remote for screenshots on SharePoint
RCLONE_SCREENSHOTS_REMOTE = os.environ.get(
    "RCLONE_SCREENSHOTS_REMOTE",
    "onedrive:OPS-1 Operations/FY27 Finances/screenshots",
)

# Max total screenshot storage in MB (cleanup oldest when exceeded)
MAX_STORAGE_MB = int(os.environ.get("MAX_SCREENSHOT_STORAGE_MB", "500"))

# Job queue: each item is a dict with 'item_name', 'url', and 'bill_title'
_queue: Queue = Queue()
_worker_thread: threading.Thread | None = None
_running = False

# Track status of jobs
_status: dict[str, str] = {}  # item_name -> "queued" | "processing" | "done" | "error"
_status_lock = threading.Lock()


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def _safe_dirname(name: str) -> str:
    """Sanitize a string for use as a directory name."""
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in name).strip()


def parse_price(s: str) -> float | None:
    """Extract price from scraped text."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.replace("\xa0", " ").strip()

    # Try dollar sign match first
    dollar_match = re.search(r"\$\s*([\d,]+\.?\d*)", s)
    if dollar_match:
        num_str = dollar_match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    # Generic decimal number
    match = re.search(r"(\d{1,3}(?:[,]\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})", s)
    if match:
        num_str = match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    return None


def _scrape_price(driver) -> str:
    """Try to find a price on the current page. Returns raw text or empty string."""

    def first_nonempty_text(element):
        txt = (element.text or "").strip()
        if not txt:
            txt = (element.get_attribute("innerText") or "").strip()
        if not txt:
            txt = (element.get_attribute("content") or "").strip()
        return txt

    # Strategy 1: Page source regex for unit price (most reliable for Amazon)
    try:
        page_source = driver.page_source
        # Amazon JS-embedded prices (per-unit, not total)
        for pattern in [
            r'"priceAmount"\s*:\s*"?([\d.]+)"?',
            r'"price"\s*:\s*\{\s*"value"\s*:\s*"?([\d.]+)"?',
            r'"buyingPrice"\s*:\s*"?([\d.]+)"?',
        ]:
            match = re.search(pattern, page_source)
            if match:
                return f"${match.group(1)}"
    except Exception:
        pass

    # Strategy 2: JSON-LD schema price
    try:
        from selenium.webdriver.common.by import By as _By
        scripts = driver.find_elements(_By.CSS_SELECTOR, 'script[type="application/ld+json"]')
        for script in scripts:
            try:
                import json
                data = json.loads(script.get_attribute("innerHTML"))
                if isinstance(data, list):
                    data = data[0] if data else {}
                offers = data.get("offers", {})
                if isinstance(offers, dict) and "price" in offers:
                    return f"${offers['price']}"
                if isinstance(offers, list):
                    for offer in offers:
                        if isinstance(offer, dict) and "price" in offer:
                            return f"${offer['price']}"
                if "price" in data:
                    return f"${data['price']}"
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 3: Amazon-priority CSS selectors
    amazon_selectors = [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#corePrice_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#sns-base-price",
        "#newBuyBoxPrice",
        "#price_inside_buybox",
        "#buyNewSection .a-price .a-offscreen",
        "span.a-price .a-offscreen",
        ".a-price .a-offscreen",
    ]

    for sel in amazon_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                text = first_nonempty_text(el)
                if text and re.search(r"\d", text):
                    return text
        except Exception:
            continue

    # Amazon whole + fraction
    try:
        whole = driver.find_elements(By.CSS_SELECTOR, ".a-price-whole")
        frac = driver.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
        if whole and frac:
            w = whole[0].text.replace(",", "").strip().rstrip(".")
            f = frac[0].text.strip()
            if w.isdigit() and f.isdigit():
                return f"{w}.{f}"
    except Exception:
        pass

    # Generic fallback selectors
    generic_selectors = [
        '[class*="price"]',
        '[id*="price"]',
        '[class*="cost"]',
        '[id*="cost"]',
        '[class*="amount"]',
        '[data-price]',
        '[itemprop*="price"]',
        '[data-testid*="price"]',
    ]

    for sel in generic_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                text = first_nonempty_text(el)
                if text and re.search(r"\d", text):
                    return text
        except Exception:
            continue

    return ""


def _autofill_queue_item(item_name: str, price: float | None, vendor: str):
    """Update a queue item's price and vendor via Graph API after scraping."""
    import configparser
    import json as _json
    import requests as _requests

    rclone_conf = os.path.expanduser("~/.config/rclone/rclone.conf")
    if not os.path.exists(rclone_conf):
        return

    config = configparser.ConfigParser()
    config.read(rclone_conf)
    if "onedrive" not in config:
        return

    try:
        token = _json.loads(config["onedrive"]["token"])
        drive_id = config["onedrive"]["drive_id"]
        access_token = token["access_token"]
    except (KeyError, _json.JSONDecodeError):
        return

    # Get file ID
    file_id = os.environ.get("_GRAPH_FILE_ID", "")
    if not file_id:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
        resp = _requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if resp.status_code == 200:
            file_id = resp.json()["id"]
            os.environ["_GRAPH_FILE_ID"] = file_id
        else:
            return

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Find the row in TestTable by item name
    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows"
    resp = _requests.get(rows_url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return

    # Get columns to know which index is Cost and Vendor
    cols_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/columns"
    cols_resp = _requests.get(cols_url, headers=headers, timeout=10)
    if cols_resp.status_code != 200:
        return

    columns = [c["name"] for c in cols_resp.json()["value"]]
    cost_idx = columns.index("Cost") if "Cost" in columns else None
    vendor_idx = columns.index("Vendor") if "Vendor" in columns else None
    name_idx = columns.index("Item Name") if "Item Name" in columns else None

    if name_idx is None:
        return

    for row in resp.json().get("value", []):
        vals = row["values"][0] if row.get("values") else []
        if name_idx < len(vals) and str(vals[name_idx]).strip() == item_name.strip():
            # Found it — update cost and vendor if empty
            updated = list(vals)
            changed = False

            if price and cost_idx is not None and not str(vals[cost_idx]).strip():
                updated[cost_idx] = price
                changed = True

            if vendor and vendor_idx is not None and not str(vals[vendor_idx]).strip():
                updated[vendor_idx] = vendor
                changed = True

            if changed:
                patch_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows/itemAt(index={row['index']})"
                patch_resp = _requests.patch(patch_url, headers=headers, json={"values": [updated]}, timeout=10)
                if patch_resp.status_code == 200:
                    print(f"[autofill] ✅ Updated {item_name}: price=${price}, vendor={vendor}")
                else:
                    print(f"[autofill] ⚠️ Update failed: {patch_resp.status_code}")
            break


def _upload_screenshot_to_sharepoint(bill_title: str, filepath: str):
    """Upload a screenshot to SharePoint via Graph API."""
    import configparser
    import json as _json
    import requests as _requests

    rclone_conf = os.path.expanduser("~/.config/rclone/rclone.conf")
    if not os.path.exists(rclone_conf):
        return

    config = configparser.ConfigParser()
    config.read(rclone_conf)
    if "onedrive" not in config:
        return

    try:
        token = _json.loads(config["onedrive"]["token"])
        drive_id = config["onedrive"]["drive_id"]
        access_token = token["access_token"]
    except (KeyError, _json.JSONDecodeError):
        return

    safe_bill = _safe_dirname(bill_title) if bill_title else "_backlog"
    filename = os.path.basename(filepath)
    remote_path = f"OPS-1 Operations/FY27 Finances/screenshots/{safe_bill}/{filename}"

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{remote_path}:/content"

    with open(filepath, "rb") as f:
        resp = _requests.put(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/png",
            },
            data=f.read(),
            timeout=30,
        )

    if resp.status_code in (200, 201):
        print(f"[screenshot] ☁️ Uploaded to SharePoint: {remote_path}")
    else:
        print(f"[screenshot] ⚠️ Upload failed: {resp.status_code}")


def _cleanup_old_screenshots():
    """Delete oldest screenshots if total storage exceeds MAX_STORAGE_MB."""
    total_bytes = 0
    all_files = []

    for root, dirs, files in os.walk(SCREENSHOT_DIR):
        for f in files:
            fp = os.path.join(root, f)
            stat = os.stat(fp)
            total_bytes += stat.st_size
            all_files.append((fp, stat.st_mtime))

    total_mb = total_bytes / (1024 * 1024)
    if total_mb <= MAX_STORAGE_MB:
        return

    # Sort by modification time (oldest first)
    all_files.sort(key=lambda x: x[1])

    # Delete oldest until under limit
    while total_mb > MAX_STORAGE_MB * 0.8 and all_files:  # Target 80% to avoid thrashing
        fp, _ = all_files.pop(0)
        try:
            size = os.path.getsize(fp)
            os.remove(fp)
            total_mb -= size / (1024 * 1024)
            print(f"[cleanup] Deleted old screenshot: {fp}")
        except OSError:
            pass

    # Remove empty directories
    for root, dirs, files in os.walk(SCREENSHOT_DIR, topdown=False):
        if root != SCREENSHOT_DIR and not os.listdir(root):
            os.rmdir(root)


def _process_job(job: dict):
    """Take a screenshot and scrape price for one item."""
    item_name = job["item_name"]
    url = job["url"]
    bill_title = job.get("bill_title", "")

    with _status_lock:
        _status[item_name] = "processing"

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"

    driver = None
    try:
        service = Service("/snap/chromium/current/usr/lib/chromium-browser/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)

        try:
            driver.get(url)
        except Exception:
            pass  # Page may partially load — still take screenshot

        time.sleep(DELAY)

        # Save screenshot in bill_title subdirectory
        safe_bill = _safe_dirname(bill_title) if bill_title else "_backlog"
        safe_name = _safe_filename(item_name)
        bill_dir = os.path.join(SCREENSHOT_DIR, safe_bill)
        os.makedirs(bill_dir, exist_ok=True)
        filepath = os.path.join(bill_dir, f"{safe_name}.png")
        driver.save_screenshot(filepath)

        # Scrape price
        price_text = _scrape_price(driver)
        price = parse_price(price_text)

        # Get page title for item name if needed
        page_title = driver.title or ""

        # Detect vendor from URL
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        vendor = ""
        if "amazon" in domain:
            vendor = "Amazon"
        elif "mcmaster" in domain:
            vendor = "McMaster-Carr"
        elif "digikey" in domain:
            vendor = "DigiKey"
        elif "mouser" in domain:
            vendor = "Mouser"
        elif "adafruit" in domain:
            vendor = "Adafruit"
        elif "sparkfun" in domain:
            vendor = "SparkFun"
        elif "pololu" in domain:
            vendor = "Pololu"

        with _status_lock:
            _status[item_name] = "done"

        if price:
            print(f"[screenshot] ✅ {item_name} - price: ${price:.2f}")
        else:
            print(f"[screenshot] ✅ {item_name} - no price found")

        # Auto-update the queue item with scraped data if available
        if price or vendor:
            _autofill_queue_item(item_name, price, vendor)

        # Push to SharePoint via Graph API
        _upload_screenshot_to_sharepoint(bill_title, filepath)

        # Cleanup if storage is getting full
        _cleanup_old_screenshots()

        return {"item_name": item_name, "price": price, "screenshot": filepath}

    except Exception as e:
        print(f"[screenshot] ❌ {item_name}: {e}")
        with _status_lock:
            _status[item_name] = "error"
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _worker_loop():
    """Main worker loop - processes jobs from queue."""
    global _running
    while _running:
        try:
            job = _queue.get(timeout=2)
            _process_job(job)
            _queue.task_done()
        except Empty:
            continue
        except Exception as e:
            print(f"[screenshot worker] Error: {e}")


def start_worker():
    """Start the background screenshot worker thread."""
    global _worker_thread, _running
    if _worker_thread and _worker_thread.is_alive():
        return

    _running = True
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()
    print("[screenshot worker] Started")


def stop_worker():
    """Stop the worker thread."""
    global _running
    _running = False


def queue_screenshot(item_name: str, url: str, bill_title: str = ""):
    """Add a screenshot job to the queue."""
    if not url or not item_name:
        return

    with _status_lock:
        _status[item_name] = "queued"

    _queue.put({"item_name": item_name, "url": url, "bill_title": bill_title})


def get_status(item_name: str) -> str:
    """Get the screenshot status for an item."""
    with _status_lock:
        return _status.get(item_name, "none")


def get_screenshot_path(item_name: str, bill_title: str = "") -> str | None:
    """Get the screenshot file path if it exists. Checks bill_title subdir first, then all subdirs."""
    safe_name = _safe_filename(item_name)

    # Check specific bill directory first
    if bill_title:
        safe_bill = _safe_dirname(bill_title)
        filepath = os.path.join(SCREENSHOT_DIR, safe_bill, f"{safe_name}.png")
        if os.path.exists(filepath):
            return filepath

    # Check _backlog
    filepath = os.path.join(SCREENSHOT_DIR, "_backlog", f"{safe_name}.png")
    if os.path.exists(filepath):
        return filepath

    # Search all subdirectories
    if os.path.exists(SCREENSHOT_DIR):
        for subdir in os.listdir(SCREENSHOT_DIR):
            filepath = os.path.join(SCREENSHOT_DIR, subdir, f"{safe_name}.png")
            if os.path.exists(filepath):
                return filepath

    return None


def has_screenshot(item_name: str, bill_title: str = "") -> bool:
    """Check if a screenshot exists for an item."""
    return get_screenshot_path(item_name, bill_title) is not None
