"""
tests/test_price_scraper.py - Unit tests for price_scraper module.
"""

import sys
import os
import pytest

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import price_scraper


def test_parse_price():
    assert price_scraper.parse_price("$19.99") == 19.99
    assert price_scraper.parse_price(" $ 1,234.56 ") == 1234.56
    assert price_scraper.parse_price("Price: 45.50 USD") == 45.50
    assert price_scraper.parse_price(15.75) == 15.75
    assert price_scraper.parse_price("") is None
    assert price_scraper.parse_price(None) is None
    assert price_scraper.parse_price("No numbers here") is None


def test_detect_vendor_from_url():
    assert price_scraper.detect_vendor_from_url("https://www.amazon.com/dp/B08N5WRWNW") == "Amazon"
    assert price_scraper.detect_vendor_from_url("https://www.mcmaster.com/91251A540/") == "McMaster-Carr"
    assert price_scraper.detect_vendor_from_url("https://www.digikey.com/product/123") == "DigiKey"
    assert price_scraper.detect_vendor_from_url("https://unknown-vendor.com/item") == ""


def test_normalize_vendor():
    assert price_scraper.normalize_vendor("amazon") == "Amazon"
    assert price_scraper.normalize_vendor("AMAZON.COM") == "Amazon"
    assert price_scraper.normalize_vendor("mcmaster-carr") == "McMaster-Carr"
    assert price_scraper.normalize_vendor("custom vendor") == "Custom Vendor"
    assert price_scraper.normalize_vendor("") == ""


def test_extract_amazon_asin():
    url1 = "https://www.amazon.com/dp/B08N5WRWNW"
    assert price_scraper.extract_amazon_asin(url1) == "B08N5WRWNW"

    url2 = "https://www.amazon.com/gp/product/B012345678/ref=xyz"
    assert price_scraper.extract_amazon_asin(url2) == "B012345678"

    assert price_scraper.extract_amazon_asin("https://example.com") is None


def test_check_and_set_amazon_quantity():
    class MockElement:
        def __init__(self, tag_name="select", text="", options=None, attributes=None):
            self.tag_name = tag_name
            self.text = text
            self._options = options or []
            self._attributes = attributes or {}

        def get_attribute(self, name):
            return self._attributes.get(name, "")

        def find_elements(self, by, value):
            return self._options

    class MockOption:
        def __init__(self, value):
            self._val = value
        def get_attribute(self, name):
            return self._val if name == "value" else ""

    class MockDriver:
        def __init__(self, avail_text="Only 3 left in stock", options=["1", "2", "3"]):
            self.avail_text = avail_text
            self.options = [MockOption(v) for v in options]

        def find_elements(self, by, value):
            if value == "availability":
                return [MockElement(text=self.avail_text)]
            if value == "quantity":
                return [MockElement(options=self.options)]
            return []

    # Test limit detected when stock is 3 and desired is 10
    driver = MockDriver("Only 3 left in stock")
    qty_set, is_limited, reason = price_scraper.check_and_set_amazon_quantity(driver, desired_qty=10)
    assert is_limited is True
    assert qty_set == 3
    assert "3 left in stock" in reason
