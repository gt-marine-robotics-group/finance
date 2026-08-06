"""
screenshot_worker.py - Background thread that takes headless Chrome screenshots of item URLs.

Queue-based: add URLs, worker processes them one at a time.
Screenshots saved as: screenshots/<bill_title>/<item_name>.png
After capture, pushes to SharePoint via rclone so OneDrive-synced laptops get them.
"""

import os
import re
import time
import subprocess
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
    "onedrive:Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/screenshots",
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

    # Amazon-priority selectors
    amazon_selectors = [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#sns-base-price",
        "#newBuyBoxPrice",
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


def _rclone_push_screenshot(bill_title: str, filepath: str):
    """Push a single screenshot to SharePoint via rclone."""
    safe_bill = _safe_dirname(bill_title) if bill_title else "_backlog"
    remote_path = f"{RCLONE_SCREENSHOTS_REMOTE}/{safe_bill}/"
    try:
        result = subprocess.run(
            ["rclone", "copy", filepath, remote_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"[rclone] Pushed screenshot to {remote_path}")
        else:
            print(f"[rclone] Push failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("[rclone] rclone not found - skipping push")
    except subprocess.TimeoutExpired:
        print("[rclone] Push timeout")


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

    driver = None
    try:
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)

        driver.get(url)
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

        with _status_lock:
            _status[item_name] = "done"

        if price:
            print(f"[screenshot] ✅ {item_name} - price: ${price:.2f}")
        else:
            print(f"[screenshot] ✅ {item_name} - no price found")

        # Push to SharePoint via rclone
        _rclone_push_screenshot(bill_title, filepath)

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
