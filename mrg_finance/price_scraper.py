"""
price_scraper.py - Shared module for price scraping, price parsing, and vendor normalization.

Used by web-app (app.py, screenshot_worker.py) and CLI tools (mrg.py).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Vendor domain mappings
VENDOR_DOMAINS = {
    "amazon": "Amazon",
    "mcmaster": "McMaster-Carr",
    "digikey": "DigiKey",
    "mouser": "Mouser",
    "adafruit": "Adafruit",
    "sparkfun": "SparkFun",
    "pololu": "Pololu",
}


def normalize_vendor(vendor: str) -> str:
    """Normalize vendor name to Title Case or standard brand format."""
    if not isinstance(vendor, str) or not vendor.strip():
        return ""
    v = vendor.strip()
    v_lower = v.lower()
    for domain_key, name in VENDOR_DOMAINS.items():
        if domain_key in v_lower:
            return name
    return v.title()


def detect_vendor_from_url(url: str) -> str:
    """Detect vendor name from URL hostname."""
    if not isinstance(url, str) or not url.strip():
        return ""
    domain = urlparse(url).netloc.lower()
    for key, vendor_name in VENDOR_DOMAINS.items():
        if key in domain:
            return vendor_name
    return ""


def parse_price(s: str) -> float | None:
    """Extract float price from scraped text or raw string."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str) or not s.strip():
        return None

    s_clean = s.replace("\xa0", " ").strip()

    # Try dollar sign match first: e.g. "$12.99"
    dollar_match = re.search(r"\$\s*([\d,]+\.?\d*)", s_clean)
    if dollar_match:
        num_str = dollar_match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    # Generic decimal number fallback
    match = re.search(r"(\d{1,3}(?:[,]\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})", s_clean)
    if match:
        num_str = match.group(1).replace(",", "")
        try:
            return float(num_str)
        except ValueError:
            pass

    return None


def scrape_price_from_driver(driver) -> str:
    """
    Extract price text from a loaded Selenium webdriver page instance.
    Returns raw price string or empty string.
    """
    from selenium.webdriver.common.by import By

    def first_nonempty_text(element):
        txt = (element.text or "").strip()
        if not txt:
            txt = (element.get_attribute("innerText") or "").strip()
        if not txt:
            txt = (element.get_attribute("content") or "").strip()
        return txt

    def is_unit_price(element) -> bool:
        """Check if an element or its parent is a per-unit price rate (e.g. $0.25/ft)."""
        try:
            parent_cls = (element.get_attribute("class") or "") + " "
            try:
                parent_cls += (element.find_element(By.XPATH, "..").get_attribute("class") or "")
            except Exception:
                pass
            parent_cls_lower = parent_cls.lower()
            return any(k in parent_cls_lower for k in ("priceperunit", "unitprice", "per-unit", "basisprice"))
        except Exception:
            return False

    # Strategy 1: Amazon Buybox whole + fraction (highest accuracy for Amazon items)
    try:
        price_containers = driver.find_elements(
            By.CSS_SELECTOR,
            ".priceToPay, #corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price), #corePrice_desktop .a-price:not(.a-text-price)"
        )
        for container in price_containers:
            if is_unit_price(container):
                continue
            wholes = container.find_elements(By.CSS_SELECTOR, ".a-price-whole")
            fracs = container.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
            if wholes and fracs:
                w_txt = wholes[0].text.replace(",", "").strip().rstrip(".")
                f_txt = fracs[0].text.strip()
                if w_txt.isdigit() and f_txt.isdigit():
                    return f"${w_txt}.{f_txt}"
    except Exception:
        pass

    # Strategy 2: Amazon-priority CSS selectors (ignoring unit prices)
    amazon_selectors = [
        ".priceToPay .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen",
        "#corePrice_desktop .a-price:not(.a-text-price) .a-offscreen",
        "#apex_desktop .priceToPay .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#sns-base-price",
        "#newBuyBoxPrice",
        "#price_inside_buybox",
        "#buyNewSection .a-price .a-offscreen",
    ]

    for sel in amazon_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elems:
                if is_unit_price(el):
                    continue
                text = first_nonempty_text(el)
                if text and re.search(r"\d", text):
                    return text
        except Exception:
            continue

    # Strategy 3: JSON-LD schema price
    try:
        scripts = driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
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
                if is_unit_price(el):
                    continue
                text = first_nonempty_text(el)
                if text and re.search(r"\d", text):
                    return text
        except Exception:
            continue

    return ""


def dismiss_popups_and_interstitials(driver):
    """
    Dismiss cookie popups, consent dialogs, and Amazon/vendor anti-bot 'Continue shopping' interstitials.
    """
    import time
    try:
        from selenium.webdriver.common.by import By
        page_src = (driver.page_source or "").lower()
        # 1. Amazon "Click the button below to continue shopping" interstitial
        if "continue shopping" in page_src or "click the button below" in page_src:
            btns = driver.find_elements(
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue shopping')] | "
                "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue shopping')] | "
                "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue shopping')]"
            )
            for btn in btns:
                try:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(3)
                        break
                except Exception:
                    continue

        # 2. Standard cookie / consent / modal popups
        for sel in [
            '[id*="cookie"] button', '[class*="cookie"] button',
            '[id*="consent"] button', 'button[class*="accept"]',
            'button[class*="dismiss"]', 'button[aria-label*="close"]',
            '#sp-cc-accept', '#a-autoid-0-announce'
        ]:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in buttons[:2]:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.3)
                        break
            except Exception:
                continue
    except Exception:
        pass


def extract_amazon_asin(url: str) -> str | None:
    """Extract 10-character Amazon ASIN from product URL or redirect."""
    if not isinstance(url, str) or not url.strip():
        return None
    # 1. Standard /dp/, /gp/product/, /d/, /product/, /gp/aw/d/
    match = re.search(r"/(?:dp|gp/product|gp/aw/d|product|d)/([A-Z0-9]{10})", url, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # 2. Standalone ASIN parameter or path
    match2 = re.search(r"(?:/|[?&]asin=)([B0-9][A-Z0-9]{9})(?:[/?&]|$)", url, re.IGNORECASE)
    if match2:
        return match2.group(1).upper()
    # 3. Shortlinks (a.co, amzn.to)
    if "a.co" in url or "amzn.to" in url:
        try:
            import requests
            r = requests.head(url, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            final_url = r.url
            match3 = re.search(r"/(?:dp|gp/product|gp/aw/d|product|d)/([A-Z0-9]{10})", final_url, re.IGNORECASE)
            if match3:
                return match3.group(1).upper()
        except Exception:
            pass
    return None


def check_and_set_amazon_quantity(driver, desired_qty: int, item_name: str = "") -> tuple[int, bool, str]:
    """
    Checks available quantity and seller limit on Amazon page and sets the quantity.
    Returns (actual_qty_set, is_limited, limit_reason).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
    import re
    import time

    # 1. Check availability text for stock limits
    try:
        avail_elems = driver.find_elements(By.ID, "availability")
        if avail_elems:
            avail_text = avail_elems[0].text.strip()
            stock_match = re.search(r"only\s+(\d+)\s+left in stock", avail_text, re.IGNORECASE)
            if stock_match:
                stock_left = int(stock_match.group(1))
                if desired_qty > stock_left:
                    # Try to select the stock_left
                    try:
                        qty_selects = driver.find_elements(By.ID, "quantity")
                        if qty_selects:
                            Select(qty_selects[0]).select_by_value(str(stock_left))
                    except Exception:
                        pass
                    return stock_left, True, f"Only {stock_left} left in stock (requested {desired_qty})"
    except Exception:
        pass

    # 2. Check quantity dropdown
    try:
        qty_selects = driver.find_elements(By.ID, "quantity")
        if qty_selects:
            sel = Select(qty_selects[0])
            options = [opt.get_attribute("value") for opt in sel.options]
            numeric_options = [int(v) for v in options if v and v.isdigit()]
            if numeric_options:
                max_selectable = max(numeric_options)
                if desired_qty in numeric_options:
                    sel.select_by_value(str(desired_qty))
                    time.sleep(0.3)
                    return desired_qty, False, ""
                elif desired_qty > max_selectable:
                    sel.select_by_value(str(max_selectable))
                    time.sleep(0.3)
                    return max_selectable, True, f"Seller maximum limit is {max_selectable} per customer/order (requested {desired_qty})"
                else:
                    sel.select_by_value(str(numeric_options[0]))
                    time.sleep(0.3)
                    return numeric_options[0], True, f"Requested quantity {desired_qty} not in available dropdown options {numeric_options}"
    except Exception:
        pass

    # 3. Check number input box
    try:
        qty_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[id*="quantity"], input[name*="quantity"]')
        if qty_inputs:
            inp = qty_inputs[0]
            max_attr = inp.get_attribute("max")
            if max_attr and max_attr.isdigit() and desired_qty > int(max_attr):
                inp.clear()
                inp.send_keys(max_attr)
                return int(max_attr), True, f"Maximum allowed input is {max_attr} (requested {desired_qty})"
            else:
                inp.clear()
                inp.send_keys(str(desired_qty))
                return desired_qty, False, ""
    except Exception:
        pass

    return desired_qty, False, ""


def generate_amazon_cart_url(items: list[dict]) -> str:
    """Generate an Amazon add-to-cart URL from items with Amazon links."""
    amazon_items = []
    for item in items:
        link = str(item.get("Link", ""))
        if "amazon" not in link.lower():
            continue
        asin = extract_amazon_asin(link)
        if asin:
            try:
                qty = int(float(str(item.get("Quantity", 1)) or 1))
            except (ValueError, TypeError):
                qty = 1
            amazon_items.append((asin, qty))

    if not amazon_items:
        return ""

    params = []
    for i, (asin, qty) in enumerate(amazon_items, 1):
        params.append(f"ASIN.{i}={asin}&Quantity.{i}={qty}")

    return "https://www.amazon.com/gp/aws/cart/add.html?" + "&".join(params)


def scrape_item_price(url: str, timeout: int = 10) -> dict | None:
    """
    Fetch a product URL and attempt to extract current item price and vendor.
    Returns dict with 'current_price' (float), 'raw_price' (str), 'vendor' (str)
    or None if unparseable/failed.
    """
    if not isinstance(url, str) or not url.strip() or not url.startswith("http"):
        return None

    vendor = detect_vendor_from_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    # 1. Fast HTTP request strategy
    try:
        import requests
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            # Try JSON-LD schema price
            ld_matches = re.findall(
                r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                text,
                re.DOTALL | re.IGNORECASE,
            )
            for ld in ld_matches:
                try:
                    import json
                    data = json.loads(ld)
                    if isinstance(data, list):
                        data = data[0] if data else {}
                    offers = data.get("offers", {})
                    price_val = None
                    if isinstance(offers, dict) and "price" in offers:
                        price_val = offers["price"]
                    elif isinstance(offers, list) and offers:
                        price_val = offers[0].get("price")
                    elif "price" in data:
                        price_val = data["price"]

                    if price_val is not None:
                        p_float = parse_price(str(price_val))
                        if p_float is not None:
                            return {
                                "current_price": p_float,
                                "raw_price": f"${p_float:.2f}",
                                "vendor": vendor,
                            }
                except Exception:
                    continue

            # Try common open graph / meta tags
            meta_price = re.search(
                r'<meta[^>]*property=["\'](?:og:price:amount|product:price:amount)["\'][^>]*content=["\']([^"\']+)["\']',
                text,
                re.IGNORECASE,
            )
            if not meta_price:
                meta_price = re.search(
                    r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\'](?:og:price:amount|product:price:amount)["\']',
                    text,
                    re.IGNORECASE,
                )
            if meta_price:
                p_float = parse_price(meta_price.group(1))
                if p_float is not None:
                    return {
                        "current_price": p_float,
                        "raw_price": f"${p_float:.2f}",
                        "vendor": vendor,
                    }

            # Try regex page source patterns (priceAmount, etc.)
            for pattern in [
                r'"priceAmount"\s*:\s*"?([\d.]+)"?',
                r'"price"\s*:\s*\{\s*"value"\s*:\s*"?([\d.]+)"?',
                r'"buyingPrice"\s*:\s*"?([\d.]+)"?',
            ]:
                m = re.search(pattern, text)
                if m:
                    p_float = parse_price(m.group(1))
                    if p_float is not None:
                        return {
                            "current_price": p_float,
                            "raw_price": f"${p_float:.2f}",
                            "vendor": vendor,
                        }
    except Exception:
        pass

    # 2. Fallback to Selenium headless driver if available
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"user-agent={headers['User-Agent']}")

        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            raw_str = scrape_price_from_driver(driver)
            p_float = parse_price(raw_str)
            if p_float is not None:
                return {
                    "current_price": p_float,
                    "raw_price": raw_str,
                    "vendor": vendor,
                }
        finally:
            driver.quit()
    except Exception:
        pass

    return None

