"""Quotes read from DigiKey must automate entry without masking wrong cart contents."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import MagicMock

import openpyxl
import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from mrg_finance import digikey_cart, digikey_quote, order_excel_builder, purchase_cart, share_a_cart
from mrg_finance.purchase_sources import offer_quote_replacements


LINK = "https://www.digikey.com/en/products/detail/raspberry-pi/SC0194-9/10258781"
ITEM = {"item_name": "Raspberry Pi", "quantity": 5, "cost": 63.35,
        "bill_no": "344042", "link": LINK}
SUMMARY = "Cart Summary\nSubtotal\n$500.00\nShipping\n* $8.49\nTotal\n* $508.49\n* Estimates"


def field(text="", visible=True, **attrs):
    element = MagicMock()
    element.text = text
    element.is_displayed.return_value = visible
    element.get_attribute.side_effect = attrs.get
    return element


def cart_row(link=LINK, quantity="5", price="100.00000", total="$500.00", visible=True):
    row = field(visible=visible)
    values = {
        ".detailRow_productDetails a[href*='/products/detail/']": [field(href=link)],
        ".detailRow_qtyInput input:not([type='hidden'])": [field(value=quantity)],
        ".cart-unitPrice": [field("Unit Price\n" + price)],
        ".cart-extendedPrice": [field("Extended Price\n" + total)],
    }
    row.find_elements.side_effect = lambda by, selector: values.get(selector, [])
    return row


def cart_driver(rows=None, summary=SUMMARY, duplicate_heading=False):
    driver = MagicMock()
    container = field(summary)
    container.id = "cart-summary"
    heading = field("Cart Summary")
    heading.find_element.return_value = container
    nested_heading = field("Cart Summary")
    nested_heading.find_element.return_value = container
    driver.find_elements.side_effect = lambda by, selector: (
        rows if rows is not None else [cart_row()]) if by == By.CSS_SELECTOR else (
        [heading, nested_heading] if duplicate_heading else [heading])
    return driver


def test_read_actual_digikey_layout_distinguishes_merchandise_shipping_and_estimated_total():
    snapshot = digikey_quote.read_cart(cart_driver(duplicate_heading=True))
    items = [ITEM.copy()]
    digikey_quote.reconcile_cart(items, snapshot)
    assert snapshot["subtotal"] == Decimal("500.00")
    assert snapshot["shipping"] == Decimal("8.49")
    assert snapshot["tax"] == 0
    assert snapshot["total"] == Decimal("508.49")
    assert snapshot["estimated"] is True
    assert digikey_quote.complete_charges(snapshot)
    assert items[0]["quoted_unit_cost"] == 100
    assert items[0]["quoted_total"] == 500
    assert items[0]["cost"] == 63.35


def test_multi_item_quote_keeps_fractional_unit_prices_and_ignores_hidden_templates():
    other = "https://www.digikey.com/en/products/detail/test/part/123"
    driver = cart_driver([cart_row(), cart_row(other, "10", "2.34567", "$23.46"),
                          cart_row(quantity="999", visible=False)],
                         SUMMARY.replace("500.00", "523.46").replace("508.49", "531.95"))
    snapshot = digikey_quote.read_cart(driver)
    items = [ITEM.copy(), {**ITEM, "link": other, "quantity": 10}]
    digikey_quote.reconcile_cart(items, snapshot)
    assert items[1]["quoted_unit_cost"] == 2.34567
    assert items[1]["quoted_total"] == 23.46
    assert snapshot["subtotal"] == Decimal("523.46")


@pytest.mark.parametrize("row", [cart_row(quantity="0"), cart_row(quantity="1.5"),
                                  cart_row(quantity="4"), cart_row(price="unavailable"),
                                  cart_row(total="$499.99")])
def test_unreadable_or_updating_rows_do_not_create_a_quote(row):
    with pytest.raises(ValueError):
        digikey_quote.read_cart(cart_driver([row]))


@pytest.mark.parametrize("change", ["quantity", "product", "additional"])
def test_readable_wrong_cart_is_rejected_without_changing_requests(change):
    snapshot = digikey_quote.read_cart(cart_driver())
    if change == "quantity":
        snapshot["items"][0]["quantity"] = 4
    elif change == "product":
        snapshot["items"][0]["product_id"] = "123"
    else:
        snapshot["items"].append({**snapshot["items"][0], "product_id": "123"})
    items = [ITEM.copy()]
    with pytest.raises(digikey_quote.DigiKeyCartMismatch):
        digikey_quote.reconcile_cart(items, snapshot)
    assert items == [ITEM]


@pytest.mark.parametrize("summary", [
    "Cart Summary\nSubtotal\n$500.00\nShipping\nCalculated at checkout\nTotal\n$500.00",
    "Cart Summary\nSubtotal\n$500.00\nShipping\n$8.49\nTotal\n$520.00",
])
def test_unknown_charges_are_not_assumed_to_be_zero(summary):
    snapshot = digikey_quote.read_cart(cart_driver(summary=summary))
    assert not digikey_quote.complete_charges(snapshot)
    assert "tax" not in snapshot


def test_quantity_break_uses_main_product_table_not_related_product_prices():
    driver, table, related = MagicMock(), field(), field()
    headers = [field("QUANTITY"), field("UNIT PRICE"), field("EXT PRICE")]
    rows = []
    for quantity, price in [("1", "$100.00000"), ("5", "$95.50000"), ("10", "$90.00000")]:
        row = field()
        row.find_elements.return_value = [field(quantity), field(price), field("irrelevant")]
        rows.append(row)
    table.find_elements.side_effect = lambda by, selector: headers if selector == "thead th" else rows
    related.find_elements.return_value = [field("Quantity"), field("Price")]
    driver.find_elements.return_value = [related, table]
    assert digikey_quote.read_product_price(driver, 5) == Decimal("95.50000")
    assert digikey_quote.read_product_price(driver, 2) == Decimal("100.00000")


@pytest.mark.parametrize("label,count", [("1 item(s)", 1), ("0 item(s)", 0),
                                        ("Your Item(s) 5", 5), ("2 items", 2)])
def test_digikey_cart_badge_is_recognized_after_adding(label, count):
    driver = MagicMock()
    driver.find_elements.return_value = [field(label)]
    assert digikey_cart._cart_count(driver) == count


def setup_browser(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    driver = cart_driver()
    monkeypatch.setattr(purchase_cart.webdriver, "Chrome", lambda **kw: driver)
    monkeypatch.setattr(purchase_cart, "Service", MagicMock())
    monkeypatch.setattr(purchase_cart, "navigate_for_evidence", MagicMock())
    monkeypatch.setattr(purchase_cart, "capture_evidence", lambda d, p, **kw: str(p))
    monkeypatch.setattr(purchase_cart, "save_page_screenshot", lambda d, p, **kw: str(p))
    monkeypatch.setattr(purchase_cart, "prepare_digikey_items", MagicMock())
    monkeypatch.setattr(share_a_cart, "find_share_a_cart_extension", lambda: None)
    monkeypatch.setattr(share_a_cart, "prompt_for_share_a_cart", lambda *a, **kw: "https://share-a-cart.com/get/DIGI01")
    return driver


def test_digikey_preparation_and_final_recheck_need_no_transcribed_amounts(monkeypatch, tmp_path):
    driver = setup_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(digikey_quote, "read_product_price", lambda *a: Decimal("100"))
    monkeypatch.setattr(purchase_cart.price_scraper, "dismiss_popups_and_interstitials", lambda *a: None)
    prompts = []
    def keep_product(prompt):
        assert "substitute product URL" in prompt
        prompts.append(prompt)
        return ""
    monkeypatch.setattr("builtins.input", keep_product)
    persist = MagicMock()
    items = [ITEM.copy()]
    cart = purchase_cart.prepare_cart(items, "DigiKey", "auto-test",
                                     quote_review=lambda rows, vendor: offer_quote_replacements(rows, vendor, persist))
    assert cart["total"] == Decimal("500.00")
    assert cart["shipping"] == 0
    assert cart["vendor_total"] == Decimal("508.49")
    assert cart["vendor_shipping"] == Decimal("8.49")
    assert cart["snapshot"]["shipping"] == Decimal("8.49")
    assert items[0]["quoted_total"] == 500
    purchase_cart.recheck_cart(cart, items)
    assert len(prompts) == 1  # Keep/replace choice retained; no repeated price, subtotal, or charge entry.
    persist.assert_not_called()
    driver.quit.assert_not_called()


@pytest.mark.parametrize("change", ["price", "quantity", "tax"])
def test_digikey_changed_quote_stops_before_upload(monkeypatch, tmp_path, change):
    setup_browser(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=AssertionError("No amount entry expected")))
    items = [ITEM.copy()]
    cart = purchase_cart.prepare_cart(items, "DigiKey", "auto-test")
    changed = deepcopy(cart["snapshot"])
    if change == "tax":
        changed["tax"] += Decimal("1")
        changed["total"] += Decimal("1")
    else:
        changed["items"][0]["unit_price" if change == "price" else "quantity"] += 1
    monkeypatch.setattr(digikey_quote, "read_cart", lambda d: changed)
    with pytest.raises(ValueError, match="changed after review"):
        purchase_cart.recheck_cart(cart, items)


def test_changing_public_shipping_estimate_does_not_change_gt_free_shipping(monkeypatch, tmp_path):
    setup_browser(monkeypatch, tmp_path)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=AssertionError("No amount entry expected")))
    items = [ITEM.copy()]
    cart = purchase_cart.prepare_cart(items, "DigiKey", "auto-test")
    fresh = deepcopy(cart["snapshot"])
    fresh["shipping"] += Decimal(1)
    fresh["total"] += Decimal(1)
    monkeypatch.setattr(digikey_quote, "read_cart", lambda d: fresh)
    purchase_cart.recheck_cart(cart, items)
    assert cart["total"] == 500


def test_gt_shipping_adjustment_preserves_tax_and_rejects_unreconciled_quote():
    quote = {"subtotal": Decimal("500"), "shipping": Decimal("8.49"),
             "tax": Decimal("30"), "total": Decimal("538.49")}
    adjusted = digikey_quote.procurement_quote(quote)
    assert adjusted["total"] == 530
    assert adjusted["tax"] == 30
    assert quote["shipping"] == Decimal("8.49")
    with pytest.raises(ValueError, match="do not reconcile"):
        digikey_quote.procurement_quote({**quote, "total": Decimal("500")})


@pytest.mark.parametrize("mismatch", [False, True])
def test_automatic_read_failure_offers_fallback_but_wrong_quantities_cannot_be_overridden(
    monkeypatch, tmp_path, mismatch,
):
    driver = setup_browser(monkeypatch, tmp_path)
    if mismatch:
        snapshot = digikey_quote.read_cart(driver)
        snapshot["items"][0]["quantity"] = 4
        monkeypatch.setattr(purchase_cart.WebDriverWait, "until", lambda *a: snapshot)
        answers = iter(["manual", "cancel"])
    else:
        monkeypatch.setattr(purchase_cart.WebDriverWait, "until", MagicMock(side_effect=TimeoutException()))
        answers = iter(["manual"])
    monkeypatch.setattr("builtins.input", lambda p: next(answers))
    if mismatch:
        with pytest.raises(ValueError, match="verification cancelled"):
            purchase_cart.verify_digikey_cart_with_retry(driver, [ITEM.copy()], tmp_path)
    else:
        assert purchase_cart.verify_digikey_cart_with_retry(driver, [ITEM.copy()], tmp_path) is None
    assert list(answers) == []


def test_auto_quote_creates_comparison_with_charges_without_fabricating_funding_lines(tmp_path):
    items = [ITEM.copy()]
    snapshot = digikey_quote.read_cart(cart_driver())
    digikey_quote.reconcile_cart(items, snapshot)
    path, csv = order_excel_builder.generate_order_budget_vs_quoted_excel(
        "auto-test", items, output_dir=str(tmp_path), preliminary=True,
        cart_quote=digikey_quote.procurement_quote(snapshot))
    report = openpyxl.load_workbook(path)
    assert report.active["F5"].value == 63.35
    assert report.active["I5"].value == 100
    assert report.active["A5"].value == "Pending lookup"
    assert report.active["J5"].value == "=ROUND(H5*I5,2)"
    summary = dict(report["Cart Reconciliation"].values)
    assert summary["Merchandise"] == 500
    assert summary["Shipping"] == 0
    assert summary["Vendor total"] == 508.49
    assert summary["Vendor displayed shipping"] == 8.49
    assert summary["Requested amount"] == 500
    assert "Georgia Tech" in summary["Shipping basis"]
    assert summary["Charges estimated by vendor"] is True
    report.close()
