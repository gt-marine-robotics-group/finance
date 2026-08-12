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

    # Strategy 1: Page source regex for unit price (most reliable for Amazon)
    try:
        page_source = driver.page_source
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


def extract_amazon_asin(url: str) -> str | None:
    """Extract 10-character Amazon ASIN from product URL."""
    if not isinstance(url, str) or not url.strip():
        return None
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


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

