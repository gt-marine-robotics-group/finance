"""Checks for stale quotes, browser challenges, and custom Engage field routing."""

import base64
import json
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import quote

import openpyxl
import pytest
from selenium.webdriver.common.by import By

from mrg_finance import cli, order_excel_builder, share_a_cart
from mrg_finance.spreadsheet_utils import get_col_val
from mrg_finance.engage_fields import FormFieldError, fill_purchase_fields, find_labeled_field
from mrg_finance.purchase_validation import money, read_amazon_cart, reconcile_amazon_cart, require_matching_total
from mrg_finance.screenshot_capture import BrowserChallenge, capture_evidence, navigate_for_evidence, save_page_screenshot
from mrg_finance.vendor_payee import lookup_vendor_payee
from mrg_finance.purchase_cart import recheck_cart, prepare_cart


class Field:
    def __init__(self, id_, value="", text="", **attributes):
        self.attributes = {"id": id_, "value": value, **attributes}
        self.text = text

    def clear(self):
        self.attributes["value"] = ""

    def send_keys(self, value):
        self.attributes["value"] += str(value)

    def get_attribute(self, name):
        return self.attributes.get(name)

    def is_displayed(self):
        return True


@pytest.mark.parametrize("value,expected", [("$1,234.56", "1234.56"), (0.1 + 0.2, "0.30"), ("2.675", "2.68")])
def test_currency_rounds_to_cents(value, expected):
    assert money(value) == Decimal(expected)


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "", None])
def test_invalid_currency_is_not_a_fallback(value):
    with pytest.raises(ValueError):
        money(value)


def test_one_cent_difference_blocks_engage():
    require_matching_total("19.99", "19.99")
    with pytest.raises(ValueError, match="differs"):
        require_matching_total("19.99", "20.00")


def order():
    return [{"item_name": "Part", "quantity": 2, "cost": 10,
             "link": "https://www.amazon.com/dp/B012345678"}]


def snapshot(quantity=2, price="12.50", extra=False):
    items = [{"asin": "B012345678", "quantity": quantity, "unit_price": Decimal(price)}]
    if extra:
        items.append({"asin": "B000000001", "quantity": 1, "unit_price": Decimal("5")})
    return {"items": items, "subtotal": sum(i["unit_price"] * i["quantity"] for i in items)}


def test_actual_cart_quote_retains_approved_baseline():
    items = order()
    reconcile_amazon_cart(items, snapshot())
    assert items[0]["cost"] == 10
    assert items[0]["quoted_unit_cost"] == 12.5
    assert items[0]["quoted_total"] == 25


@pytest.mark.parametrize("cart", [snapshot(quantity=1), snapshot(extra=True), {"items": [], "subtotal": Decimal(0)}])
def test_seller_limits_and_unrelated_items_block(cart):
    with pytest.raises(ValueError, match="quantities"):
        reconcile_amazon_cart(order(), cart)


def test_duplicate_asins_are_aggregated():
    items = order() + order()
    reconcile_amazon_cart(items, snapshot(quantity=4))
    assert sum(i["quoted_total"] for i in items) == 50


def test_cart_reader_refuses_unreadable_prices():
    driver = MagicMock()
    row = MagicMock()
    row.is_displayed.return_value = True
    row.get_attribute.side_effect = lambda key: {"data-asin": "B012345678", "data-quantity": "2"}.get(key)
    row.find_elements.return_value = []
    driver.find_elements.return_value = [row]
    with pytest.raises(ValueError, match="Could not read"):
        read_amazon_cart(driver)


def test_refresh_rejects_changed_unit_prices_even_when_total_is_unchanged(monkeypatch, tmp_path):
    old = snapshot()
    old["items"].append({"asin": "B000000001", "quantity": 1, "unit_price": Decimal("5")})
    old["subtotal"] = Decimal("30")
    fresh = snapshot(price="13")
    fresh["items"].append({"asin": "B000000001", "quantity": 1, "unit_price": Decimal("4")})
    fresh["subtotal"] = Decimal("30")
    monkeypatch.setattr("mrg_finance.purchase_cart.navigate_for_evidence", lambda *a: None)
    monkeypatch.setattr("mrg_finance.purchase_cart.capture_evidence", lambda *a, **kw: None)
    monkeypatch.setattr("mrg_finance.purchase_cart.read_amazon_cart", lambda d: fresh)
    cart = {"driver": MagicMock(), "vendor_key": "amazon", "snapshot": old,
            "subtotal": Decimal("30"), "screenshot": str(tmp_path / "cart.png")}
    with pytest.raises(ValueError, match="changed after review"):
        recheck_cart(cart, order())


def challenge_driver(body):
    driver = MagicMock()
    driver.current_url = "https://www.amazon.com/errors/validateCaptcha"
    driver.title = "Robot Check"
    driver.find_element.return_value.text = body
    driver.find_elements.return_value = []
    driver.execute_script.return_value = "complete"
    driver.save_screenshot.side_effect = lambda path: Path(path).write_bytes(b"image") or True
    return driver


def test_captcha_saves_diagnostic_and_invalidates_stale_attachment(tmp_path):
    target = tmp_path / "cart.png"
    target.write_bytes(b"old quote")
    with pytest.raises(BrowserChallenge):
        capture_evidence(challenge_driver("Enter the characters you see below"), target)
    assert not target.exists()
    metadata = list((tmp_path / "challenges").glob("*.json"))
    assert len(metadata) == 1
    assert json.loads(metadata[0].read_text())["status"] == "challenge"


def test_challenge_can_be_solved_before_capturing_quote(tmp_path):
    driver = challenge_driver("Robot check")
    def solve(_):
        driver.current_url = "https://www.amazon.com/gp/cart/view.html"
        driver.title = "Cart"
        driver.find_element.return_value.text = "Subtotal $25.00"
        return ""
    driver.execute_cdp_cmd.side_effect = RuntimeError("No CDP")
    path = capture_evidence(driver, tmp_path / "cart.png", interactive=True, prompt=solve)
    assert Path(path).exists()
    assert list((tmp_path / "challenges").glob("*.png"))


def test_full_page_capture_and_viewport_fallback(tmp_path):
    driver = MagicMock()
    driver.execute_cdp_cmd.side_effect = [{"contentSize": {"width": 100, "height": 5000}},
                                         {"data": base64.b64encode(b"png bytes").decode()}]
    target = tmp_path / "page.png"
    save_page_screenshot(driver, target)
    assert target.read_bytes() == b"png bytes"
    assert driver.execute_cdp_cmd.call_args.args[1]["clip"]["height"] == 5000
    driver.execute_cdp_cmd.side_effect = RuntimeError("Unsupported")
    driver.save_screenshot.return_value = False
    with pytest.raises(RuntimeError, match="capture failed"):
        save_page_screenshot(driver, target)


def test_navigation_timeout_allows_challenge_inspection():
    from selenium.common.exceptions import TimeoutException
    driver = MagicMock()
    driver.get.side_effect = TimeoutException()
    navigate_for_evidence(driver, "https://example.org")
    driver.get.assert_called_once()


def form_driver():
    driver = MagicMock()
    amount = Field("Amount")
    driver.find_elements.side_effect = lambda by, value: [amount] if value == "Amount" else []
    fields = {"refs": Field("refs"), "sga": Field("sga"), "payee": Field("payee")}
    def resolve(script, labels, excluded):
        if labels[0].startswith("What is"):
            return [fields["refs"]]
        if labels[0].startswith("Include Bill"):
            return [fields["sga"]]
        if labels[0] == "payee name":
            return [fields["payee"]]
        return []
    driver.execute_script.side_effect = resolve
    return driver, amount, fields


def test_bill_details_go_into_separate_verified_fields():
    driver, amount, fields = form_driver()
    fill_purchase_fields(driver, amount="25", cart_total="25", bill_refs="Bill 376582, Line 4",
                         sga_lines="$25.00, Bill 376582, Line 4", payee={"name": "Amazon"})
    assert fields["refs"].get_attribute("value") == "Bill 376582, Line 4"
    assert fields["sga"].get_attribute("value").startswith("$25.00")
    assert fields["payee"].get_attribute("value") == "Amazon"
    assert amount.get_attribute("value") == "25.00"
    assert all(call.args[1] != "Description" for call in driver.find_elements.call_args_list)


def test_missing_custom_field_stops_without_description_fallback():
    driver, _, _ = form_driver()
    driver.execute_script.return_value = []
    driver.execute_script.side_effect = None
    with pytest.raises(FormFieldError, match="found 0"):
        fill_purchase_fields(driver, amount=25, cart_total=25, bill_refs="Bill 1, Line 2",
                             sga_lines="$25, Bill 1", payee={"name": "Vendor"})
    assert not driver.find_element.called


def test_ambiguous_field_is_rejected():
    driver = MagicMock()
    driver.execute_script.return_value = [Field("a"), Field("b")]
    with pytest.raises(FormFieldError, match="found 2"):
        find_labeled_field(driver, ["SGA Bill"])


def test_requested_amount_mismatch_blocks_before_custom_fields():
    driver, _, _ = form_driver()
    with pytest.raises(ValueError, match="differs"):
        fill_purchase_fields(driver, amount=20, cart_total=25, bill_refs="Bill 1",
                             sga_lines="$20", payee={"name": "Vendor"})
    driver.execute_script.assert_not_called()


@pytest.mark.parametrize("vendor", ["Digi-Key", "DigiKey Electronics", "Other vendor"])
def test_non_amazon_share_cart_never_posts_synthetic_payload(monkeypatch, vendor):
    post = MagicMock()
    monkeypatch.setattr("requests.post", post)
    assert share_a_cart.create_share_a_cart_link(order(), vendor) is None
    post.assert_not_called()


@pytest.mark.parametrize("raw,expected", [
    ("ABC123", "https://share-a-cart.com/get/ABC123"),
    ("share-a-cart.com/get/ABC123", "https://share-a-cart.com/get/ABC123"),
    ("https://shareacart.net/get/ABC123", "https://shareacart.net/get/ABC123"),
    ("https://evil.example/get/ABC123", None), ("not a cart", None),
])
def test_shared_cart_links_are_validated(raw, expected):
    assert share_a_cart.normalize_share_a_cart_url(raw) == expected


def test_known_payees_require_no_options_or_network(monkeypatch):
    get = MagicMock()
    monkeypatch.setattr("requests.get", get)
    assert lookup_vendor_payee("Amazon", "")["name"] == "Amazon.com Services LLC"
    assert lookup_vendor_payee("Digi-Key", "")["email"] == "orders@digikey.com"
    get.assert_not_called()


def test_other_payee_uses_official_structured_contact(monkeypatch):
    response = MagicMock()
    response.url = "https://example.org/contact"
    response.text = '<script type="application/ld+json">' + json.dumps({
        "@type": "Organization", "name": "Example Parts", "url": "https://example.org",
        "address": {"streetAddress": "123 Main St", "addressLocality": "Atlanta", "postalCode": "30332"},
        "email": "orders@example.org",
    }) + '</script>'
    monkeypatch.setattr("requests.get", lambda *a, **kw: response)
    result = lookup_vendor_payee("Example", "https://example.org/products/part")
    assert result["address"] == "123 Main St, Atlanta, 30332"
    assert result["source"] == response.url


def test_report_uses_verified_line_and_quote_instead_of_excel_id(tmp_path):
    item = order()[0]
    item.update(bill_no="376582", bill_item_id="999", resolved_line_id=4,
                resolved_section="B06", quoted_unit_cost=12.5)
    xlsx, _ = order_excel_builder.generate_order_budget_vs_quoted_excel("test", [item], output_dir=str(tmp_path))
    wb = openpyxl.load_workbook(xlsx)
    row = list(wb.active.iter_rows(min_row=5, max_row=5, values_only=True))[0]
    assert row[0] == "Line 4"
    assert row[3] == "B06"
    assert row[5] == 10
    assert row[8] == 12.5
    wb.close()


def test_cli_removed_gui_and_exposes_personal_cart(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["mrg-finance", "purchase", "--help"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--cart-source" in help_text
    assert "payee" not in help_text
    assert "review GUI" not in help_text
    assert not hasattr(cli, "cmd_review")


def test_personal_mode_shares_real_cart_and_uses_account_profile(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    driver = MagicMock()
    factory = MagicMock(return_value=driver)
    monkeypatch.setattr("mrg_finance.purchase_cart.webdriver.Chrome", factory)
    monkeypatch.setattr("mrg_finance.purchase_cart.Service", MagicMock())
    monkeypatch.setattr("mrg_finance.purchase_cart.navigate_for_evidence", lambda *a: None)
    monkeypatch.setattr("mrg_finance.purchase_cart.capture_evidence", lambda d, p, **kw: str(p))
    monkeypatch.setattr("mrg_finance.purchase_cart.read_amazon_cart", lambda d: snapshot())
    monkeypatch.setattr(share_a_cart, "find_share_a_cart_extension", lambda: None)
    api = MagicMock()
    monkeypatch.setattr(share_a_cart, "create_share_a_cart_link", api)
    monkeypatch.setattr(share_a_cart, "prompt_for_share_a_cart", lambda *a: "https://share-a-cart.com/get/REAL01")
    answers = iter(["", "", "", "25.00"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    cart = prepare_cart(order(), "Amazon", "personal-test", source="personal")
    assert cart["total"] == Decimal("25.00")
    assert cart["share_url"].endswith("REAL01")
    assert any(a.startswith("--user-data-dir=") for a in factory.call_args.kwargs["options"].arguments)
    api.assert_not_called()


def test_automated_quantity_limit_stops_before_sharing_or_upload(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    driver = MagicMock()
    driver.current_url = order()[0]["link"]
    monkeypatch.setattr("mrg_finance.purchase_cart.webdriver.Chrome", lambda **kw: driver)
    monkeypatch.setattr("mrg_finance.purchase_cart.Service", MagicMock())
    monkeypatch.setattr("mrg_finance.purchase_cart.navigate_for_evidence", lambda *a: None)
    monkeypatch.setattr("mrg_finance.purchase_cart.capture_evidence", lambda d, p, **kw: str(p))
    monkeypatch.setattr("mrg_finance.price_scraper.dismiss_popups_and_interstitials", lambda d: None)
    monkeypatch.setattr("mrg_finance.price_scraper.check_and_set_amazon_quantity", lambda *a: (1, True, "seller maximum"))
    monkeypatch.setattr(share_a_cart, "find_share_a_cart_extension", lambda: None)
    api = MagicMock()
    monkeypatch.setattr(share_a_cart, "create_share_a_cart_link", api)
    with pytest.raises(ValueError, match="available 1"):
        prepare_cart(order(), "Amazon", "limited-test")
    driver.quit.assert_called_once()
    api.assert_not_called()


@pytest.mark.parametrize("column,key", [("Bill Item ID", "item_name"), ("Total Cost", "cost"),
                                       ("Share-A-Cart Link", "link"), ("Bill No. (Engage)", "bill_item_id")])
def test_column_aliases_do_not_take_values_from_other_known_fields(column, key):
    assert get_col_val({column: "wrong value"}, key) == ""


@pytest.mark.parametrize("changed_amount", [False, True])
def test_purchase_upload_gate_uses_real_cart_amount(monkeypatch, tmp_path, changed_amount):
    from mrg_finance import automation_purchase
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bills"
    ws.append(["Bill Item ID", "Bill No.", "Bill Title", "Item Name", "Vendor", "Cost", "Quantity", "Link"])
    ws.append(["999", "376582", "Test Bill", "Part", "Amazon", 10, 2, order()[0]["link"]])
    ws = wb.create_sheet("Ordering")
    ws.append(["Order ID", "Bill Item ID", "Quantity", "Status"])
    ws.append(["purchase-test", "999", 2, "Pending"])
    path = tmp_path / "test.xlsx"
    wb.save(path)
    wb.close()
    items = order()
    reconcile_amazon_cart(items, snapshot())
    folder = tmp_path / "evidence"
    folder.mkdir()
    screenshot = folder / "cart.png"
    screenshot.write_bytes(b"fake cart screenshot")
    cart_driver = MagicMock()
    cart = {"driver": cart_driver, "folder": folder, "screenshot": str(screenshot),
            "total": Decimal("25.00"), "subtotal": Decimal("25.00"),
            "shipping": Decimal(0), "tax": Decimal(0), "share_url": "https://share-a-cart.com/get/REAL01"}
    def prepared(requests, *a):
        requests[0].update(quoted_unit_cost=12.5, quoted_total=25)
        return cart
    monkeypatch.setattr(automation_purchase, "prepare_cart", prepared)
    monkeypatch.setattr(automation_purchase, "USERNAME", "test-only")
    monkeypatch.setattr(automation_purchase, "PASSWORD", "test-only")
    monkeypatch.setattr("sys.argv", ["purchase", "--order", "purchase-test", "--excel-path", str(path)])
    driver, amount, fields = form_driver()
    description = Field("Description")
    uploads = [Field("upload-1"), Field("upload-2")]
    driver.current_url = "https://gatech.campuslabs.com/engage/finance/request/1234"
    driver.find_elements.side_effect = lambda by, selector: [amount] if selector == "Amount" else uploads if selector == 'input[type="file"]' else []
    def find_element(by, selector):
        if selector == "discovery-bar":
            raise LookupError()
        if selector == "Description":
            return description
        return MagicMock()
    driver.find_element.side_effect = find_element
    monkeypatch.setattr(automation_purchase.webdriver, "Chrome", lambda **kw: driver)
    monkeypatch.setattr(automation_purchase.WebDriverWait, "until", lambda *a: MagicMock())
    monkeypatch.setattr(automation_purchase.time, "sleep", lambda *a: None)
    monkeypatch.setattr(automation_purchase, "lookup_bill_item_locations", lambda *a: {"Part": {"section_line_number": 4, "section": "B06"}})
    def recheck(*a):
        if changed_amount:
            amount.attributes["value"] = "24.99"
    monkeypatch.setattr(automation_purchase, "recheck_cart", recheck)
    monkeypatch.setattr(automation_purchase, "save_page_screenshot", lambda *a: "diagnostic.png")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: MagicMock(returncode=0))
    answers = iter(["y", "y", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    if changed_amount:
        with pytest.raises(SystemExit) as error:
            automation_purchase.main()
        assert error.value.code == 1
        assert all(not f.get_attribute("value") for f in uploads)
    else:
        automation_purchase.main()
        assert amount.get_attribute("value") == "25.00"
        assert all(f.get_attribute("value") for f in uploads)
        assert fields["sga"].get_attribute("value") == "$25.00, Line 4, Bill 376582, B06"
        report = openpyxl.load_workbook(folder / "Budget_vs_Quoted_Detail_purchase-test.xlsx")
        assert "Cart Reconciliation" in report.sheetnames
        report.close()
    assert "Share-A-Cart" in description.get_attribute("value")
    assert "Bill 376582" not in description.get_attribute("value")
    cart_driver.quit.assert_called_once()
    driver.quit.assert_called_once()


@pytest.mark.skipif(os.environ.get("MRG_RUN_BROWSER_TESTS") != "1", reason="Opt-in local headless Chrome DOM verification")
def test_real_dom_routes_custom_questions_without_touching_description():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    try:
        html = '''<form>
          <label for="Subject">Subject</label><input id="Subject">
          <label for="Description">Description</label><textarea id="Description">Keep shared cart link</textarea>
          <label for="Amount">Requested Amount</label><input id="Amount">
          <div><p>What is the Budget/Bill # and Request Line #? (Ex. Bill 376582, Line 4)</p><textarea id="custom-1"></textarea></div>
          <div><h3>SGA Bill</h3><label for="custom-2">Include Bill # and total reimbursement amount below ($ Per line item)</label><textarea id="custom-2"></textarea></div>
          <span id="payee-label">Payee Name</span><input id="custom-3" aria-labelledby="payee-label">
          <label for="address">Payee Address</label><textarea id="address"></textarea>
        </form>'''
        driver.get("data:text/html," + quote(html))
        fill_purchase_fields(driver, amount=25, cart_total=25,
                             bill_refs="Bill 376582, Line 4", sga_lines="$25.00, Bill 376582, Line 4",
                             payee={"name": "Amazon.com Services LLC", "address": "410 Terry Avenue North"})
        assert driver.find_element(By.ID, "Description").get_attribute("value") == "Keep shared cart link"
        assert driver.find_element(By.ID, "custom-1").get_attribute("value") == "Bill 376582, Line 4"
        assert driver.find_element(By.ID, "custom-2").get_attribute("value").startswith("$25.00")
        assert driver.find_element(By.ID, "custom-3").get_attribute("value") == "Amazon.com Services LLC"
        assert driver.find_element(By.ID, "address").get_attribute("value") == "410 Terry Avenue North"
    finally:
        driver.quit()
