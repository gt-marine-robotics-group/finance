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


def test_generate_amazon_cart_url():
    items = [
        {"Link": "https://www.amazon.com/dp/B08N5WRWNW", "Quantity": 2},
        {"Link": "https://www.amazon.com/dp/B012345678", "Quantity": 1},
        {"Link": "https://www.mcmaster.com/123", "Quantity": 5},
    ]
    cart_url = price_scraper.generate_amazon_cart_url(items)
    assert "ASIN.1=B08N5WRWNW" in cart_url
    assert "Quantity.1=2" in cart_url
    assert "ASIN.2=B012345678" in cart_url
    assert "Quantity.2=1" in cart_url
