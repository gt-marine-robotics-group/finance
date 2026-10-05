"""Prepare and verify a vendor cart before opening the Engage form."""

from decimal import Decimal
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from . import price_scraper, share_a_cart
from .purchase_validation import money, read_amazon_cart, reconcile_amazon_cart, require_matching_total
from .screenshot_capture import capture_evidence, navigate_for_evidence
from .vendor_payee import vendor_key


def prepare_cart(items, vendor, order_id, source="automated"):
    folder = Path("screenshots", order_id).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument("--window-size=1600,1000")
    extension = share_a_cart.find_share_a_cart_extension()
    if extension:
        if extension.endswith(".crx"):
            options.add_extension(extension)
        else:
            options.add_argument(f"--load-extension={extension}")
    if source == "personal":
        options.add_argument(f"--user-data-dir={Path('.mrg-finance-browser').resolve()}")
        print("Personal cart: sign into your Amazon account in this Chrome window. "
              "The dedicated profile remembers your sign-in and extensions.")
    driver = webdriver.Chrome(service=Service(), options=options)
    driver.set_page_load_timeout(30)
    try:
        key = vendor_key(vendor)
        if key == "amazon" and source == "automated":
            for i, item in enumerate(items, 1):
                print(f"\nProduct {i}/{len(items)}: {item['item_name']} (quantity {item['quantity']})")
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
                if not buttons:
                    raise ValueError(f"Add to Cart unavailable for {item['item_name']}.")
                buttons[0].click()

        cart_url = {"amazon": "https://www.amazon.com/gp/cart/view.html",
                    "digikey": "https://www.digikey.com/ordering/shoppingcart"}.get(key)
        navigate_for_evidence(driver, cart_url or items[0]["link"])
        if source == "personal" or key != "amazon":
            print("\nBuild the cart in the open Chrome window using these items only:")
            for item in items:
                print(f"  {item['quantity']} x {item['item_name']}\n    {item['link']}")
        print("\nCheck stock, seller quantity limits, selected cart items, and delivery charges.")
        input("Press Enter when the vendor cart is ready for verification: ")
        screenshot = capture_evidence(driver, folder / "cart.png", interactive=True)
        snapshot = None
        if key == "amazon":
            snapshot = read_amazon_cart(driver)
            reconcile_amazon_cart(items, snapshot)
            subtotal = snapshot["subtotal"]
            print(f"Verified Amazon items and quantities. Subtotal: ${subtotal}")
        else:
            print("Verify each quoted unit price against the vendor cart:")
            for item in items:
                item["quoted_unit_cost"] = float(money(input(f"  {item['item_name']} x {item['quantity']}, unit price: $")))
                item["quoted_total"] = float(money(Decimal(str(item["quoted_unit_cost"])) * item["quantity"]))
            subtotal = sum((money(i["quoted_total"]) for i in items), Decimal("0"))
            require_matching_total(input("Vendor cart merchandise subtotal: $"), subtotal)
            if input("Do the cart items and quantities match the listed order? [y/N]: ").strip().lower() not in ("y", "yes"):
                raise ValueError("Vendor cart quantities were not confirmed.")

        shipping = money(input("Shipping shown by vendor (Enter for $0): $").strip() or "0")
        tax = money(input("Tax shown by vendor (Enter for $0): $").strip() or "0")
        total = money(input(f"Final vendor cart/checkout total, including shipping and tax (${subtotal + shipping + tax}): $"))
        require_matching_total(total, subtotal + shipping + tax)

        # Share the actual vendor cart for personal mode and DigiKey. The payload
        # endpoint cannot establish seller limits or validate DigiKey cart contents.
        auto_url = None
        if key == "amazon" and source == "automated":
            auto_url = share_a_cart.create_share_a_cart_link(items, vendor, f"MRG {order_id}")
        if key == "digikey":
            print("DigiKey: use Share-A-Cart Everything to create the link. The recipient also needs the extension.")
        if source == "personal" or not auto_url:
            print("Create a link with Share-A-Cart in this Chrome window. Install the extension here if needed.")
        share_url = share_a_cart.prompt_for_share_a_cart(len(items), vendor, auto_url)
        if key in ("amazon", "digikey") and not share_url:
            raise ValueError("A Share-A-Cart link from the verified cart is required.")
        return {"driver": driver, "folder": folder, "screenshot": screenshot,
                "share_url": share_url, "subtotal": subtotal, "shipping": shipping,
                "tax": tax, "total": total, "snapshot": snapshot, "vendor_key": key}
    except BaseException:
        driver.quit()
        raise


def recheck_cart(cart, items):
    """Re-read Amazon immediately before upload, while the original cart stays open."""
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
    else:
        require_matching_total(input("Reconfirm current vendor merchandise subtotal before upload: $"), cart["subtotal"])
        if input("Cart quantities still match? [y/N]: ").strip().lower() not in ("y", "yes"):
            raise ValueError("Cart quantities changed.")
    require_matching_total(input("Reconfirm final vendor total including shipping/tax before upload: $"), cart["total"])
