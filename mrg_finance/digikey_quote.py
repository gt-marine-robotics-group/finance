"""Read DigiKey's displayed quote, keeping product prices separate from charges."""

from collections import Counter
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlparse

from selenium.webdriver.common.by import By

from .purchase_validation import money


class DigiKeyCartMismatch(ValueError):
    """A readable cart contains different products, quantities, or prices."""


def product_id(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "digikey.com" or host.endswith(".digikey.com")):
        raise ValueError("Automatic DigiKey verification needs a digikey.com product URL.")
    match = re.search(r"/products/detail/[^/]+/[^/]+/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise ValueError("DigiKey product ID not found in the product URL.")
    return match[1]


def unit_price(text):
    # Electronics prices can have five decimal places; round only extended totals.
    match = re.fullmatch(r"\s*(?:Unit Price\s*)?\$?\s*(\d[\d,]*(?:\.\d+)?)\s*", text, re.I)
    if not match:
        raise ValueError("DigiKey unit price could not be read.")
    try:
        value = Decimal(match[1].replace(",", ""))
    except InvalidOperation:
        raise ValueError("Invalid DigiKey unit price.") from None
    if not value.is_finite():
        raise ValueError("Invalid DigiKey unit price.")
    return value


def read_product_price(driver, quantity):
    """Choose the applicable quantity break in the product's main pricing table."""
    prices = set()
    for table in driver.find_elements(By.CSS_SELECTOR, "table"):
        if not table.is_displayed():
            continue
        headers = [" ".join(e.text.lower().split()) for e in table.find_elements(By.CSS_SELECTOR, "thead th")]
        if "quantity" not in headers or "unit price" not in headers:
            continue
        q_col, p_col = headers.index("quantity"), headers.index("unit price")
        breaks = []
        for row in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
            if not row.is_displayed():
                continue
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            if len(cells) <= max(q_col, p_col):
                continue
            threshold = cells[q_col].text.strip().replace(",", "")
            if not threshold.isdigit():
                continue
            if int(threshold) <= quantity:
                breaks.append((int(threshold), unit_price(cells[p_col].text)))
        if breaks:
            threshold = max(q for q, _ in breaks)
            prices.update(p for q, p in breaks if q == threshold)
    if len(prices) != 1:
        raise ValueError("DigiKey product pricing table unavailable or ambiguous.")
    return prices.pop()


def _summary(driver):
    summaries = {}
    for heading in driver.find_elements(By.XPATH, "//*[normalize-space(.)='Cart Summary']"):
        if heading.is_displayed():
            container = heading.find_element(By.XPATH,
                "./ancestor::*[contains(., 'Subtotal') and contains(., 'Total')][1]")
            summaries[container.id] = container.text
    if len(summaries) != 1:
        raise ValueError("DigiKey Cart Summary not found or ambiguous.")
    text = next(iter(summaries.values()))
    amounts = {}
    for label, value in re.findall(
        r"(?im)^\s*(Subtotal|Shipping|(?:Sales )?Tax|Total)\s*:?\s*(?:\*\s*)?\$?\s*"
        r"(\d[\d,]*(?:\.\d+)?)\s*\*?\s*$", text,
    ):
        key = label.lower().replace("sales ", "")
        if key in amounts and amounts[key] != money(value):
            raise ValueError(f"Conflicting DigiKey {key} amounts.")
        amounts[key] = money(value)
    for label in re.findall(r"(?im)^\s*(Shipping|(?:Sales )?Tax)\s*:?\s*(?:Free|No charge)\s*$", text):
        amounts[label.lower().replace("sales ", "")] = money(0)
    if "subtotal" not in amounts:
        raise ValueError("DigiKey merchandise subtotal unavailable.")
    amounts["estimated"] = bool(re.search(r"\bestimat", text, re.I))
    amounts["tax_displayed"] = "tax" in amounts
    # The cart often has no tax line. Zero here describes the displayed quote,
    # not a claim about the tax on a future checkout or invoice.
    if ("tax" not in amounts and "shipping" in amounts and "total" in amounts
            and amounts["total"] == amounts["subtotal"] + amounts["shipping"]):
        amounts["tax"] = money(0)
    return amounts


def read_cart(driver):
    """Read visible native cart rows; ignore hidden templates and recommendations."""
    items = []
    for row in driver.find_elements(By.CSS_SELECTOR, "#cartDetails tbody tr.detailRow"):
        if not row.is_displayed():
            continue
        links = {e.get_attribute("href") for e in row.find_elements(By.CSS_SELECTOR,
                 ".detailRow_productDetails a[href*='/products/detail/']") if e.is_displayed()}
        quantities = {e.get_attribute("value") for e in row.find_elements(By.CSS_SELECTOR,
                      ".detailRow_qtyInput input:not([type='hidden'])") if e.is_displayed()}
        prices = {unit_price(e.text) for e in row.find_elements(By.CSS_SELECTOR, ".cart-unitPrice")
                  if e.is_displayed()}
        extended = {money(re.sub(r"^\s*Extended Price\s*", "", e.text, flags=re.I))
                    for e in row.find_elements(By.CSS_SELECTOR, ".cart-extendedPrice") if e.is_displayed()}
        if any(len(values) != 1 for values in (links, quantities, prices, extended)):
            raise ValueError("DigiKey cart row has unreadable or ambiguous product, quantity, or price fields.")
        quantity = quantities.pop()
        if not quantity or not quantity.isdigit() or int(quantity) <= 0:
            raise ValueError("DigiKey cart quantity unavailable.")
        price, line_total = prices.pop(), extended.pop()
        if money(price * int(quantity)) != line_total:
            raise ValueError("DigiKey row prices are still updating or do not match its quantity.")
        items.append({"product_id": product_id(links.pop()), "quantity": int(quantity),
                      "unit_price": price, "line_total": line_total})
    if not items:
        raise ValueError("No readable DigiKey cart items found.")
    summary = _summary(driver)
    if summary["subtotal"] != sum((i["line_total"] for i in items), Decimal(0)):
        raise ValueError("DigiKey item totals disagree with its displayed subtotal; wait for the cart to update.")
    return {"items": items, **summary}


def reconcile_cart(requests, snapshot):
    expected = Counter()
    for item in requests:
        expected[product_id(item["link"])] += item["quantity"]
    actual, prices = Counter(), {}
    for item in snapshot["items"]:
        part = item["product_id"]
        actual[part] += item["quantity"]
        if part in prices and prices[part] != item["unit_price"]:
            raise DigiKeyCartMismatch("DigiKey has multiple prices for one product; correct the cart before continuing.")
        prices[part] = item["unit_price"]
    if actual != expected:
        raise DigiKeyCartMismatch(f"DigiKey cart products/quantities differ from Ordering. "
                                 f"Expected {dict(expected)}; cart {dict(actual)}. Correct the cart in Chrome.")
    quotes = [(float(prices[product_id(item["link"])]),
               float(money(prices[product_id(item["link"])] * item["quantity"]))) for item in requests]
    if snapshot["subtotal"] != sum((money(total) for _, total in quotes), Decimal(0)):
        raise DigiKeyCartMismatch("DigiKey line rounding differs from the order quote; review the cart before continuing.")
    for item, (price, total) in zip(requests, quotes):
        item.update(quoted_unit_cost=price, quoted_total=total)


def complete_charges(snapshot):
    return (all(key in snapshot for key in ("shipping", "tax", "total"))
            and snapshot["total"] == snapshot["subtotal"] + snapshot["shipping"] + snapshot["tax"])


def procurement_quote(quote):
    """Apply MRG's GT-accountant shipping arrangement, preserving vendor evidence.

    DigiKey's public cart estimate is not the shipping charge on the institution's
    order. Merchandise and tax remain subject to the usual verification gates.
    """
    if not complete_charges(quote):
        raise ValueError("DigiKey quote charges do not reconcile; refresh the quote before applying GT shipping.")
    return {**quote, "vendor_shipping": quote["shipping"], "vendor_total": quote["total"],
            "shipping": money(0), "total": quote["subtotal"] + quote["tax"],
            "shipping_basis": "Georgia Tech accountant DigiKey order: free shipping"}
