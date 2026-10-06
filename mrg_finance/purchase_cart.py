"""Prepare and verify a vendor cart before opening the Engage form."""

from decimal import Decimal
import json
from pathlib import Path
import re

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException,
    StaleElementReferenceException, TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from . import digikey_quote, price_scraper, share_a_cart
from .purchase_validation import money, read_amazon_cart, reconcile_amazon_cart, require_matching_total
from .screenshot_capture import BrowserChallenge, capture_evidence, navigate_for_evidence, save_page_screenshot
from .vendor_payee import vendor_key
from .digikey_cart import prepare_digikey_items
from .browser_profiles import cart_profile


def _cart_count(driver):
    counts = driver.find_elements(By.ID, "nav-cart-count")
    return next((int(e.text.strip()) for e in counts
                 if e.is_displayed() and e.text.strip().isdigit()), None)


def amazon_items_to_add(driver, items, folder):
    """Add only absent products; retain unreadable/conflicting carts for repair."""
    navigate_for_evidence(driver, "https://www.amazon.com/gp/cart/view.html")
    capture_evidence(driver, folder / "amazon_cart_before.png", interactive=True)
    grouped = {}
    for item in items:
        asin = price_scraper.extract_amazon_asin(item["link"])
        if not asin:
            raise ValueError(f"Missing Amazon product ID for {item['item_name']}")
        asin = asin.upper()
        if asin in grouped:
            grouped[asin]["quantity"] += item["quantity"]
        else:
            grouped[asin] = dict(item)
    body = driver.find_element(By.TAG_NAME, "body").text
    empty = isinstance(body, str) and any(text in body.lower() for text in (
        "your amazon cart is empty", "your shopping cart is empty"))
    if empty and _cart_count(driver) in (None, 0):
        return list(grouped.values())
    try:
        snapshot = read_amazon_cart(driver)
        actual = {}
        for row in snapshot["items"]:
            actual[row["asin"]] = actual.get(row["asin"], 0) + row["quantity"]
        if any(asin not in grouped or qty != grouped[asin]["quantity"]
               for asin, qty in actual.items()):
            raise ValueError("Existing cart quantities/products differ from this order.")
    except ValueError as error:
        print(f"Amazon cart retained: {error}\n"
              "Automatic additions are paused to avoid duplicates. Correct the cart in Chrome; "
              "it will be verified before continuing.")
        return []
    missing = [item for asin, item in grouped.items() if asin not in actual]
    print(f"Reusing {len(actual)} existing Amazon product(s); adding {len(missing)} missing product(s).")
    return missing


def prompt_money(prompt, *, default=None):
    """Recover from typing errors without discarding the verified cart."""
    while True:
        answer = input(prompt).strip()
        if answer.lower() in ("cancel", "q", "quit"):
            raise ValueError("Cart amount entry cancelled; no Engage request was prepared.")
        if not answer and default is not None:
            return money(default)
        try:
            return money(answer)
        except ValueError:
            print("Enter the nonnegative amount shown by the vendor (for example 609.90), "
                  "or type 'cancel'. The browser is still open.")


def prompt_manual_cart_quote(items):
    """Reconcile manually read merchandise prices without discarding the cart on a typo."""
    print("\nRead the prices from the actual cart. Enter the price for ONE unit of each product.\n"
          "Shipping and tax are entered separately after the item subtotal matches.")
    while True:
        for item in items:
            item["quoted_unit_cost"] = float(prompt_money(
                f"  {item['item_name']} — price for ONE unit (ordering {item['quantity']}; or 'cancel'): $"))
            item["quoted_total"] = float(money(Decimal(str(item["quoted_unit_cost"])) * item["quantity"]))
        subtotal = sum((money(i["quoted_total"]) for i in items), Decimal("0"))
        print("\nCalculated item totals:")
        for item in items:
            print(f"  {item['quantity']} x ${money(item['quoted_unit_cost'])} = ${money(item['quoted_total'])}"
                  f" — {item['item_name']}")
        print(f"Items only: ${subtotal}. Shipping and tax are excluded.")
        while True:
            shown = prompt_money("Cart ITEMS subtotal, excluding shipping/tax (or 'cancel'): $")
            if shown == subtotal:
                return subtotal
            print(f"\nSubtotal mismatch: the cart amount you entered is ${shown}; "
                  f"the entered unit prices x quantities total ${subtotal}.\n"
                  "If your amount includes shipping or tax, enter only the item subtotal here; "
                  "you will enter those charges next. Otherwise check the unit prices and cart quantities.\n"
                  "The browser is still open; no Engage request has been prepared.")
            while True:
                action = input("Enter to correct the subtotal, 'prices' to re-enter unit prices, or 'cancel': ").strip().lower()
                if action in ("cancel", "q", "quit"):
                    raise ValueError("Cart subtotal verification cancelled; no Engage request was prepared.")
                if action in ("", "prices"):
                    break
                print("Press Enter, type 'prices', or type 'cancel'.")
            if action == "prices":
                break


def decline_amazon_coverage(driver, clicked):
    """Resolve a visible optional coverage dialog; leave unknown choices to the user.

    Return whether a coverage dialog is still visible. A cart-count increase is
    not sufficient confirmation while Amazon is asking about another purchase.
    """
    dialogs = driver.find_elements(By.CSS_SELECTOR,
        "[role='dialog'], [aria-modal='true'], .a-popover, "
        "#attach-warranty, #attach-warranty-pane, #attach-warranty-display, #attach-service-interstitial")
    visible = False
    for dialog in dialogs:
        if not dialog.is_displayed() or not re.search(r"\b(?:protection|coverage|warranty)\b", dialog.text, re.I):
            continue
        visible = True
        declines = []
        for control in dialog.find_elements(By.CSS_SELECTOR,
                "button, input[type='button'], input[type='submit'], a, [role='button']"):
            if not control.is_displayed() or not control.is_enabled():
                continue
            labels = [control.text, control.get_attribute("aria-label"), control.get_attribute("value")]
            for label_id in (control.get_attribute("aria-labelledby") or "").split():
                labels.extend(e.get_attribute("textContent") for e in dialog.find_elements(By.ID, label_id))
            if any(re.fullmatch(
                r"no,?\s+thanks[.!]?|no,?\s+thank you[.!]?|"
                r"(?:continue|proceed) without (?:coverage|protection)(?: plan)?[.!]?|"
                r"(?:decline|skip) (?:coverage|protection)(?: plan)?[.!]?",
                " ".join((label or "").lower().split()),
            ) for label in labels):
                declines.append(control)
        # Do not choose among multiple ambiguous offers, or repeat a decline
        # while the dialog is still processing its first native click.
        if len(declines) == 1 and declines[0].id not in clicked:
            control = declines[0]
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", control)
                control.click()
            except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
                continue
            clicked.add(control.id)
            print("Declined optional Amazon protection coverage; waiting for the item to be added.")
            return True
    return visible


def add_amazon_item_to_cart(driver, button, item_name, folder):
    """Use native clicks, recover from overlays, and wait for Amazon confirmation."""
    before = _cart_count(driver)
    coverage_choices = set()

    def click_visible_button(d):
        if decline_amazon_coverage(d, coverage_choices):
            return False
        count = _cart_count(d)
        if before is not None and count is not None and count > before:
            return True  # A replaced DOM node may already have submitted the add.
        # Amazon can replace the buy box after quantity selection. Reacquire the
        # current visible button and center it away from sticky page elements.
        for candidate in d.find_elements(By.ID, "add-to-cart-button"):
            if candidate.is_displayed() and candidate.is_enabled():
                d.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", candidate)
                candidate.click()
                return True
        return False

    def added(d):
        if decline_amazon_coverage(d, coverage_choices):
            return False
        count = _cart_count(d)
        if before is not None and count is not None and count > before:
            return True
        confirmations = d.find_elements(
            By.CSS_SELECTOR,
            "#NATC_SMART_WAGON_CONF_MSG_SUCCESS, #huc-v2-order-row-confirm-text, #sw-atc-confirmation",
        )
        return any(e.is_displayed() and "added to cart" in e.text.lower() for e in confirmations)

    try:
        try:
            if button is None:
                raise ElementNotInteractableException("Add to Cart button not available")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", button)
            button.click()
        except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
            print("Add to Cart is blocked or still loading; retrying the visible button…")
            WebDriverWait(driver, 8, ignored_exceptions=(
                ElementClickInterceptedException, ElementNotInteractableException,
                StaleElementReferenceException,
            )).until(click_visible_button)
        WebDriverWait(driver, 20, ignored_exceptions=(StaleElementReferenceException,)).until(added)
    except TimeoutException:
        diagnostic = save_page_screenshot(driver, folder / "cart_diagnostics" / "add_to_cart.png", full_page=False)
        print(f"\nAdd to Cart was not confirmed for {item_name}.\n"
              f"Diagnostic: {diagnostic}\n"
              "The browser is still open. Resolve any sign-in or offer prompt and finish adding this item.\n"
              "Check whether it was already added before adding it again.\n"
              "The complete cart will still be checked against the order.")
        answer = input("Finish adding the item, then Enter to continue (or 'cancel'): ").strip().lower()
        if answer in ("cancel", "skip", "q", "quit"):
            raise ValueError("Cart preparation cancelled; no Engage request was prepared.")


def verify_amazon_cart_with_retry(driver, items, folder):
    """Keep the same browser open for corrections, without accepting an unverified quote."""
    attempt = 0
    while True:
        capture_evidence(driver, folder / "cart.png", interactive=True)
        try:
            snapshot = read_amazon_cart(driver)
            reconcile_amazon_cart(items, snapshot)
            return snapshot
        except (ValueError, StaleElementReferenceException) as error:
            attempt += 1
            diagnostics = folder / "cart_diagnostics"
            diagnostic = save_page_screenshot(
                driver, diagnostics / f"verification_{attempt}.png", full_page=False,
            )
            Path(diagnostic).with_suffix(".json").write_text(json.dumps({
                "status": "verification_failed", "reason": str(error),
                "url": driver.current_url, "title": driver.title,
            }, indent=2), encoding="utf-8")
            (folder / "cart.png").unlink(missing_ok=True)
            print(f"\nAmazon cart verification failed: {error}\n"
                  f"Diagnostic: {diagnostic}\n"
                  "The browser is still open. Sign in if needed, add the missing items, and check quantities.\n"
                  "Remove unrelated items, then leave the Amazon cart page visible before retrying.")
            answer = input("Fix the cart, then Enter to retry verification (or 'cancel'): ").strip().lower()
            if answer in ("cancel", "skip", "q", "quit"):
                raise ValueError("Amazon cart verification cancelled; no Engage request was prepared.") from error


def review_product_prices_before_cart(driver, items, vendor, folder, quote_review):
    """Offer substitutions before any cart mutation or interactive challenge loop."""
    print("\nChecking product prices against the approved bill before adding anything to the cart.")
    for n, item in enumerate(items, 1):
        print(f"\nPrice check {n}/{len(items)}: {item['item_name']}")
        navigate_for_evidence(driver, item["link"])
        price_scraper.dismiss_popups_and_interstitials(driver)
        shot = folder / ("".join(c if c.isalnum() or c in " -_" else "_" for c in item["item_name"]) + ".png")
        quoted = None
        try:
            capture_evidence(driver, shot, interactive=False, source_url=item["link"])
            def read_price(d):
                if vendor_key(vendor) == "digikey":
                    try:
                        return (digikey_quote.read_product_price(d, item["quantity"]),)
                    except ValueError:
                        return None
                value = price_scraper.parse_price(price_scraper.scrape_price_from_driver(d))
                return None if value is None else (money(value),)
            quoted = WebDriverWait(driver, 5, ignored_exceptions=(StaleElementReferenceException,)).until(read_price)[0]
        except (BrowserChallenge, TimeoutException, ValueError):
            print("Price unavailable. You can enter the vendor's price or replace this product before cart preparation.")
        item["quoted_unit_cost"] = None if quoted is None else float(quoted)
        item.pop("quoted_total", None)
        if quoted is not None:
            item["quoted_total"] = float(quoted * item["quantity"])
            print(f"Approved: ${money(item['cost'])}/unit | Product page: ${quoted}/unit")
    quote_review(items, vendor)


def verify_digikey_cart_with_retry(driver, items, folder):
    """Read the native cart first; manual transcription is an explicit fallback."""
    while True:
        capture_evidence(driver, folder / "cart.png", interactive=True)
        reason = "The cart did not finish loading."
        def read(d):
            nonlocal reason
            try:
                return digikey_quote.read_cart(d)
            except ValueError as error:
                reason = str(error)
                return False
        mismatch = False
        try:
            snapshot = WebDriverWait(driver, 5, ignored_exceptions=(StaleElementReferenceException,)).until(read)
            digikey_quote.reconcile_cart(items, snapshot)
            return snapshot
        except digikey_quote.DigiKeyCartMismatch as error:
            reason, mismatch = str(error), True
        except TimeoutException:
            pass
        diagnostic = save_page_screenshot(driver, folder / "cart_diagnostics" / "digikey_verification.png", full_page=False)
        print(f"\nCould not automatically verify the DigiKey quote: {reason}\nDiagnostic: {diagnostic}\n"
              "Chrome is still open. Correct the cart or wait for it to load, then retry.")
        prompt = ("Enter to retry reading the cart (or 'cancel'): " if mismatch else
                  "Enter to retry reading the cart, 'manual' to enter its quote yourself, or 'cancel': ")
        while True:
            action = input(prompt).strip().lower()
            if action in ("cancel", "q", "quit"):
                raise ValueError("DigiKey cart verification cancelled; no Engage request was prepared.")
            if not action:
                break
            if action == "manual" and not mismatch:
                return None
            print("Correct the cart and press Enter, or type 'cancel'." if mismatch else
                  "Press Enter, type 'manual', or type 'cancel'.")


def prepare_cart(items, vendor, order_id, source="automated", *, quote_review=None, save_share_url=None):
    folder = Path("screenshots", order_id).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    key = vendor_key(vendor)
    extension = share_a_cart.find_share_a_cart_extension()
    if extension:
        if extension.endswith(".crx"):
            options.add_extension(extension)
        else:
            options.add_argument(f"--load-extension={extension}")
    profile = cart_profile(key)
    options.add_argument(f"--user-data-dir={profile}")
    print(f"Cart Chrome profile: {profile}\n"
          "This dedicated profile retains your vendor sign-in and Share-A-Cart extension across runs.")
    if source == "personal":
        print("Personal cart: sign into your vendor account in this Chrome window.")
    driver = webdriver.Chrome(service=Service(), options=options)
    if hasattr(driver, "execute_cdp_cmd"):
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            })
        except Exception:
            pass
    driver.set_page_load_timeout(30)
    try:
        if quote_review:
            review_product_prices_before_cart(driver, items, vendor, folder, quote_review)
        if key == "amazon" and source == "automated":
            additions = amazon_items_to_add(driver, items, folder)
            for i, item in enumerate(additions, 1):
                print(f"\nProduct {i}/{len(additions)}: {item['item_name']} (quantity {item['quantity']})")
                url = item["link"]
                if not url.startswith("https://") or not price_scraper.extract_amazon_asin(url):
                    raise ValueError("Automated Amazon carts require an Amazon product URL for every item.")
                navigate_for_evidence(driver, url)
                price_scraper.dismiss_popups_and_interstitials(driver)
                shot = folder / ("".join(c if c.isalnum() or c in " -_" else "_" for c in item["item_name"]) + ".png")
                capture_evidence(driver, shot, interactive=True)
                item["resolved_url"] = driver.current_url
                item["asin"] = price_scraper.extract_amazon_asin(driver.current_url) or price_scraper.extract_amazon_asin(url)
                quantity, limited, reason = price_scraper.check_and_set_amazon_quantity(driver, item["quantity"], item["item_name"])
                if limited or quantity != item["quantity"]:
                    raise ValueError(f"{item['item_name']}: requested {item['quantity']}, available {quantity}: {reason}. "
                                     "Update the Ordering quantity or choose a substitute, then rerun. "
                                     "Use --cart-source personal to build the cart in your signed-in account.")
                buttons = driver.find_elements(By.ID, "add-to-cart-button")
                button = next((b for b in buttons if b.is_displayed() and b.is_enabled()), None)
                add_amazon_item_to_cart(driver, button, item["item_name"], folder)

        if key == "digikey" and source == "automated":
            prepare_digikey_items(driver, items, folder)

        cart_url = {"amazon": "https://www.amazon.com/gp/cart/view.html",
                    "digikey": "https://www.digikey.com/ordering/shoppingcart"}.get(key)
        navigate_for_evidence(driver, cart_url or items[0]["link"])
        if source == "personal" or key != "amazon":
            print("\nCheck the cart in the open Chrome window against this order. "
                  "Keep items already added; add only what is missing:")
            for item in items:
                print(f"  {item['quantity']} x {item['item_name']}\n    {item['link']}")
        print("\nCheck stock, seller quantity limits, selected cart items, and delivery charges.")
        if key != "digikey" or source == "personal":
            input("Press Enter when the vendor cart is ready for verification: ")
        else:
            print("Reading the DigiKey cart automatically…")
        snapshot = None
        if key == "amazon":
            snapshot = verify_amazon_cart_with_retry(driver, items, folder)
            screenshot = str(folder / "cart.png")
            subtotal = snapshot["subtotal"]
            print(f"Verified Amazon items and quantities. Subtotal: ${subtotal}")
        elif key == "digikey":
            snapshot = verify_digikey_cart_with_retry(driver, items, folder)
            screenshot = str(folder / "cart.png")
            if snapshot is not None:
                subtotal = snapshot["subtotal"]
                print(f"Verified DigiKey products, quantities and prices. Subtotal: ${subtotal}")
                for item in items:
                    print(f"  {item['quantity']} x ${item['quoted_unit_cost']} = ${money(item['quoted_total'])} — {item['item_name']}")
            else:
                subtotal = prompt_manual_cart_quote(items)
                if input("Do the cart items and quantities match the listed order? [y/N]: ").strip().lower() not in ("y", "yes"):
                    raise ValueError("Vendor cart quantities were not confirmed.")
        else:
            screenshot = capture_evidence(driver, folder / "cart.png", interactive=True)
            subtotal = prompt_manual_cart_quote(items)
            if input("Do the cart items and quantities match the listed order? [y/N]: ").strip().lower() not in ("y", "yes"):
                raise ValueError("Vendor cart quantities were not confirmed.")

        if quote_review:
            quote_review(items, vendor)

        automatic_charges = snapshot is not None and key == "digikey" and digikey_quote.complete_charges(snapshot)
        if automatic_charges:
            shipping, tax, total = (snapshot[k] for k in ("shipping", "tax", "total"))
            tax_label = f"tax ${tax}" if snapshot.get("tax_displayed") else "no separate tax line in the displayed total"
            print(f"Read vendor charges: shipping ${shipping}; {tax_label}; total ${total}.")
            if snapshot.get("estimated"):
                print("DigiKey labels these charges as estimates. Review them before continuing to Engage.")
        while not automatic_charges:
            shipping = prompt_money("Shipping shown by vendor (Enter for $0): $", default="0")
            tax = prompt_money("Tax shown by vendor (Enter for $0): $", default="0")
            expected = subtotal + shipping + tax
            total = prompt_money(f"Final vendor cart/checkout total including shipping/tax "
                                 f"(expected ${expected}; enter amount or 'cancel'): $")
            if total == expected:
                break
            print(f"Vendor total ${total} differs from merchandise ${subtotal} + shipping ${shipping} "
                  f"+ tax ${tax} = ${expected}. Check the vendor's charges and re-enter them.\n"
                  "If merchandise prices changed, type 'cancel' and rerun to refresh the quote.")

        # Share the actual vendor cart for personal mode and DigiKey. The payload
        # endpoint cannot establish seller limits or validate DigiKey cart contents.
        auto_url = None
        if key == "amazon" and source == "automated":
            auto_url = share_a_cart.create_share_a_cart_link(items, vendor, f"MRG {order_id}")
        if key == "digikey":
            print("DigiKey: use the Share-A-Cart Chrome extension to create the link. The recipient needs it to load the cart too.")
        if source == "personal" or not auto_url:
            print("Create a link with Share-A-Cart in this Chrome window. Install the extension here if needed.")
        share_url = share_a_cart.prompt_for_share_a_cart(len(items), vendor, auto_url, required=key in ("amazon", "digikey"))
        if key in ("amazon", "digikey") and not share_url:
            raise ValueError("A Share-A-Cart link from the verified cart is required.")
        if share_url:
            recovery = folder / "share_a_cart.json"
            recovery.write_text(json.dumps({"order_id": order_id, "vendor": vendor, "share_url": share_url}, indent=2), encoding="utf-8")
            if save_share_url:
                while True:
                    try:
                        save_share_url(share_url)
                        break
                    except (OSError, ValueError) as error:
                        print(f"\nShare-A-Cart link was not saved to Ordering: {error}\n"
                              f"Keep this URL: {share_url}\nRecovery file: {recovery}\n"
                              "The browser is still open. Close Excel and resolve the workbook issue before retrying.")
                        if input("Enter to retry saving the link (or 'cancel'): ").strip().lower() in ("cancel", "q", "quit"):
                            raise ValueError("Share-A-Cart link was not saved to Excel; Engage preparation cancelled.") from error
        cart = {"driver": driver, "folder": folder, "screenshot": screenshot,
                "share_url": share_url, "subtotal": subtotal, "shipping": shipping,
                "tax": tax, "total": total, "snapshot": snapshot, "vendor_key": key}
        if key == "digikey":
            cart = digikey_quote.procurement_quote(cart)
            print(f"\nDigiKey vendor quote: ${cart['vendor_total']} (shipping ${cart['vendor_shipping']}).\n"
                  f"{cart['shipping_basis']}. Requested shipping: $0.00.\n"
                  f"Amount for Engage: ${cart['total']} = merchandise ${cart['subtotal']} + tax ${cart['tax']}.\n"
                  "The comparison workbook retains the vendor estimate and this shipping adjustment.")
        return cart
    except BaseException:
        driver.quit()
        raise


def recheck_cart(cart, items):
    """Recheck the supported vendor quote before upload, retaining the cart session."""
    driver = cart["driver"]
    if cart["vendor_key"] == "amazon":
        navigate_for_evidence(driver, "https://www.amazon.com/gp/cart/view.html")
    else:
        driver.refresh()
    capture_evidence(driver, cart["screenshot"], interactive=True)
    if cart["vendor_key"] == "amazon":
        fresh = read_amazon_cart(driver)
        require_matching_total(cart["subtotal"], fresh["subtotal"])
        canonical = lambda snap: sorted((i["asin"], i["quantity"], i["unit_price"]) for i in snap["items"])
        if canonical(fresh) != canonical(cart["snapshot"]):
            raise ValueError("Amazon cart items, quantities, or prices changed after review. Rerun to refresh the report and Share-A-Cart.")
        reconcile_amazon_cart(items, fresh)
    elif cart["vendor_key"] == "digikey" and cart["snapshot"] is not None:
        fresh = digikey_quote.read_cart(driver)
        canonical = lambda snap: sorted((i["product_id"], i["quantity"], i["unit_price"], i["line_total"]) for i in snap["items"])
        if fresh["subtotal"] != cart["subtotal"] or canonical(fresh) != canonical(cart["snapshot"]):
            raise ValueError("DigiKey cart products, quantities, or prices changed after review. Rerun to refresh the report and Share-A-Cart.")
        digikey_quote.reconcile_cart(items, fresh)
        if digikey_quote.complete_charges(cart["snapshot"]):
            if not digikey_quote.complete_charges(fresh):
                raise ValueError("DigiKey charges changed after review. Rerun to refresh the quote before uploading.")
            payable = digikey_quote.procurement_quote(fresh) if cart.get("shipping_basis") else fresh
            if any(payable[k] != cart[k] for k in ("shipping", "tax", "total")):
                raise ValueError("DigiKey charges changed after review. Rerun to refresh the quote before uploading.")
            if cart.get("shipping_basis"):
                cart.update(vendor_shipping=payable["vendor_shipping"],
                            vendor_total=payable["vendor_total"], snapshot=fresh)
            print(f"Rechecked DigiKey merchandise/tax: vendor total ${fresh['total']}; "
                  f"Engage amount ${payable['total']}.")
            return
    else:
        require_matching_total(prompt_money("Reconfirm current vendor merchandise subtotal before upload (or 'cancel'): $"), cart["subtotal"])
        if input("Cart quantities still match? [y/N]: ").strip().lower() not in ("y", "yes"):
            raise ValueError("Cart quantities changed.")
    displayed_total = cart.get("vendor_total", cart["total"]) if cart.get("shipping_basis") else cart["total"]
    require_matching_total(prompt_money("Reconfirm final vendor total including shipping/tax before upload (or 'cancel'): $"), displayed_total)
