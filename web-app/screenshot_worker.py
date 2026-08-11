"""
screenshot_worker.py - Background thread that takes headless Chrome screenshots of item URLs.

Queue-based: add URLs, worker processes them sequentially using a reusable Chromium session.
Screenshots saved as: screenshots/<bill_title>/<item_name>.png
After capture, pushes to SharePoint via Graph API.
"""

import os
import sys
import time
import threading
from queue import Queue, Empty
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Add parent directory for price_scraper import
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import price_scraper

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

# Persistent browser driver
_driver_instance = None
_driver_lock = threading.Lock()


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def _safe_dirname(name: str) -> str:
    """Sanitize a string for use as a directory name."""
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in name).strip()


# Delegate parse_price and _scrape_price to price_scraper
parse_price = price_scraper.parse_price
_scrape_price = price_scraper.scrape_price_from_driver


def _create_chrome_driver():
    """Create a new headless Chrome webdriver instance."""
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
    return driver


def _get_reusable_driver():
    """Get existing driver or initialize a new one if missing/dead."""
    global _driver_instance
    with _driver_lock:
        if _driver_instance is None:
            try:
                _driver_instance = _create_chrome_driver()
            except Exception as e:
                print(f"[screenshot worker] Failed to launch Chrome driver: {e}")
                _driver_instance = None
        return _driver_instance


def _close_driver():
    """Shutdown driver instance safely."""
    global _driver_instance
    with _driver_lock:
        if _driver_instance is not None:
            try:
                _driver_instance.quit()
            except Exception:
                pass
            _driver_instance = None


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

    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows"
    resp = _requests.get(rows_url, headers=headers, timeout=10)
    if resp.status_code != 200:
        return

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
            updated = list(vals)
            changed = False

            if price and cost_idx is not None and not str(vals[cost_idx]).strip():
                updated[cost_idx] = price
                changed = True

            if vendor and vendor_idx is not None and not str(vals[vendor_idx]).strip():
                updated[vendor_idx] = price_scraper.normalize_vendor(vendor)
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

    try:
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
    except Exception as e:
        print(f"[screenshot] ⚠️ SharePoint upload exception: {e}")


def _cleanup_old_screenshots():
    """Delete oldest screenshots if total storage exceeds MAX_STORAGE_MB."""
    total_bytes = 0
    all_files = []

    for root, dirs, files in os.walk(SCREENSHOT_DIR):
        for f in files:
            fp = os.path.join(root, f)
            try:
                stat = os.stat(fp)
                total_bytes += stat.st_size
                all_files.append((fp, stat.st_mtime))
            except OSError:
                pass

    total_mb = total_bytes / (1024 * 1024)
    if total_mb <= MAX_STORAGE_MB:
        return

    all_files.sort(key=lambda x: x[1])

    while total_mb > MAX_STORAGE_MB * 0.8 and all_files:
        fp, _ = all_files.pop(0)
        try:
            size = os.path.getsize(fp)
            os.remove(fp)
            total_mb -= size / (1024 * 1024)
            print(f"[cleanup] Deleted old screenshot: {fp}")
        except OSError:
            pass

    for root, dirs, files in os.walk(SCREENSHOT_DIR, topdown=False):
        if root != SCREENSHOT_DIR and not os.listdir(root):
            try:
                os.rmdir(root)
            except OSError:
                pass


def _process_job(job: dict):
    """Take a screenshot and scrape price for one item using reusable browser session."""
    item_name = job["item_name"]
    url = job["url"]
    bill_title = job.get("bill_title", "")

    with _status_lock:
        _status[item_name] = "processing"

    driver = _get_reusable_driver()
    if not driver:
        with _status_lock:
            _status[item_name] = "error"
        return None

    try:
        try:
            driver.get(url)
        except Exception as load_err:
            print(f"[screenshot worker] Page load warning for {item_name}: {load_err}")

        time.sleep(DELAY)

        safe_bill = _safe_dirname(bill_title) if bill_title else "_backlog"
        safe_name = _safe_filename(item_name)
        bill_dir = os.path.join(SCREENSHOT_DIR, safe_bill)
        os.makedirs(bill_dir, exist_ok=True)
        filepath = os.path.join(bill_dir, f"{safe_name}.png")
        driver.save_screenshot(filepath)

        price_text = price_scraper.scrape_price_from_driver(driver)
        price = price_scraper.parse_price(price_text)
        vendor = price_scraper.detect_vendor_from_url(url)

        with _status_lock:
            _status[item_name] = "done"

        if price:
            print(f"[screenshot] ✅ {item_name} - price: ${price:.2f}")
        else:
            print(f"[screenshot] ✅ {item_name} - no price found")

        if price or vendor:
            _autofill_queue_item(item_name, price, vendor)

        _upload_screenshot_to_sharepoint(bill_title, filepath)
        _cleanup_old_screenshots()

        return {"item_name": item_name, "price": price, "screenshot": filepath}

    except Exception as e:
        print(f"[screenshot] ❌ {item_name} failed: {e}")
        # Close driver so next job recreates a fresh session if browser crashed
        _close_driver()
        with _status_lock:
            _status[item_name] = "error"
        return None


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
            print(f"[screenshot worker] Loop Error: {e}")
    _close_driver()


def start_worker():
    """Start the background screenshot worker thread."""
    global _worker_thread, _running
    if _worker_thread and _worker_thread.is_alive():
        return

    _running = True
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()
    print("[screenshot worker] Started (reusable Chromium session)")


def stop_worker():
    """Stop the worker thread."""
    global _running
    _running = False
    _close_driver()


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
    """Get the screenshot file path if it exists."""
    safe_name = _safe_filename(item_name)

    if bill_title:
        safe_bill = _safe_dirname(bill_title)
        filepath = os.path.join(SCREENSHOT_DIR, safe_bill, f"{safe_name}.png")
        if os.path.exists(filepath):
            return filepath

    filepath = os.path.join(SCREENSHOT_DIR, "_backlog", f"{safe_name}.png")
    if os.path.exists(filepath):
        return filepath

    if os.path.exists(SCREENSHOT_DIR):
        for subdir in os.listdir(SCREENSHOT_DIR):
            filepath = os.path.join(SCREENSHOT_DIR, subdir, f"{safe_name}.png")
            if os.path.exists(filepath):
                return filepath

    return None


def has_screenshot(item_name: str, bill_title: str = "") -> bool:
    """Check if a screenshot exists for an item."""
    return get_screenshot_path(item_name, bill_title) is not None
