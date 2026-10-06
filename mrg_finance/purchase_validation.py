"""Reconcile real carts, quote amounts, and Engage amounts using decimal currency."""

from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from selenium.webdriver.common.by import By

from .price_scraper import extract_amazon_asin


def money(value):
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid money amount: {value!r}") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"Amount must be finite and nonnegative: {value!r}")
    try:
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"Invalid money amount: {value!r}") from None


def require_matching_total(cart_total, requested_amount):
    cart, request = money(cart_total), money(requested_amount)
    if cart != request:
        raise ValueError(f"Cart total ${cart} differs from Engage requested amount ${request}. "
                         "Refresh the cart and correct the quote before uploading.")


def _amazon_price(element):
    """Read a visible price, including Amazon's split whole/fraction markup."""
    if not element.is_displayed():
        return None
    # Amazon exposes the complete accessible price in a visually hidden span.
    # Its Selenium .text is empty, while the visible duplicate is split over lines.
    for accessible in element.find_elements(By.CSS_SELECTOR, ".a-offscreen"):
        raw = accessible.get_attribute("textContent")
        if raw and raw.strip():
            try:
                return money(raw)
            except ValueError:
                pass
    try:
        return money(element.text)
    except ValueError:
        whole = element.find_elements(By.CSS_SELECTOR, ".a-price-whole")
        fraction = element.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
        if whole and fraction:
            digits = fraction[0].text.strip()
            if re.fullmatch(r"\d{2}", digits):
                try:
                    return money(f"{whole[0].text.strip().rstrip('.')}.{digits}")
                except ValueError:
                    pass
    return None


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
        if not qty:
            quantities = set()
            for control in row.find_elements(By.CSS_SELECTOR, "button[aria-label*='Quantity is']"):
                match = re.search(r"\bquantity is\s+(\d+)\b", control.get_attribute("aria-label") or "", re.I)
                if control.is_displayed() and match:
                    quantities.add(match[1])
            if len(quantities) == 1:
                qty = quantities.pop()
        price = None
        # Prefer the explicit current price; do not scrape recommended items or a crossed-out list price.
        for selector in (".apex-price-to-pay-value", ".sc-product-price, .sc-price"):
            candidates = {_amazon_price(p) for p in row.find_elements(By.CSS_SELECTOR, selector)} - {None}
            if len(candidates) > 1:
                raise ValueError(f"Conflicting Amazon unit prices for {asin}; review the cart before continuing.")
            if candidates:
                price = candidates.pop()
                break
        missing = []
        if not asin:
            missing.append("ASIN")
        if not qty or not str(qty).isdigit() or int(qty) <= 0:
            missing.append("quantity")
        if price is None:
            missing.append("unit price")
        if missing:
            raise ValueError(f"Could not read an Amazon cart row ({asin or 'unknown item'}): "
                             f"missing {', '.join(missing)}. Check the cart and let it finish loading.")
        items.append({"asin": asin.upper(), "quantity": int(qty), "unit_price": price})
    subtotal_fields = driver.find_elements(
        By.CSS_SELECTOR, "#sc-subtotal-amount-activecart, #sc-subtotal-amount-buybox",
    )
    if not items:
        raise ValueError("No active Amazon cart items found. The cart may be empty; confirm the items were added in this browser.")
    subtotals = {_amazon_price(field) for field in subtotal_fields} - {None}
    if not subtotals:
        raise ValueError("Amazon cart subtotal not found. Return to the cart page and let it finish loading.")
    if len(subtotals) > 1:
        raise ValueError("Amazon cart subtotals disagree. Check selected items and reload the cart.")
    subtotal = subtotals.pop()
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
