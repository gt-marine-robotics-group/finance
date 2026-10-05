"""Reconcile real carts, quote amounts, and Engage amounts using decimal currency."""

from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from selenium.webdriver.common.by import By

from .price_scraper import extract_amazon_asin


def money(value):
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid money amount: {value!r}") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"Amount must be finite and nonnegative: {value!r}")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def require_matching_total(cart_total, requested_amount):
    cart, request = money(cart_total), money(requested_amount)
    if cart != request:
        raise ValueError(f"Cart total ${cart} differs from Engage requested amount ${request}. "
                         "Refresh the cart and correct the quote before uploading.")


def read_amazon_cart(driver):
    """Read active cart rows only. Unknown quantities/prices fail rather than guessing."""
    items = []
    for row in driver.find_elements(By.CSS_SELECTOR, "#sc-active-cart .sc-list-item[data-asin]"):
        if not row.is_displayed():
            continue
        asin = row.get_attribute("data-asin")
        qty = row.get_attribute("data-quantity")
        if not qty:
            controls = row.find_elements(By.CSS_SELECTOR, "select[name='quantity'], input[name='quantity']")
            qty = controls[0].get_attribute("value") if controls else None
        prices = row.find_elements(By.CSS_SELECTOR, ".sc-product-price, .sc-price")
        price = next((p.text.strip() for p in prices if p.is_displayed() and p.text.strip()), None)
        if not asin or not qty or not str(qty).isdigit() or int(qty) <= 0 or not price:
            raise ValueError("Could not read an Amazon cart row. Use --cart-source personal for manual verification.")
        items.append({"asin": asin.upper(), "quantity": int(qty), "unit_price": money(price)})
    subtotal_fields = driver.find_elements(By.CSS_SELECTOR, "#sc-subtotal-amount-activecart")
    if not items or not subtotal_fields:
        raise ValueError("Amazon active cart or subtotal not found. Resolve sign-in/CAPTCHA or use personal mode.")
    subtotal = money(subtotal_fields[0].text)
    line_total = sum((item["unit_price"] * item["quantity"] for item in items), Decimal("0"))
    require_matching_total(subtotal, line_total)
    return {"items": items, "subtotal": subtotal}


def reconcile_amazon_cart(requests, snapshot):
    expected = Counter()
    for item in requests:
        asin = item.get("asin") or extract_amazon_asin(item.get("resolved_url") or item.get("link", ""))
        if not asin:
            raise ValueError(f"Missing Amazon ASIN for {item['item_name']}")
        expected[asin.upper()] += item["quantity"]
    actual = Counter()
    price_by_asin = {}
    for item in snapshot["items"]:
        asin = item["asin"].upper()
        actual[asin] += item["quantity"]
        if asin in price_by_asin and price_by_asin[asin] != item["unit_price"]:
            raise ValueError(f"Multiple offers with different prices for {asin}; verify in personal mode.")
        price_by_asin[asin] = item["unit_price"]
    if actual != expected:
        raise ValueError(f"Amazon cart quantities do not match this order. Expected {dict(expected)}; "
                         f"actual {dict(actual)}. Check seller limits, missing items, and unrelated cart items.")
    for item in requests:
        asin = item.get("asin") or extract_amazon_asin(item.get("resolved_url") or item["link"])
        item["quoted_unit_cost"] = float(price_by_asin[asin.upper()])
        item["quoted_total"] = float(money(price_by_asin[asin.upper()] * item["quantity"]))
    require_matching_total(snapshot["subtotal"], sum(money(r["quoted_total"]) for r in requests))
