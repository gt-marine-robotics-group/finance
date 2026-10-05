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
    """Try to dismiss cookie/popup overlays and Amazon continue shopping interstitials."""
    import price_scraper
    price_scraper.dismiss_popups_and_interstitials(driver)


def wait_for_page_ready(driver, timeout=15):
    """Wait for the page to fully load."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass
    time.sleep(2)  # Extra settle for JS content


def sync_screenshots_to_sharepoint():
    """Upload evidence folders, including separately marked challenge diagnostics."""
    import subprocess
    try:
        result = subprocess.run(
            ["rclone", "copy", "--ignore-checksum", "--ignore-size", "--update",
             SAVE_FOLDER, "onedrive:OPS-1 Operations/FY27 Finances/screenshots"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode:
            print(f"Screenshot sync skipped: {result.stderr.strip()}")
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Screenshot sync skipped: {error}")


def main():
    import argparse
    from pathlib import Path
    # Support running both as a package and via the CLI's script subprocess.
    project_root = os.path.dirname(SCRIPT_DIR)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from mrg_finance import spreadsheet_utils
    from mrg_finance.screenshot_capture import capture_evidence, navigate_for_evidence, BrowserChallenge
    parser = argparse.ArgumentParser(description="Capture vendor screenshots and a price audit for spreadsheet review")
    parser.add_argument("--bill", "-b")
    parser.add_argument("--excel-path", default=os.environ.get("FINANCE_XLSX_PATH"))
    parser.add_argument("--interactive", action="store_true", help="Show Chrome and pause so you can solve CAPTCHAs")
    parser.add_argument("--no-review", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.excel_path:
        from mrg_finance.cli import get_xlsx_path
        args.excel_path = get_xlsx_path()
    if args.excel_path.endswith(".xlsx"):
        df = spreadsheet_utils.read_sheet_robust(args.excel_path, ["Bills", "Bill", "Budget"])
    else:
        df = pd.read_csv(args.excel_path).fillna("")
    title_col = next((c for c in df.columns if str(c).strip().lower() in spreadsheet_utils.COLUMN_ALIASES["bill_title"]), None)
    if not title_col:
        raise ValueError("Bill Title column not found")
    titles = [t for t in df[title_col].astype(str).str.strip().unique() if t and t.lower() != "nan"]
    if not args.bill:
        for i, title in enumerate(titles, 1):
            print(f"  {i}. {title}")
        choice = input("Select bill title or number: ").strip()
        args.bill = titles[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(titles) else choice
    df = df[df[title_col].astype(str).str.strip().str.lower() == args.bill.lower()]
    if df.empty:
        raise ValueError(f"No items for bill {args.bill}")
    safe_bill = "".join(c if c.isalnum() or c in " -_" else "_" for c in args.bill)
    folder = Path(SAVE_FOLDER, safe_bill).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Workbook: {Path(args.excel_path).resolve()}\nEvidence directory: {folder}")
    options = Options()
    if not args.interactive:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1200")
    driver = webdriver.Chrome(service=Service(), options=options)
    driver.set_page_load_timeout(30)
    results = []
    try:
        for i, (_, row) in enumerate(df.iterrows(), 1):
            record = row.to_dict()
            name = str(spreadsheet_utils.get_col_val(record, "item_name") or "").strip()
            url = str(spreadsheet_utils.get_col_val(record, "link") or "").strip()
            cost = spreadsheet_utils.get_col_val(record, "cost")
            result = {"Item": name, "URL": url, "Approved Unit Cost": cost,
                      "Quoted Unit Cost": None, "Status": "skipped", "Screenshot": "", "Error": ""}
            print(f"\n[{i}/{len(df)}] {name}")
            if url.startswith("http"):
                shot = folder / ("".join(c if c.isalnum() or c in " -_" else "_" for c in name) + ".png")
                shot.unlink(missing_ok=True)
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        navigate_for_evidence(driver, url)
                        dismiss_popups(driver)
                        result["Screenshot"] = capture_evidence(driver, shot, interactive=args.interactive)
                        text, confidence = extract_price_from_page(driver, url)
                        value = parse_price(text)
                        result["Quoted Unit Cost"] = value
                        result["Status"] = "captured" if value is not None else "price_unverified"
                        result["Error"] = ""
                        print(f"  Screenshot: {result['Screenshot']}")
                        print(f"  Quoted unit price: {value if value is not None else 'unverified'}")
                        break
                    except BrowserChallenge as error:
                        result["Status"] = "challenge"
                        result["Error"] = str(error)
                        break
                    except Exception as error:
                        result["Status"] = "failed"
                        result["Error"] = str(error)
                        if attempt == MAX_RETRIES:
                            print(f"  Failed after {MAX_RETRIES + 1} attempts: {error}")
                results.append(result)
            else:
                results.append(result)
    finally:
        driver.quit()
    audit = folder / "screenshot_audit.csv"
    pd.DataFrame(results).to_csv(audit, index=False)
    print(f"\nReview audit in your spreadsheet: {audit}")
    print(f"Screenshots: {folder}\nCAPTCHA diagnostics: {folder / 'challenges'}")
    failed = sum(r["Status"] in ("challenge", "failed", "price_unverified") for r in results)
    print(f"Items: {len(results)} | Need attention: {failed}")
    sync_screenshots_to_sharepoint()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
