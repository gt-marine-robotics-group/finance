from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mrg_finance import browser_profiles, purchase_cart


def test_profile_is_stable_across_working_folders_and_keeps_extension(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    profile = browser_profiles.cart_profile("amazon")
    extension = profile / "Default" / "Extensions" / "share-a-cart" / "1.0"
    extension.mkdir(parents=True)
    (extension / "manifest.json").write_text('{"name": "Share-A-Cart"}')
    monkeypatch.chdir(second)
    assert browser_profiles.cart_profile("amazon") == profile
    assert (extension / "manifest.json").exists()
    assert browser_profiles.cart_profile("digikey") != profile


@pytest.mark.parametrize("vendor", ["amazon", "digikey"])
def test_old_profile_migration_preserves_extensions_and_original(monkeypatch, tmp_path, vendor):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / ".mrg-finance-browser"
    if vendor == "digikey":
        legacy /= "digikey"
    extension = legacy / "Default" / "Extensions" / "share-a-cart"
    extension.mkdir(parents=True)
    (extension / "manifest.json").write_text("saved extension")
    (legacy / "Local State").write_text("saved profile state")
    (legacy / "Default" / "Preferences").write_text("saved preferences")
    (legacy / "DevToolsActivePort").write_text("stale debugging port")
    (legacy / "evidence").mkdir()
    (legacy / "evidence" / "other-profile").write_text("not the cart profile")
    target = browser_profiles.cart_profile(vendor)
    assert (target / "Default" / "Extensions" / "share-a-cart" / "manifest.json").read_text() == "saved extension"
    assert (target / "Default" / "Preferences").read_text() == "saved preferences"
    assert not (target / "DevToolsActivePort").exists()
    assert not (target / "evidence").exists()
    assert (legacy / "Default" / "Preferences").exists()
    # Subsequent runs keep the active profile rather than overwriting with backup.
    (target / "Default" / "Preferences").write_text("new preferences")
    assert browser_profiles.cart_profile(vendor) == target
    assert (target / "Default" / "Preferences").read_text() == "new preferences"


def test_open_legacy_profile_is_not_copied(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / ".mrg-finance-browser"
    (legacy / "Default").mkdir(parents=True)
    (legacy / "SingletonLock").symlink_to("host-999")
    with pytest.raises(ValueError, match="Close the previous"):
        browser_profiles.cart_profile("amazon")
    assert not (browser_profiles.profile_root() / "amazon").exists()


@pytest.fixture
def amazon_driver(monkeypatch):
    driver = MagicMock()
    driver.find_element.return_value.text = "Amazon Cart"
    monkeypatch.setattr(purchase_cart, "navigate_for_evidence", lambda *a: None)
    monkeypatch.setattr(purchase_cart, "capture_evidence", lambda *a, **kw: None)
    monkeypatch.setattr(purchase_cart, "_cart_count", lambda d: 2)
    return driver


def item(asin="B012345678", qty=2):
    return {"link": f"https://www.amazon.com/dp/{asin}", "quantity": qty, "item_name": "Part"}


def test_existing_complete_amazon_order_is_reused_without_addition(monkeypatch, amazon_driver, tmp_path):
    monkeypatch.setattr(purchase_cart, "read_amazon_cart", lambda d: {
        "items": [{"asin": "B012345678", "quantity": 2}]})
    assert purchase_cart.amazon_items_to_add(amazon_driver, [item()], tmp_path) == []


def test_partial_amazon_cart_adds_only_absent_products(monkeypatch, amazon_driver, tmp_path):
    monkeypatch.setattr(purchase_cart, "read_amazon_cart", lambda d: {
        "items": [{"asin": "B012345678", "quantity": 2}]})
    missing = item("B087654321", 5)
    assert purchase_cart.amazon_items_to_add(amazon_driver, [item(), missing], tmp_path) == [missing]


@pytest.mark.parametrize("snapshot", [
    {"items": [{"asin": "B012345678", "quantity": 1}]},
    {"items": [{"asin": "B087654321", "quantity": 2}]},
])
def test_conflicting_amazon_cart_is_preserved_for_manual_repair(monkeypatch, amazon_driver, tmp_path, snapshot):
    monkeypatch.setattr(purchase_cart, "read_amazon_cart", lambda d: snapshot)
    assert purchase_cart.amazon_items_to_add(amazon_driver, [item()], tmp_path) == []


def test_unreadable_amazon_cart_does_not_blindly_append(monkeypatch, amazon_driver, tmp_path):
    monkeypatch.setattr(purchase_cart, "read_amazon_cart", MagicMock(side_effect=ValueError("quantity missing")))
    assert purchase_cart.amazon_items_to_add(amazon_driver, [item()], tmp_path) == []


def test_empty_amazon_cart_groups_same_product_across_order_rows(monkeypatch, amazon_driver, tmp_path):
    amazon_driver.find_element.return_value.text = "Your Amazon Cart is empty"
    monkeypatch.setattr(purchase_cart, "_cart_count", lambda d: 0)
    additions = purchase_cart.amazon_items_to_add(amazon_driver, [item(), item(qty=3)], tmp_path)
    assert len(additions) == 1
    assert additions[0]["quantity"] == 5
