import os
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
CSV_PATH = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
OUTPUT_CSV = "./FY27_Bills_Budget_Updated.csv"
SHEET_NAME = "Bills"  # which sheet/tab to read from the xlsx
SAVE_FOLDER = "./screenshots"
REVIEW_HTML = "./review.html"
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


def generate_review_html(data, bill_title, output_path):
    """Generate an interactive HTML review page with editable prices."""
    ok_count = sum(1 for d in data if d["status"] == "ok")
    review_count = sum(1 for d in data if d["status"] == "needs_review")
    fail_count = sum(1 for d in data if d["status"] in ("failed", "error"))
    skip_count = sum(1 for d in data if d["status"] == "skipped")

    rows_html = ""
    for i, item in enumerate(data):
        status_emoji = {"ok": "✅", "needs_review": "⚠️", "failed": "❌",
                        "error": "💥", "skipped": "⏭️"}.get(item["status"], "❓")
        status_class = item["status"]
        current_price = f"{item['parsed_price']:.2f}" if item["parsed_price"] else ""
        csv_price = item["csv_cost"]

        screenshot_html = (
            f'<a href="screenshots/{item["screenshot"]}" target="_blank">'
            f'<img src="screenshots/{item["screenshot"]}" alt="{item["item_name"]}" loading="lazy" /></a>'
            if item["screenshot"]
            else '<div class="no-screenshot">No screenshot</div>'
        )

        rows_html += f'''
        <div class="item-card {status_class}" data-status="{status_class}" data-index="{i}">
            <div class="item-header">
                <span class="status">{status_emoji}</span>
                <span class="item-name">{item['item_name']}</span>
                <span class="confidence badge-{item['confidence']}">{item['confidence']}</span>
            </div>
            <div class="item-body">
                <div class="screenshot-col">{screenshot_html}</div>
                <div class="details-col">
                    <table>
                        <tr><td>Spreadsheet:</td><td><strong>{csv_price}</strong></td></tr>
                        <tr><td>Scraped:</td><td><code>{item['scraped_price']}</code></td></tr>
                        <tr>
                            <td>Final Price:</td>
                            <td>
                                <span class="price-input-wrap">$<input type="number" step="0.01" min="0"
                                    class="price-input" data-index="{i}"
                                    value="{current_price}"
                                    placeholder="enter price" /></span>
                            </td>
                        </tr>
                        <tr><td>URL:</td><td><a href="{item['url']}" target="_blank">Open Link ↗</a></td></tr>
                    </table>
                    <button class="use-csv-btn" onclick="useCsvPrice({i}, '{csv_price}')">Use spreadsheet price</button>
                </div>
            </div>
        </div>'''

    # Build JSON data for export
    import json as json_mod
    items_json = json_mod.dumps([{
        "item_name": d["item_name"],
        "csv_cost": d["csv_cost"],
        "parsed_price": d["parsed_price"],
        "url": d["url"],
    } for d in data])

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Price Review — {bill_title}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; padding: 20px; }}
        h1 {{ margin-bottom: 10px; }}
        .top-bar {{ display: flex; align-items: center; gap: 15px; margin-bottom: 20px; }}
        .summary {{ background: #fff; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary span {{ margin-right: 20px; }}
        .filters {{ margin-bottom: 15px; }}
        .filters button {{ padding: 6px 14px; margin-right: 8px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background: #fff; }}
        .filters button.active {{ background: #333; color: #fff; border-color: #333; }}
        .export-bar {{ background: #1976d2; color: #fff; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; align-items: center; gap: 15px; }}
        .export-bar button {{ padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 0.95em; }}
        .export-bar .btn-export {{ background: #fff; color: #1976d2; }}
        .export-bar .btn-export:hover {{ background: #e3f2fd; }}
        .export-bar .btn-accept {{ background: #4caf50; color: #fff; }}
        .export-bar .btn-accept:hover {{ background: #388e3c; }}
        .item-card {{ background: #fff; border-radius: 8px; margin-bottom: 16px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 4px solid #ccc; }}
        .item-card.ok {{ border-left-color: #4caf50; }}
        .item-card.needs_review {{ border-left-color: #ff9800; }}
        .item-card.failed {{ border-left-color: #f44336; }}
        .item-card.error {{ border-left-color: #9c27b0; }}
        .item-card.skipped {{ border-left-color: #9e9e9e; opacity: 0.7; }}
        .item-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
        .item-name {{ font-weight: 600; font-size: 1.1em; }}
        .confidence {{ font-size: 0.8em; padding: 2px 8px; border-radius: 3px; }}
        .badge-high {{ background: #e8f5e9; color: #2e7d32; }}
        .badge-medium {{ background: #fff3e0; color: #e65100; }}
        .badge-low {{ background: #fce4ec; color: #c62828; }}
        .badge-none {{ background: #f5f5f5; color: #616161; }}
        .badge-skipped {{ background: #f5f5f5; color: #9e9e9e; }}
        .badge-manual {{ background: #e3f2fd; color: #1565c0; }}
        .item-body {{ display: flex; gap: 20px; align-items: flex-start; }}
        .screenshot-col {{ flex: 0 0 450px; }}
        .screenshot-col img {{ width: 100%; border: 1px solid #eee; border-radius: 4px; }}
        .no-screenshot {{ width: 100%; height: 200px; display: flex; align-items: center; justify-content: center; background: #f5f5f5; border-radius: 4px; color: #999; }}
        .details-col table {{ border-collapse: collapse; }}
        .details-col td {{ padding: 6px 12px 6px 0; vertical-align: middle; }}
        .details-col td:first-child {{ color: #666; }}
        .price-input-wrap {{ display: flex; align-items: center; gap: 2px; font-weight: 600; font-size: 1.1em; }}
        .price-input {{ width: 100px; padding: 4px 8px; border: 2px solid #ddd; border-radius: 4px; font-size: 1em; font-weight: 600; }}
        .price-input:focus {{ border-color: #1976d2; outline: none; }}
        .price-input.edited {{ border-color: #4caf50; background: #f1f8e9; }}
        .use-csv-btn {{ margin-top: 8px; padding: 4px 10px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer; background: #fff; font-size: 0.85em; }}
        .use-csv-btn:hover {{ background: #f5f5f5; }}
        code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }}
        a {{ color: #1976d2; }}
        .hidden {{ display: none !important; }}
        .toast {{ position: fixed; bottom: 20px; right: 20px; background: #333; color: #fff; padding: 12px 20px; border-radius: 8px; display: none; z-index: 999; }}
        .toast.show {{ display: block; animation: fadeIn 0.3s; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
    </style>
</head>
<body>
    <h1>📋 Price Review — {bill_title}</h1>
    <p style="color:#666; margin-bottom:15px;">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Edit prices below, then export.</p>

    <div class="export-bar">
        <span>✏️ Edit prices directly → then:</span>
        <button class="btn-accept" onclick="acceptAllCsv()">Accept all spreadsheet prices</button>
        <button class="btn-export" onclick="saveToSpreadsheet()">💾 Save to Spreadsheet</button>
        <span id="export-status"></span>
    </div>

    <div class="summary">
        <span>✅ OK: <strong>{ok_count}</strong></span>
        <span>⚠️ Review: <strong>{review_count}</strong></span>
        <span>❌ Failed: <strong>{fail_count}</strong></span>
        <span>⏭️ Skipped: <strong>{skip_count}</strong></span>
        <span>Total: <strong>{len(data)}</strong></span>
    </div>

    <div class="filters">
        <button class="active" onclick="filterItems('all')">All ({len(data)})</button>
        <button onclick="filterItems('needs_review')">⚠️ Review ({review_count})</button>
        <button onclick="filterItems('failed')">❌ Failed ({fail_count})</button>
        <button onclick="filterItems('ok')">✅ OK ({ok_count})</button>
    </div>

    <div id="items">{rows_html}</div>

    <div class="toast" id="toast"></div>

    <script>
        const itemsData = {items_json};

        // Track edits
        document.querySelectorAll('.price-input').forEach(input => {{
            input.addEventListener('input', function() {{
                this.classList.add('edited');
                const idx = parseInt(this.dataset.index);
                itemsData[idx].final_price = parseFloat(this.value) || 0;
            }});
        }});

        function useCsvPrice(idx, csvPrice) {{
            const val = parseFloat(csvPrice.replace('$','').replace(',','')) || 0;
            const input = document.querySelector(`.price-input[data-index="${{idx}}"]`);
            input.value = val.toFixed(2);
            input.classList.add('edited');
            itemsData[idx].final_price = val;
            showToast(`Set ${{itemsData[idx].item_name}} to $${{val.toFixed(2)}}`);
        }}

        function acceptAllCsv() {{
            document.querySelectorAll('.price-input').forEach(input => {{
                const idx = parseInt(input.dataset.index);
                const csvPrice = itemsData[idx].csv_cost;
                const val = parseFloat(String(csvPrice).replace('$','').replace(',','')) || 0;
                if (val > 0) {{
                    input.value = val.toFixed(2);
                    input.classList.add('edited');
                    itemsData[idx].final_price = val;
                }}
            }});
            showToast('All prices set to spreadsheet values');
        }}

        function exportCsv() {{
            // Collect all edited prices
            const prices = [];
            document.querySelectorAll('.price-input').forEach(input => {{
                const idx = parseInt(input.dataset.index);
                const val = parseFloat(input.value);
                if (val > 0) {{
                    prices.push({{
                        item_name: itemsData[idx].item_name,
                        price: val
                    }});
                }}
            }});

            // Send to local server
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
                    showToast(`✅ Saved ${{data.count}} prices to spreadsheet`);
                }}
            }})
            .catch(err => {{
                showToast('❌ Server not running. Start with: python review_server.py');
            }});
        }}

        function saveToSpreadsheet() {{
            exportCsv();
        }}

        function filterItems(status) {{
            document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            document.querySelectorAll('.item-card').forEach(card => {{
                const s = card.dataset.status;
                if (status === 'all') card.classList.remove('hidden');
                else if (status === 'failed') card.classList.toggle('hidden', s !== 'failed' && s !== 'error');
                else card.classList.toggle('hidden', s !== status);
            }});
        }}

        function showToast(msg) {{
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }}
    </script>
</body>
</html>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# === MAIN ===
if __name__ == "__main__":
    # === CHECK FILE NOT LOCKED ===
    if CSV_PATH.endswith(".xlsx"):
        # Check for Excel lock file (indicates file is open)
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
    df.fillna("", inplace=True)
    df.columns = df.columns.str.strip()

    required_cols = {"Item Name", "Link", "Cost", "Bill Title"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in CSV: {missing}")

    # Show available bills and prompt
    titles = df["Bill Title"].astype(str).str.strip().unique()
    SKIP_TITLES = ("nan", "request", "liquid", "misc")
    titles = [t for t in titles if t and not any(t.lower().startswith(s) for s in SKIP_TITLES)]
    print("\nAvailable Bill Titles:")
    for i, t in enumerate(titles, 1):
        count = (df["Bill Title"].astype(str).str.strip().str.lower() == t.lower()).sum()
        print(f"  {i}. {t} ({count} items)")

    bill_title = input("\nEnter Bill Title (or number): ").strip()
    if bill_title.isdigit() and 1 <= int(bill_title) <= len(titles):
        bill_title = titles[int(bill_title) - 1]

    # Filter
    mask = df["Bill Title"].astype(str).str.strip().str.lower() == bill_title.lower()
    df_filtered = df[mask].copy()

    if df_filtered.empty:
        print(f"\n⚠️ No entries for '{bill_title}'")
        exit(0)

    # === PRE-FLIGHT CHECK ===
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

    # === PREPARE DIRECTORIES ===
    if os.path.exists(SAVE_FOLDER):
        for f in os.listdir(SAVE_FOLDER):
            fp = os.path.join(SAVE_FOLDER, f)
            if os.path.isfile(fp):
                os.remove(fp)
    else:
        os.makedirs(SAVE_FOLDER)

    # === SETUP SELENIUM ===
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

    # === SCRAPE LOOP ===
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
                "confidence": "skipped", "screenshot": None, "status": "skipped",
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
                # Extra wait for Amazon (JS-heavy)
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                if "amazon" in domain:
                    time.sleep(DELAY)  # Amazon needs more time for price widgets
                else:
                    time.sleep(DELAY - 2)

                scraped_text, confidence = extract_price_from_page(driver, url)
                parsed = parse_price(scraped_text)

                # Save screenshot with safe filename
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', item_name) + ".png"
                screenshot_path = os.path.join(SAVE_FOLDER, safe_filename)
                driver.save_screenshot(screenshot_path)
                screenshot_file = safe_filename
                print(f"  📸 Saved")
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

        if parsed is not None and parsed > 0.0:
            # Only overwrite cost if the spreadsheet has no cost for this item
            existing_cost = parse_price(csv_cost)
            if existing_cost and existing_cost > 0:
                # Compare scraped vs existing — flag mismatch for review
                if abs(parsed - existing_cost) > 0.01:
                    print(f"  💲 Scraped ${parsed:.2f} ≠ spreadsheet ${existing_cost:.2f} — keeping spreadsheet value")
                    status = "needs_review"
                else:
                    print(f"  💲 ${parsed:.2f} ✓ matches spreadsheet")
                    status = "ok"
            else:
                df.at[idx, "Cost"] = f"${parsed:.2f}"
                print(f"  💲 ${parsed:.2f} (confidence: {confidence})")
                status = "ok" if confidence in ("high", "medium") else "needs_review"
        else:
            print(f"  ⚠️ No price scraped (raw: '{scraped_text}')")
            status = "failed" if screenshot_file else "error"

        review_data.append({
            "item_name": item_name, "url": url, "csv_cost": csv_cost,
            "scraped_price": scraped_text, "parsed_price": parsed,
            "confidence": confidence, "screenshot": screenshot_file, "status": status,
        })

    driver.quit()

    # === SAVE ===
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n✅ Updated CSV: {OUTPUT_CSV}")

    generate_review_html(review_data, bill_title, REVIEW_HTML)
    print(f"📋 Review: {os.path.abspath(REVIEW_HTML)}")

    # === SUMMARY ===
    ok = sum(1 for d in review_data if d["status"] == "ok")
    needs_review = sum(1 for d in review_data if d["status"] == "needs_review")
    failed = sum(1 for d in review_data if d["status"] in ("failed", "error"))
    print(f"\n{'='*50}")
    print(f"  ✅ OK: {ok}  |  ⚠️ Review: {needs_review}  |  ❌ Failed: {failed}")
    print(f"{'='*50}")

    # === INTERACTIVE PRICE CORRECTION ===
    flagged = [d for d in review_data if d["status"] in ("needs_review", "failed", "error")]
    if flagged:
        print(f"\n📝 {len(flagged)} item(s) need review.")
        print(f"   Opening review.html with live editing...")
        print(f"   Edit prices in your browser, click 'Save to Spreadsheet', then come back here.\n")

        # Start local server in background thread
        import threading
        import subprocess
        from http.server import HTTPServer
        from review_server import ReviewHandler, PORT

        server = HTTPServer(("localhost", PORT), ReviewHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print(f"   ✅ Review server running on http://localhost:{PORT}")

        # Open review.html
        subprocess.run(["open", REVIEW_HTML])

        input("   Press Enter when done editing → ")
        server.shutdown()
        print("   ✅ Server stopped. Changes saved to spreadsheet.")
    else:
        print(f"\n✅ All prices matched! No review needed.")
        import subprocess
        open_review = input(f"\nOpen review.html anyway? [y/N]: ").strip().lower()
        if open_review == "y":
            subprocess.run(["open", REVIEW_HTML])
