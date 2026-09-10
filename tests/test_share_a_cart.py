import pytest
import os
import tempfile
from share_a_cart import normalize_share_a_cart_url, find_share_a_cart_extension

def test_normalize_share_a_cart_url():
    # Full URL preserved
    assert normalize_share_a_cart_url("https://shareacart.net/get/ABC1234") == "https://shareacart.net/get/ABC1234"
    assert normalize_share_a_cart_url("http://shareacart.net/cart/XYZ987") == "http://shareacart.net/cart/XYZ987"
    
    # Standalone code transformed
    assert normalize_share_a_cart_url("ABC1234") == "https://shareacart.net/get/ABC1234"
    assert normalize_share_a_cart_url("shareacart.net/get/ABC1234") == "https://shareacart.net/get/ABC1234"
    
    # Whitespace and empty handling
    assert normalize_share_a_cart_url("  ABC1234  ") == "https://shareacart.net/get/ABC1234"
    assert normalize_share_a_cart_url("") is None
    assert normalize_share_a_cart_url("   ") is None
    assert normalize_share_a_cart_url(None) is None

def test_find_share_a_cart_extension(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock extensions directory
        ext_dir = os.path.join(tmpdir, "extensions")
        os.makedirs(ext_dir, exist_ok=True)
        
        crx_path = os.path.join(ext_dir, "share-a-cart.crx")
        with open(crx_path, "w") as f:
            f.write("mock crx")
            
        monkeypatch.setattr("os.path.dirname", lambda _: tmpdir)
        found = find_share_a_cart_extension()
        assert found == crx_path

def test_create_share_a_cart_link(monkeypatch):
    from share_a_cart import create_share_a_cart_link

    class MockResponse:
        status_code = 200
        def json(self):
            return {"cartid": "TEST1234"}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: MockResponse())
    
    items = [
        {"item_name": "16 awg wire", "link": "https://www.amazon.com/dp/B08N5WRWNW", "quantity": 3, "cost": 32.99}
    ]
    cart_url = create_share_a_cart_link(items, vendor_name="amazon")
    assert cart_url == "https://share-a-cart.com/get/TEST1234"
