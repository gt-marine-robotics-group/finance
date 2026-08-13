import os
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import time
import re
import json
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# === CONFIG ===
DEFAULT_XLSX = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
CSV_PATH = os.environ.get("FINANCE_XLSX_PATH", DEFAULT_XLSX)
OUTPUT_CSV = "./FY27_Bills_Budget_Updated.csv"
SHEET_NAME = "Bills"
SAVE_FOLDER = "./screenshots"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REVIEW_HTML = os.path.join(SCRIPT_DIR, "review.html")
DELAY = 5  # seconds to wait after page load
MAX_RETRIES = 2  # retry failed page loads


# === Price extraction ===
def parse_price(s: str):
    """Return float for first valid price string."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.replace("\xa0", " ").strip()

    dollar_match = re.search(r'\$\s*([\d,]+\.?\d*)', s)
    if dollar_match:
        num_str = dollar_match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    match = re.search(r'(\d{1,3}(?:[,]\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})', s)
    if match:
        num_str = match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    euro_match = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{1,2})', s)
    if euro_match:
        num_str = euro_match.group(1).replace(".", "").replace(",", ".")
        try:
            return float(num_str)
        except ValueError:
            pass

    fallback = re.search(r'(\d+\.?\d*)', s)
    if fallback:
        try:
            val = float(fallback.group(1))
            if val > 0:
                return val
        except ValueError:
            pass
    return None


def _get_text(element):
    """Get text content from an element."""
    txt = (element.text or "").strip()
    if not txt:
        txt = (element.get_attribute("innerText") or "").strip()
    if not txt:
        txt = (element.get_attribute("textContent") or "").strip()
    if not txt:
        txt = (element.get_attribute("content") or "").strip()
    return txt


def _find_price_in_json(data):
    """Recursively find price in JSON-LD schema data."""
    if isinstance(data, list):
        for item in data:
            result = _find_price_in_json(item)
            if result:
                return result
    elif isinstance(data, dict):
        if "offers" in data:
            offers = data["offers"]
            if isinstance(offers, dict) and "price" in offers:
                return str(offers["price"])
            elif isinstance(offers, list):
                for offer in offers:
                    if isinstance(offer, dict) and "price" in offer:
                        return str(offer["price"])
        if "price" in data:
            return str(data["price"])
        for val in data.values():
            if isinstance(val, (dict, list)):
                result = _find_price_in_json(val)
                if result:
                    return result
    return None


def _extract_amazon_price(driver):
    """Amazon-specific price extraction — multiple strategies."""
    # Strategy 1: Try the page source directly for twister-plus-price-data or JS-embedded price
    try:
        page_source = driver.page_source
        # Amazon embeds price in various data attributes and scripts
        # Look for "priceAmount" in the page source (from JS state)
        price_match = re.search(r'"priceAmount"\s*:\s*"?([\d.]+)"?', page_source)
        if price_match:
            return f"${price_match.group(1)}", "high"
        # Also check for "price":{"value": pattern
        price_match = re.search(r'"price"\s*:\s*\{\s*"value"\s*:\s*"?([\d.]+)"?', page_source)
        if price_match:
            return f"${price_match.group(1)}", "high"
        # Check for buyingPrice
        price_match = re.search(r'"buyingPrice"\s*:\s*"?([\d.]+)"?', page_source)
        if price_match:
            return f"${price_match.group(1)}", "high"
    except Exception:
        pass

    # Strategy 2: CSS selectors for visible price elements
    selectors = [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#corePrice_desktop .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#sns-base-price",
        "#newBuyBoxPrice",
        "#price_inside_buybox",
        "#buyNewSection .a-price .a-offscreen",
        "#price .a-offscreen",
        "span.a-price .a-offscreen",
        "#tp_price_block_total_price_ww .a-offscreen",
    ]
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                text = _get_text(el)
                if text and re.search(r'\$[\d,]+\.?\d*', text):
                    return text, "high"
        except Exception:
            continue

    try:
        whole_els = driver.find_elements(By.CSS_SELECTOR, ".a-price-whole")
        frac_els = driver.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
        if whole_els and frac_els:
            w = whole_els[0].text.replace(",", "").replace(".", "").strip()
            f = frac_els[0].text.strip()
            if w.isdigit() and f.isdigit():
                return f"${w}.{f}", "high"
    except Exception:
        pass
    return "", "low"


def _extract_schema_price(driver):
    """Extract price from JSON-LD or microdata."""
    try:
        scripts = driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
        for script in scripts:
            try:
                data = json.loads(script.get_attribute("innerHTML"))
                price = _find_price_in_json(data)
                if price:
                    return price
            except (json.JSONDecodeError, Exception):
                continue
    except Exception:
        pass
    try:
        price_el = driver.find_element(By.CSS_SELECTOR, '[itemprop="price"]')
        content = price_el.get_attribute("content") or price_el.text
        if content and re.search(r'\d', content):
            return content.strip()
    except Exception:
        pass
    return None


def _extract_meta_price(driver):
    """Extract from meta tags."""
    for sel in ['meta[property="og:price:amount"]', 'meta[property="product:price:amount"]',
                'meta[name="price"]', 'meta[property="price"]']:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            content = el.get_attribute("content")
            if content and re.search(r'\d', content):
                return content.strip()
        except Exception:
            continue
    return None


def _extract_generic_css_price(driver):
    """Try common CSS selectors for price elements."""
    selectors = [
        '[class*="price"]:not([class*="compare"]):not([class*="was"]):not([class*="old"]):not([class*="shipping"])',
        '[id*="price"]:not([id*="compare"]):not([id*="was"])',
        '[data-price]', '[itemprop*="price"]', '[data-testid*="price"]',
        '[class*="ProductPrice"]', '[class*="product-price"]',
        '[class*="sale-price"]', '[class*="current-price"]',
    ]
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for el in elems:
            text = _get_text(el)
            if not text:
                continue
            if re.search(r'\$\s*\d', text) or re.search(r'\d+\.\d{2}', text):
                if "–" in text or " - " in text:
                    continue
                return text
    return None


def _extract_regex_price(driver):
    """Last resort: regex the page source."""
    try:
        html = driver.page_source
        matches = re.findall(r'\$\s*(\d{1,6}(?:,\d{3})*\.\d{2})', html)
        for m in matches:
            val = float(m.replace(",", ""))
            if val > 0:
                return f"${m}"
    except Exception:
        pass
    return None


def extract_price_from_page(driver, url):
    """Multi-strategy price extraction. Returns (price_text, confidence)."""
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
    except Exception:
        pass

    if "amazon" in domain:
        return _extract_amazon_price(driver)

    price_text = _extract_schema_price(driver)
    if price_text:
        return price_text, "high"

    price_text = _extract_meta_price(driver)
    if price_text:
        return price_text, "high"

    price_text = _extract_generic_css_price(driver)
    if price_text:
        return price_text, "medium"

    price_text = _extract_regex_price(driver)
    if price_text:
        return price_text, "low"

    return "", "none"


def dismiss_popups(driver):
    """Try to dismiss cookie/popup overlays."""
    for sel in ['[id*="cookie"] button', '[class*="cookie"] button',
                '[id*="consent"] button', 'button[class*="accept"]',
                'button[class*="dismiss"]', 'button[aria-label*="close"]']:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in buttons[:2]:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.3)
                    break
        except Exception:
            continue


def wait_for_page_ready(driver, timeout=15):
    """Wait for the page to fully load."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass
    time.sleep(2)  # Extra settle for JS content


def _find_file_in_dir(dir_path, item_name):
    """Find a screenshot file in dir_path using exact, sanitized, space-normalized, or case-insensitive matching."""
    if not dir_path or not os.path.isdir(dir_path):
        return None

    # Match the same filename sanitization used when screenshots are saved.
    def _sanitize_for_filename(name):
        return "".join(c if c.isalnum() or c in " -_" else "_" for c in str(name or "")).strip()

    safe_name = _sanitize_for_filename(item_name) + ".png"
    exact = os.path.join(dir_path, safe_name)
    if os.path.exists(exact):
        return exact

    # Try exact match after removing punctuation differences that often appear between the UI label and saved filename.
    alias_candidates = {
        re.sub(r'[<>:"/\\|?*]', '_', str(item_name or "")) + ".png",
        safe_name,
        re.sub(r'\s+', ' ', str(item_name or "")).strip() + ".png",
    }
    for candidate in alias_candidates:
        alt = os.path.join(dir_path, candidate)
        if os.path.exists(alt):
            return alt

    target_norm = re.sub(r'\s+', ' ', safe_name).lower()
    try:
        for f in os.listdir(dir_path):
            file_norm = re.sub(r'\s+', ' ', f).lower()
            if file_norm == target_norm:
                return os.path.join(dir_path, f)
            # Also match when punctuation differences exist between item labels and saved filenames.
            cleaned_f = "".join(c if c.isalnum() or c in " -_" else "_" for c in f).lower()
            cleaned_target = "".join(c if c.isalnum() or c in " -_" else "_" for c in safe_name).lower()
            if cleaned_f == cleaned_target:
                return os.path.join(dir_path, f)
    except Exception:
        pass
    return None


def find_screenshots_for_item(bill_title, item_name, screenshot_file=None, order_id=None):
    """Locate baseline (old) and newly scraped screenshot files for an item with flexible matching."""
    bill_dir = os.path.join("screenshots", bill_title) if bill_title else None
    order_dir = os.path.join("screenshots", order_id) if order_id else None
    old_dir = os.path.join("screenshots", bill_title, "old") if bill_title else None
    root_old_dir = os.path.join("screenshots", "old")
    root_dir = "screenshots"
    new_dir = os.path.join("screenshots", bill_title, "new") if bill_title else None
    root_new_dir = os.path.join("screenshots", "new")

    old_screenshot = None
    new_screenshot = None

    if order_dir and os.path.isdir(order_dir):
        # Purchase Order Review Mode: new_shot is in order_dir, old_shot is in bill_dir or root_dir
        new_screenshot = _find_file_in_dir(order_dir, item_name)
        for d in (bill_dir, old_dir, root_old_dir, root_dir):
            if d:
                found = _find_file_in_dir(d, item_name)
                if found and (not new_screenshot or os.path.abspath(found) != os.path.abspath(new_screenshot)):
                    old_screenshot = found
                    break
    else:
        # Standard Bill Request / Review Mode
        for d in (old_dir, root_old_dir):
            if d:
                found = _find_file_in_dir(d, item_name)
                if found:
                    old_screenshot = found
                    break

        if screenshot_file:
            cand = os.path.join("screenshots", screenshot_file)
            if os.path.exists(cand):
                new_screenshot = cand

        if not new_screenshot:
            for d in (bill_dir, root_dir, new_dir, root_new_dir):
                if d:
                    found = _find_file_in_dir(d, item_name)
                    if found:
                        new_screenshot = found
                        break

    if old_screenshot and new_screenshot and os.path.abspath(old_screenshot) == os.path.abspath(new_screenshot):
        old_screenshot = None

    return old_screenshot, new_screenshot


def resolve_review_screenshot_paths(item_name, source_bill_title="", order_id=""):
    """Resolve the original source-bill screenshot and the current order screenshot for a review item."""
    source_bill_title = (source_bill_title or "").strip()
    old_shot, new_shot = find_screenshots_for_item(source_bill_title, item_name, order_id=order_id)
    if not old_shot and source_bill_title:
        bill_dir = os.path.join("screenshots", source_bill_title)
        old_shot = _find_file_in_dir(bill_dir, item_name)
    return old_shot, new_shot


def calculate_review_status(csv_cost, parsed_price, screenshot_file=None):
    """Return review status based on actual price delta, not screenshot presence alone."""
    if parsed_price is None:
        return "failed" if screenshot_file else "error"

    try:
        csv_value = float(str(csv_cost).replace("$", "").replace(",", "").strip())
    except Exception:
        return "ok" if parsed_price > 0 else "failed"

    if abs(parsed_price - csv_value) > 0.01:
        return "needs_review"
    return "ok"


def generate_review_html(data, bill_title, output_path):
    """Generate an interactive HTML review page with side-by-side screenshot comparison and fast navigation."""
    ok_count = sum(1 for d in data if d["status"] == "ok")
    review_count = sum(1 for d in data if d["status"] == "needs_review")
    fail_count = sum(1 for d in data if d["status"] in ("failed", "error"))
    skip_count = sum(1 for d in data if d["status"] == "skipped")

    import json as json_mod
    import base64

    def _image_to_data_uri(filepath):
        if not filepath or not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            ext = os.path.splitext(filepath)[1].lower().replace(".", "")
            mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ("jpg", "jpeg") else "image/png")
            return f"data:{mime};base64,{encoded}"
        except Exception:
            return None

    # Embed Base64 image data URIs directly into items data
    for item in data:
        old_path = item.get("old_screenshot")
        new_path = item.get("new_screenshot") or item.get("screenshot")
        if new_path and not os.path.exists(new_path) and os.path.exists(os.path.join("screenshots", os.path.basename(new_path))):
            new_path = os.path.join("screenshots", os.path.basename(new_path))
        item["old_screenshot_data"] = _image_to_data_uri(old_path)
        item["new_screenshot_data"] = _image_to_data_uri(new_path)

    items_json = json_mod.dumps(data)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Side-by-Side Review — {bill_title}</title>
    <style>
        :root {{
            --bg-main: #f8fafc;
            --bg-panel: #ffffff;
            --bg-card: #ffffff;
            --border-color: #e2e8f0;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --accent-blue: #2563eb;
            --accent-green: #16a34a;
            --accent-orange: #ca8a04;
            --accent-red: #dc2626;
            --radius: 8px;
            --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.08);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.1);
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: var(--bg-main); color: var(--text-main); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}

        /* Top Header */
        header {{
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            box-shadow: var(--shadow-sm);
        }}
        .header-title {{ font-size: 1.15rem; font-weight: 700; display: flex; align-items: center; gap: 10px; color: var(--text-main); }}
        .header-subtitle {{ font-size: 0.85rem; color: var(--text-muted); font-weight: 400; }}
        .header-actions {{ display: flex; align-items: center; gap: 10px; }}

        .btn {{
            background: #ffffff;
            color: var(--text-main);
            border: 1px solid #cbd5e1;
            padding: 8px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.85rem;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
        }}
        .btn:hover {{ background: #f1f5f9; }}
        .btn-primary {{ background: #2563eb; color: #ffffff; border-color: #1d4ed8; }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        .btn-success {{ background: #16a34a; color: #ffffff; border-color: #15803d; }}
        .btn-success:hover {{ background: #15803d; }}
        .btn-active {{ background: #2563eb; color: #ffffff; font-weight: 700; }}

        /* App Container */
        .app-body {{ display: flex; flex: 1; overflow: hidden; }}

        /* Sidebar Navigation Drawer */
        .sidebar {{
            width: 320px;
            background: var(--bg-panel);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }}
        .sidebar-tabs {{
            display: flex;
            border-bottom: 1px solid var(--border-color);
            background: #f8fafc;
        }}
        .tab-btn {{
            flex: 1;
            padding: 10px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            border-bottom: 2px solid transparent;
        }}
        .tab-btn.active {{ color: var(--accent-blue); border-bottom-color: var(--accent-blue); background: var(--bg-panel); font-weight: 700; }}

        .sidebar-list {{ overflow-y: auto; flex: 1; padding: 8px; }}
        .sidebar-item {{
            padding: 10px 12px;
            border-radius: 8px;
            margin-bottom: 6px;
            cursor: pointer;
            border: 1px solid transparent;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: background 0.15s ease;
            color: var(--text-main);
        }}
        .sidebar-item:hover {{ background: #f1f5f9; }}
        .sidebar-item.active {{ background: #2563eb; color: #ffffff; font-weight: 600; }}

        .item-info {{ display: flex; flex-direction: column; gap: 2px; max-width: 200px; }}
        .item-name {{ font-size: 0.85rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .item-sub {{ font-size: 0.75rem; opacity: 0.85; }}

        .badge {{
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .badge-ok {{ background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }}
        .badge-review {{ background: #fef9c3; color: #854d0e; border: 1px solid #fef08a; }}
        .badge-failed {{ background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }}

        /* Main Workspace */
        .workspace {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; background: var(--bg-main); }}

        /* Fast Navigation Bar */
        .nav-bar {{
            background: var(--bg-panel);
            padding: 12px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: var(--shadow-sm);
        }}
        .nav-info {{ display: flex; align-items: center; gap: 15px; }}
        .item-title-large {{ font-size: 1.2rem; font-weight: 700; color: var(--text-main); }}

        /* Side-by-Side Comparison Container */
        .comparison-view {{
            flex: 1;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            overflow-y: auto;
        }}

        .price-panel {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 14px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
            box-shadow: var(--shadow-sm);
        }}
        .price-metric {{ display: flex; flex-direction: column; gap: 2px; }}
        .metric-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }}
        .metric-value {{ font-size: 1.2rem; font-weight: 700; color: var(--text-main); }}

        .price-input-box {{
            background: #ffffff;
            border: 2px solid var(--accent-blue);
            color: var(--text-main);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 1.1rem;
            font-weight: 700;
            width: 120px;
        }}

        /* Side by Side Split Grid */
        .split-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            flex: 1;
            min-height: 450px;
        }}

        .shot-card {{
            background: var(--bg-panel);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
        }}
        .shot-header {{
            background: #f8fafc;
            color: var(--text-main);
            padding: 10px 14px;
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border-color);
        }}
        .shot-body {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f1f5f9;
            padding: 12px;
            position: relative;
        }}
        .shot-body img {{
            max-width: 100%;
            max-height: 580px;
            object-fit: contain;
            border-radius: 6px;
            cursor: zoom-in;
            box-shadow: var(--shadow-md);
            border: 1px solid #cbd5e1;
        }}
        .placeholder-box {{ color: var(--text-muted); font-size: 0.9rem; font-style: italic; text-align: center; }}

        /* Cards List View Mode */
        .cards-list-view {{ display: none; padding: 20px; overflow-y: auto; gap: 20px; flex-direction: column; }}
        .cards-list-view.active {{ display: flex; }}
        .card-row {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            box-shadow: var(--shadow-sm);
        }}
        .card-row-shots {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; height: 260px; }}
        .card-row-shots img {{ width: 100%; height: 100%; object-fit: contain; background: #f1f5f9; border-radius: 4px; border: 1px solid #cbd5e1; }}

        /* Footer Hints */
        .footer-hints {{
            background: var(--bg-panel);
            border-top: 1px solid var(--border-color);
            padding: 10px 20px;
            font-size: 0.78rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }}
        kbd {{ background: #e2e8f0; color: #1e293b; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.7rem; border: 1px solid #cbd5e1; }}

        /* Toast */
        .toast {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #0284c7;
            color: #fff;
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 600;
            box-shadow: 0 8px 20px rgba(0,0,0,0.4);
            display: none;
            z-index: 1000;
        }}
        .toast.show {{ display: block; }}

        /* Lightbox Modal */
        .lightbox {{
            position: fixed;
            top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.9);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 2000;
        }}
        .lightbox.show {{ display: flex; }}
        .lightbox img {{ max-width: 95vw; max-height: 95vh; object-fit: contain; border-radius: 8px; }}
    </style>
</head>
<body>
    <header>
        <div>
            <div class="header-title">📋 Side-by-Side Price & Screenshot Review</div>
            <div class="header-subtitle">Bill: {bill_title} | Review & Edit Prices</div>
        </div>
        <div class="header-actions">
            <button class="btn" id="toggle-view-btn" onclick="toggleViewMode()">☰ List View</button>
            <button class="btn btn-success" onclick="acceptAllCsv()">Accept All Spreadsheet Prices</button>
            <button class="btn btn-primary" onclick="saveToSpreadsheet()">💾 Save to Spreadsheet</button>
        </div>
    </header>

    <div class="app-body">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-tabs">
                <button class="tab-btn active" onclick="setFilter('all')">All ({len(data)})</button>
                <button class="tab-btn" onclick="setFilter('needs_review')">⚠️ Review ({review_count})</button>
                <button class="tab-btn" onclick="setFilter('ok')">✅ OK ({ok_count})</button>
            </div>
            <div class="sidebar-list" id="sidebar-list"></div>
        </div>

        <!-- Main Workspace -->
        <div class="workspace">
            <!-- Inspector Mode -->
            <div id="inspector-container" style="display: flex; flex-direction: column; flex: 1; overflow: hidden;">
                <div class="nav-bar">
                    <div class="nav-info">
                        <span class="item-title-large" id="item-title-text">Item Name</span>
                        <span id="item-status-badge" class="badge">STATUS</span>
                        <a id="item-url-link" href="#" target="_blank" class="btn" style="padding: 4px 10px; font-size: 0.75rem;">Open Link ↗</a>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span id="item-count-text" style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600;">Item 1 of {len(data)}</span>
                        <button class="btn" onclick="prevItem()">◀ Prev (←)</button>
                        <button class="btn btn-primary" onclick="nextItem()">Next (→) ▶</button>
                    </div>
                </div>

                <div class="comparison-view">
                    <!-- Price Control Panel -->
                    <div class="price-panel">
                        <div class="price-metric">
                            <span class="metric-label">Spreadsheet Price</span>
                            <span class="metric-value" id="val-csv">$0.00</span>
                        </div>
                        <div class="price-metric">
                            <span class="metric-label">Scraped Price</span>
                            <span class="metric-value" id="val-scraped" style="color: var(--accent-blue);">$0.00</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button class="btn" onclick="useSpreadsheetPriceCurrent()">Use Spreadsheet Price [1]</button>
                            <button class="btn" onclick="useScrapedPriceCurrent()">Use Scraped Price [2]</button>
                        </div>
                        <div class="price-metric" style="align-items: flex-end;">
                            <span class="metric-label">Final Price to Save</span>
                            <div style="display: flex; align-items: center; gap: 4px;">
                                <span style="font-weight: 700; font-size: 1.1rem;">$</span>
                                <input type="number" step="0.01" min="0" class="price-input-box" id="final-price-input" oninput="onPriceInputChange(this.value)" />
                            </div>
                        </div>
                    </div>

                    <!-- Side-by-Side / Single Screenshot Grid -->
                    <div class="split-grid" id="split-grid-container">
                        <div class="shot-card" id="old-shot-card">
                            <div class="shot-header">
                                <span>📜 Baseline / Old Screenshot</span>
                                <span id="old-shot-status">Ground Truth</span>
                            </div>
                            <div class="shot-body" id="old-shot-container"></div>
                        </div>
                        <div class="shot-card" id="new-shot-card">
                            <div class="shot-header">
                                <span id="new-shot-card-title">📸 New / Scraped Screenshot</span>
                                <span id="new-shot-status">Captured Verification</span>
                            </div>
                            <div class="shot-body" id="new-shot-container"></div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- List Mode Container -->
            <div class="cards-list-view" id="cards-list-container"></div>

            <div class="footer-hints">
                <span><kbd>←</kbd> / <kbd>A</kbd> Previous Item</span>
                <span><kbd>→</kbd> / <kbd>D</kbd> Next Item</span>
                <span><kbd>1</kbd> Use Spreadsheet Price</span>
                <span><kbd>2</kbd> Use Scraped Price</span>
                <span><kbd>Enter</kbd> Save & Advance</span>
            </div>
        </div>
    </div>

    <div class="lightbox" id="lightbox" onclick="closeLightbox()">
        <img id="lightbox-img" src="" alt="Full view" />
    </div>

    <div class="toast" id="toast"></div>

    <script>
        const itemsData = {items_json};
        let currentIndex = 0;
        let currentFilter = 'all';
        let isListView = false;

        function escapeHtml(str) {{
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }}

        function getFilteredIndices() {{
            return itemsData.map((item, idx) => {{
                if (currentFilter === 'all') return idx;
                if (currentFilter === 'needs_review') return item.status === 'needs_review' ? idx : -1;
                if (currentFilter === 'ok') return item.status === 'ok' ? idx : -1;
                return idx;
            }}).filter(idx => idx !== -1);
        }}

        function setFilter(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            if (event && event.target) event.target.classList.add('active');
            const filtered = getFilteredIndices();
            if (filtered.length > 0 && !filtered.includes(currentIndex)) {{
                currentIndex = filtered[0];
            }}
            renderSidebar();
            renderInspector();
            if (isListView) renderListView();
        }}

        function renderSidebar() {{
            const listEl = document.getElementById('sidebar-list');
            const filtered = getFilteredIndices();

            listEl.innerHTML = filtered.map(idx => {{
                const item = itemsData[idx];
                const activeClass = idx === currentIndex ? 'active' : '';
                const badgeClass = item.status === 'ok' ? 'badge-ok' : (item.status === 'needs_review' ? 'badge-review' : 'badge-failed');
                const badgeText = item.status === 'ok' ? 'OK' : (item.status === 'needs_review' ? 'Review' : 'Failed');

                return `
                    <div class="sidebar-item ${{activeClass}}" onclick="selectItem(${{idx}})">
                        <div class="item-info">
                            <span class="item-name">${{escapeHtml(item.item_name)}}</span>
                            <span class="item-sub">Spreadsheet: $${{item.csv_cost}} | Scraped: ${{item.scraped_price || '$0.00'}}</span>
                        </div>
                        <span class="badge ${{badgeClass}}">${{badgeText}}</span>
                    </div>
                `;
            }}).join('');
        }}

        function renderInspector() {{
            if (itemsData.length === 0) return;
            const item = itemsData[currentIndex];

            document.getElementById('item-title-text').textContent = item.item_name;
            document.getElementById('item-url-link').href = item.url || '#';
            document.getElementById('item-count-text').textContent = `Item ${{currentIndex + 1}} of ${{itemsData.length}}`;

            const badge = document.getElementById('item-status-badge');
            if (item.status === 'ok') {{
                badge.className = 'badge badge-ok';
                badge.textContent = '✅ Matched';
            }} else if (item.status === 'needs_review') {{
                badge.className = 'badge badge-review';
                badge.textContent = '⚠️ Price Mismatch';
            }} else {{
                badge.className = 'badge badge-failed';
                badge.textContent = '❌ Failed / Skipped';
            }}

            const csvVal = parseFloat(String(item.csv_cost).replace('$','').replace(',','')) || 0;
            document.getElementById('val-csv').textContent = `$${{csvVal.toFixed(2)}}`;
            document.getElementById('val-scraped').textContent = item.scraped_price ? item.scraped_price : (item.parsed_price ? `$${{item.parsed_price.toFixed(2)}}` : 'N/A');

            const curVal = item.final_price !== undefined ? item.final_price : (item.parsed_price || csvVal);
            document.getElementById('final-price-input').value = parseFloat(curVal).toFixed(2);

            // Always display 2-column side-by-side comparison layout
            const oldContainer = document.getElementById('old-shot-container');
            const newContainer = document.getElementById('new-shot-container');
            const gridEl = document.getElementById('split-grid-container');
            const oldCardEl = document.getElementById('old-shot-card');
            const newCardTitleEl = document.getElementById('new-shot-card-title');

            oldCardEl.style.display = 'flex';
            gridEl.style.gridTemplateColumns = '1fr 1fr';
            newCardTitleEl.textContent = '📸 Current Live / Scraped Screenshot';

            const oldSrc = item.old_screenshot_data || item.old_screenshot;
            if (oldSrc) {{
                oldContainer.innerHTML = `<img src="${{oldSrc}}" alt="Baseline Screenshot" onclick="openLightbox(this.src)" />`;
            }} else {{
                oldContainer.innerHTML = `<div class="placeholder-box">📷 Approved bill screenshot not available</div>`;
            }}

            const newSrc = item.new_screenshot_data || item.new_screenshot || (item.screenshot ? `screenshots/${{item.screenshot}}` : null);
            if (newSrc) {{
                newContainer.innerHTML = `<img src="${{newSrc}}" alt="New Screenshot" onclick="openLightbox(this.src)" />`;
            }} else {{
                newContainer.innerHTML = `<div class="placeholder-box">📸 Current online screenshot not captured</div>`;
            }}

            renderSidebar();
        }}

        function selectItem(idx) {{
            currentIndex = idx;
            renderInspector();
        }}

        function nextItem() {{
            const filtered = getFilteredIndices();
            const pos = filtered.indexOf(currentIndex);
            if (pos >= 0 && pos < filtered.length - 1) {{
                selectItem(filtered[pos + 1]);
            }}
        }}

        function prevItem() {{
            const filtered = getFilteredIndices();
            const pos = filtered.indexOf(currentIndex);
            if (pos > 0) {{
                selectItem(filtered[pos - 1]);
            }}
        }}

        function useSpreadsheetPriceCurrent() {{
            const item = itemsData[currentIndex];
            const val = parseFloat(String(item.csv_cost).replace('$','').replace(',','')) || 0;
            item.final_price = val;
            document.getElementById('final-price-input').value = val.toFixed(2);
            showToast(`Applied spreadsheet price: $${{val.toFixed(2)}}`);
        }}

        function useScrapedPriceCurrent() {{
            const item = itemsData[currentIndex];
            const val = item.parsed_price || 0;
            if (val > 0) {{
                item.final_price = val;
                document.getElementById('final-price-input').value = val.toFixed(2);
                showToast(`Applied scraped price: $${{val.toFixed(2)}}`);
            }}
        }}

        function onPriceInputChange(val) {{
            itemsData[currentIndex].final_price = parseFloat(val) || 0;
        }}

        function acceptAllCsv() {{
            itemsData.forEach(item => {{
                const val = parseFloat(String(item.csv_cost).replace('$','').replace(',','')) || 0;
                if (val > 0) item.final_price = val;
            }});
            renderInspector();
            showToast('Set all prices to spreadsheet values');
        }}

        function saveToSpreadsheet() {{
            const prices = itemsData.map(item => ({{
                item_name: item.item_name,
                price: item.final_price !== undefined ? item.final_price : (item.parsed_price || parseFloat(String(item.csv_cost).replace('$','').replace(',','')) || 0)
            }})).filter(p => p.price > 0);

            fetch('http://localhost:8321/save-prices', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ prices }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.error) {{
                    showToast('❌ Error: ' + data.error);
                }} else {{
                    showToast(`✅ Saved ${{data.count}} prices to spreadsheet!`);
                }}
            }})
            .catch(err => {{
                showToast('❌ Save failed. Is review_server.py running?');
            }});
        }}

        function toggleViewMode() {{
            isListView = !isListView;
            const insp = document.getElementById('inspector-container');
            const cards = document.getElementById('cards-list-container');
            const btn = document.getElementById('toggle-view-btn');

            if (isListView) {{
                insp.style.display = 'none';
                cards.style.display = 'flex';
                btn.textContent = '🔍 Inspector View';
                renderListView();
            }} else {{
                insp.style.display = 'flex';
                cards.style.display = 'none';
                btn.textContent = '☰ List View';
                renderInspector();
            }}
        }}

        function renderListView() {{
            const cardsEl = document.getElementById('cards-list-container');
            const filtered = getFilteredIndices();

            cardsEl.innerHTML = filtered.map(idx => {{
                const item = itemsData[idx];
                const oldSrc = item.old_screenshot_data || item.old_screenshot;
                const newSrc = item.new_screenshot_data || item.new_screenshot || (item.screenshot ? `screenshots/${{item.screenshot}}` : null);

                return `
                    <div class="card-row">
                        <div style="display:flex; align-items:center; justify-content:space-between;">
                            <span style="font-weight:700; font-size:1.1rem;">${{escapeHtml(item.item_name)}}</span>
                            <div>
                                <span style="margin-right:15px;">Spreadsheet: <strong>$${{item.csv_cost}}</strong></span>
                                <span>Scraped: <strong>${{item.scraped_price || 'N/A'}}</strong></span>
                            </div>
                        </div>
                        <div class="card-row-shots">
                            <div>${{oldSrc ? `<img src="${{oldSrc}}" onclick="openLightbox(this.src)" />` : '<div class="placeholder-box">No baseline image</div>'}}</div>
                            <div>${{newSrc ? `<img src="${{newSrc}}" onclick="openLightbox(this.src)" />` : '<div class="placeholder-box">No new image</div>'}}</div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function openLightbox(src) {{
            document.getElementById('lightbox-img').src = src;
            document.getElementById('lightbox').classList.add('show');
        }}

        function closeLightbox() {{
            document.getElementById('lightbox').classList.remove('show');
        }}

        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }}

        document.addEventListener('keydown', function(e) {{
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') {{
                prevItem();
            }} else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') {{
                nextItem();
            }} else if (e.key === '1') {{
                useSpreadsheetPriceCurrent();
            }} else if (e.key === '2') {{
                useScrapedPriceCurrent();
            }} else if (e.key === 'Enter') {{
                nextItem();
            }}
        }});

        renderInspector();
    </script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# === MAIN ===
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Automated price scraper & side-by-side screenshot review")
    parser.add_argument("--bill", "-b", help="Bill title to process or review")
    parser.add_argument("--review-only", "-r", action="store_true", help="Launch side-by-side review GUI directly without web scraping")
    args, _ = parser.parse_known_args()

    # === CHECK FILE NOT LOCKED ===
    if CSV_PATH.endswith(".xlsx"):
        lock_file = os.path.join(os.path.dirname(CSV_PATH), "~$" + os.path.basename(CSV_PATH))
        if os.path.exists(lock_file):
            print("⚠️  The spreadsheet appears to be open in Excel.")
            print("   Close it first so the script can read/write properly.")
            resp = input("   Continue anyway? [y/N]: ").strip().lower()
            if resp != "y":
                exit(0)

    # === LOAD SPREADSHEET ===
    if CSV_PATH.endswith(".xlsx"):
        df = pd.read_excel(CSV_PATH, sheet_name=SHEET_NAME)
    else:
        df = pd.read_csv(CSV_PATH, encoding="utf-8", on_bad_lines="skip")
    df = df.astype(object).fillna("")
    df.columns = df.columns.str.strip()

    required_cols = {"Item Name", "Link", "Cost", "Bill Title"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in CSV: {missing}")

    titles = df["Bill Title"].astype(str).str.strip().unique()
    SKIP_TITLES = ("nan", "request", "liquid", "misc")
    titles = [t for t in titles if t and not any(t.lower().startswith(s) for s in SKIP_TITLES)]

    bill_title = args.bill
    if not bill_title:
        print("\nAvailable Bill Titles:")
        for i, t in enumerate(titles, 1):
            count = (df["Bill Title"].astype(str).str.strip().str.lower() == t.lower()).sum()
            print(f"  {i}. {t} ({count} items)")
        choice = input("\nEnter Bill Title (or number): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(titles):
            bill_title = titles[int(choice) - 1]
        else:
            bill_title = choice

    mask = df["Bill Title"].astype(str).str.strip().str.lower() == bill_title.lower()
    df_filtered = df[mask].copy()

    if df_filtered.empty:
        print(f"\n⚠️ No entries for '{bill_title}'")
        exit(0)

    # === REVIEW-ONLY MODE ===
    if args.review_only:
        print(f"\n📋 Launching Review GUI for: {bill_title} (no web scraping)")
        review_data = []
        for idx, row in df_filtered.iterrows():
            item_name = str(row.get("Item Name", "")).strip()
            url = str(row.get("Link", "")).strip()
            csv_cost = str(row.get("Cost", "")).strip()

            old_shot, new_shot = find_screenshots_for_item(bill_title, item_name)
            parsed = parse_price(csv_cost)
            status = calculate_review_status(csv_cost, parsed, screenshot_file=new_shot)

            review_data.append({
                "item_name": item_name, "url": url, "csv_cost": csv_cost,
                "scraped_price": f"${parsed:.2f}" if parsed else "", "parsed_price": parsed,
                "confidence": "high", "screenshot": os.path.basename(new_shot) if new_shot else None,
                "old_screenshot": old_shot, "new_screenshot": new_shot, "status": status,
            })

        generate_review_html(review_data, bill_title, REVIEW_HTML)
        print(f"📋 Review page generated: {os.path.abspath(REVIEW_HTML)}")
        from review_server import launch_review_server_and_browser
        launch_review_server_and_browser(REVIEW_HTML)
        input("\n   Press Enter when done reviewing & saving prices on the review page → ")
        print("   ✅ Review complete. Changes saved.")
        exit(0)

    # === REGULAR SCRAPING MODE ===
    print(f"\n{'='*60}")
    print(f"📋 Will screenshot {len(df_filtered)} items for '{bill_title}':")
    print(f"{'='*60}")
    print(f"{'#':<4} {'Item Name':<45} {'Has Link'}")
    print("-" * 60)
    skip_count = 0
    for i, (_, row) in enumerate(df_filtered.iterrows()):
        name = str(row.get("Item Name", "")).strip()
        link = str(row.get("Link", "")).strip()
        if not link or link.lower() == "nan":
            print(f"{i+1:<4} {name:<45} ❌ NO LINK (will skip)")
            skip_count += 1
        else:
            print(f"{i+1:<4} {name:<45} ✅")

    will_process = len(df_filtered) - skip_count
    print(f"\n  → {will_process} items will be screenshotted, {skip_count} skipped (no link)")

    confirm = input(f"\nProceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("Cancelled.")
        exit(0)

    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1200")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_page_load_timeout(30)

    review_data = []
    processed = 0

    for idx, row in df_filtered.iterrows():
        item_name = str(row.get("Item Name", "")).strip()
        url = str(row.get("Link", "")).strip()
        csv_cost = str(row.get("Cost", "")).strip()

        if not item_name or not url or url.lower() == "nan":
            review_data.append({
                "item_name": item_name, "url": url, "csv_cost": csv_cost,
                "scraped_price": "", "parsed_price": None,
                "confidence": "skipped", "screenshot": None,
                "old_screenshot": None, "new_screenshot": None, "status": "skipped",
            })
            continue

        processed += 1
        print(f"\n🔍 [{processed}/{will_process}] {item_name}")
        scraped_text = ""
        confidence = "none"
        parsed = None
        screenshot_file = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                driver.get(url)
                wait_for_page_ready(driver)
                dismiss_popups(driver)
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if "amazon" in domain:
                    time.sleep(DELAY)
                else:
                    time.sleep(DELAY - 2)

                scraped_text, confidence = extract_price_from_page(driver, url)
                parsed = parse_price(scraped_text)

                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', item_name) + ".png"
                screenshot_path = os.path.join(SAVE_FOLDER, safe_filename)
                driver.save_screenshot(screenshot_path)
                screenshot_file = safe_filename
                print(f"  📸 Saved new screenshot")
                break

            except TimeoutException:
                if attempt < MAX_RETRIES:
                    print(f"  ⚠️ Timeout, retrying ({attempt+1}/{MAX_RETRIES})...")
                    time.sleep(2)
                else:
                    print(f"  ❌ Timed out")
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"  ⚠️ Error: {e}, retrying...")
                    time.sleep(2)
                else:
                    print(f"  ❌ Failed: {e}")

        old_shot, new_shot = find_screenshots_for_item(bill_title, item_name, screenshot_file)

        if parsed is not None and parsed > 0.0:
            status = calculate_review_status(csv_cost, parsed, screenshot_file=screenshot_file)
            if status == "needs_review":
                print(f"  💲 Scraped ${parsed:.2f} ≠ spreadsheet ${parse_price(csv_cost):.2f} — keeping spreadsheet value")
            elif status == "ok":
                print(f"  💲 ${parsed:.2f} ✓ matches spreadsheet")
            else:
                print(f"  💲 ${parsed:.2f} (confidence: {confidence})")
        else:
            print(f"  ⚠️ No price scraped (raw: '{scraped_text}')")
            status = "failed" if screenshot_file else "error"

        review_data.append({
            "item_name": item_name, "url": url, "csv_cost": csv_cost,
            "scraped_price": scraped_text, "parsed_price": parsed,
            "confidence": confidence, "screenshot": screenshot_file,
            "old_screenshot": old_shot, "new_screenshot": new_shot, "status": status,
        })

    driver.quit()

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n✅ Updated CSV: {OUTPUT_CSV}")

    generate_review_html(review_data, bill_title, REVIEW_HTML)
    print(f"📋 Review: {os.path.abspath(REVIEW_HTML)}")

    ok = sum(1 for d in review_data if d["status"] == "ok")
    needs_review = sum(1 for d in review_data if d["status"] == "needs_review")
    failed = sum(1 for d in review_data if d["status"] in ("failed", "error"))
    print(f"\n{'='*50}")
    print(f"  ✅ OK: {ok}  |  ⚠️ Review: {needs_review}  |  ❌ Failed: {failed}")
    print(f"{'='*50}")

def sync_screenshots_to_sharepoint():
    """Automatically upload local screenshots to SharePoint via rclone."""
    try:
        import subprocess
        print("☁️ Syncing screenshots up to SharePoint...")
        result = subprocess.run(
            ["rclone", "copy", "--checksum", SAVE_FOLDER, "onedrive:OPS-1 Operations/FY27 Finances/screenshots"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("  ✅ Screenshots synced to SharePoint!")
        else:
            print(f"  ⚠️ SharePoint sync notice: {result.stderr.strip()}")
    except Exception as ex:
        print(f"  ⚠️ SharePoint sync warning: {ex}")


    sync_screenshots_to_sharepoint()
    from review_server import launch_review_server_and_browser
    launch_review_server_and_browser(REVIEW_HTML)
    input("\n   Press Enter when done reviewing & saving prices on the review page → ")
    print("   ✅ Server complete. Changes saved.")

