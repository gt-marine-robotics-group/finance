"""Prepare DigiKey carts through the visible website, with manual challenge recovery."""

import re

from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException,
    StaleElementReferenceException, TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from . import price_scraper
from .screenshot_capture import capture_evidence, navigate_for_evidence, save_page_screenshot


CART_URL = "https://www.digikey.com/ordering/shoppingcart"


def _cart_count(driver):
    counts = set()
    for link in driver.find_elements(By.CSS_SELECTOR, "a[href*='shoppingcart']"):
        if not link.is_displayed():
            continue
        text = " ".join(link.text.split())
        match = re.fullmatch(r"(?:your item\(s\)\s*)?(\d+)(?:\s*items?(?:\(s\))?)?", text, re.I)
        if match:
            counts.add(int(match[1]))
    return counts.pop() if len(counts) == 1 else None


def _manual_add(driver, item, folder, reason):
    diagnostic = save_page_screenshot(driver, folder / "cart_diagnostics" / "digikey_add.png", full_page=False)
    print(f"\nDigiKey could not confirm adding {item['item_name']}: {reason}\n"
          f"Diagnostic: {diagnostic}\n"
          "The browser is still open. Complete any verification or vendor prompt, then check the cart.\n"
          f"Ensure it contains {item['quantity']} of this product:\n  {item['link']}\n"
          "If it is already in the cart at that quantity, leave it there and press Enter. "
          "Otherwise add or correct it in Chrome, then press Enter.")
    if input("Finish adding this DigiKey item, then Enter (or 'cancel'): ").strip().lower() in ("cancel", "q", "quit"):
        raise ValueError("DigiKey cart preparation cancelled; no Engage request was prepared.")


def add_digikey_item(driver, item, folder):
    """Add once at the requested quantity; never bypass a challenge or guess controls."""
    navigate_for_evidence(driver, item["link"])
    price_scraper.dismiss_popups_and_interstitials(driver)
    name = "".join(c if c.isalnum() or c in " -_" else "_" for c in item["item_name"])
    capture_evidence(driver, folder / (name + ".png"), interactive=True)
    before = _cart_count(driver)

    def controls(d):
        buttons = [e for e in d.find_elements(By.XPATH,
            "//button[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='add to cart'] | "
            "//input[translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='add to cart']")
            if e.is_displayed() and e.is_enabled()]
        if len(buttons) != 1:
            return False
        button = buttons[0]
        quantity_selector = (
            "input[aria-label='Quantity' i], input[placeholder='Quantity' i], "
            "input[name='quantity' i], input[id*='quantity' i], input[data-testid*='quantity' i], input[type='number']")
        # Related-product tables also have quantity fields. Prefer the buy box
        # around the actual Add to Cart button rather than every input on page.
        for scope in button.find_elements(By.XPATH, "./ancestor::*[.//input][1]"):
            quantities = [e for e in scope.find_elements(By.CSS_SELECTOR, quantity_selector)
                          if e.is_displayed() and e.is_enabled()]
            if not quantities:
                quantities = [e for e in scope.find_elements(By.CSS_SELECTOR,
                    "input:not([type='hidden']):not([type='checkbox']):not([type='radio'])"
                    ":not([type='search']):not([type='submit']):not([type='button'])")
                    if e.is_displayed() and e.is_enabled()]
            if len(quantities) == 1:
                return quantities[0], button
            if quantities:
                return False
        quantities = [e for e in d.find_elements(By.CSS_SELECTOR, quantity_selector)
                      if e.is_displayed() and e.is_enabled()]
        return (quantities[0], button) if len(quantities) == 1 else False

    try:
        quantity, button = WebDriverWait(driver, 10, ignored_exceptions=(StaleElementReferenceException,)).until(controls)
        maximum = quantity.get_attribute("max")
        if maximum and maximum.isdigit() and item["quantity"] > int(maximum):
            raise ValueError(f"DigiKey limits {item['item_name']} to {maximum}; requested {item['quantity']}. "
                             "Correct the order quantity or replace its product URL before continuing.")
        quantity.clear()
        quantity.send_keys(str(item["quantity"]))
        quantity.send_keys(Keys.TAB)
        # A React update can replace the buy box when quantity changes.
        quantity, button = WebDriverWait(driver, 10, ignored_exceptions=(StaleElementReferenceException,)).until(controls)
        if quantity.get_attribute("value") != str(item["quantity"]):
            _manual_add(driver, item, folder, "quantity field did not retain the requested value")
            return
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'nearest'});", button)
        button.click()
        # The click itself may cause a verification page. Keep its diagnostics
        # separate and let the purchaser solve it in this same session.
        capture_evidence(driver, folder / (name + "_after_add.png"), interactive=True)

        def added(d):
            count = _cart_count(d)
            if before is not None and count is not None and count > before:
                return True
            for alert in d.find_elements(By.CSS_SELECTOR, "[role='alert'], [role='status'], [aria-live='polite']"):
                if (alert.is_displayed()
                    and not re.search(r"\b(?:not|unable|failed|cannot|could not)\b", alert.text, re.I)
                    and re.search(r"\b(?:successfully added|added to (?:your )?cart)\b", alert.text, re.I)):
                    return True
            return False

        WebDriverWait(driver, 15, ignored_exceptions=(StaleElementReferenceException,)).until(added)
    except (TimeoutException, ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException) as error:
        _manual_add(driver, item, folder, type(error).__name__)


def prepare_digikey_items(driver, items, folder):
    navigate_for_evidence(driver, CART_URL)
    capture_evidence(driver, folder / "digikey_cart_before.png", interactive=True)
    if "your shopping cart is empty" not in driver.find_element(By.TAG_NAME, "body").text.lower():
        print("Existing DigiKey cart retained to avoid adding duplicate quantities.\n"
              "Correct its items and quantities to match this order before verification.")
        return
    for n, item in enumerate(items, 1):
        print(f"\nDigiKey product {n}/{len(items)}: {item['item_name']} (quantity {item['quantity']})")
        add_digikey_item(driver, item, folder)
