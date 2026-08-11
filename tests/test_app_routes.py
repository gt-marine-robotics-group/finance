"""
tests/test_app_routes.py - Flask routes unit tests.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../web-app")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Password" in response.data or b"password" in response.data


def test_unauthenticated_redirect(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_success(client):
    response = client.post("/login", data={"password": "boats0519", "name": "Test User"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"MRG Purchasing" in response.data


def test_404_handler(client):
    response = client.get("/non-existent-route-1234")
    assert response.status_code == 404
    assert b"404" in response.data


def test_is_bill_locked_logic():
    from routes.bills import is_bill_locked, LOCKED_STATUSES
    assert "bill approved" in LOCKED_STATUSES
    assert "bill submitted" in LOCKED_STATUSES
    # An unknown or empty bill title is not locked
    assert is_bill_locked("NonExistentBillTitle1234") is False


from unittest.mock import patch


def test_quick_add_post_with_quantity(client):
    # Authenticate session
    client.post("/login", data={"password": "boats0519", "name": "Tester"})
    with patch("xlsx_manager.add_item", return_value=True):
        response = client.post("/quick-add", data={
            "item_name": "Pytest Test Motor",
            "quantity": "5",
            "link": "https://www.amazon.com/dp/B08N5WRWNW"
        }, follow_redirects=True)
        assert response.status_code == 200


def test_locked_bill_protection(client):
    """Ensure approved/submitted locked bills reject add/edit/delete mutations."""
    client.post("/login", data={"password": "boats0519", "name": "Tester"})
    with patch("routes.bills.is_bill_locked", return_value=True):
        response = client.post("/bill/Request%201/add-item", data={
            "item_name": "Test Item",
            "cost": "100.00",
            "quantity": "1"
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Cannot add items to an approved or submitted bill" in response.data


def test_max_bill_qty_enforcement(client):
    """Ensure ordering a quantity exceeding max approved bill quantity is rejected."""
    client.post("/login", data={"password": "boats0519", "name": "Tester"})
    mock_order_rows = [{
        "_table_index": 2,
        "Order ID": "260811_vendor_tester",
        "Bill Item ID": "101",
        "Item Name": "Sensor Probe",
        "Quantity": 1,
        "Vendor": "Amazon"
    }]
    mock_bill_items = [{
        "Bill Item ID": "101",
        "Item Name": "Sensor Probe",
        "Quantity": 2.0  # Approved bill quantity max is 2.0
    }]
    with patch("xlsx_manager.graph_get_order_rows", return_value=mock_order_rows), \
         patch("xlsx_manager.read_items", return_value=mock_bill_items):
        response = client.post("/orders/edit-item/2", data={
            "item_name": "Sensor Probe",
            "quantity": "5.0",  # Exceeds max_bill_qty (2.0)
            "vendor": "Amazon",
            "purchaser": "Tester",
            "status": "pending purchase",
            "notes": ""
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"cannot exceed approved bill quantity" in response.data


def test_order_deletion_title_cleanup(client):
    """Ensure deleting an order cleans up title header rows without mutating production spreadsheet."""
    client.post("/login", data={"password": "boats0519", "name": "Tester"})
    mock_order_rows = [
        {"_table_index": 1, "Order ID": "Order 1", "Bill Item ID": "", "Item Name": "", "Vendor": "Order 1"},
        {"_table_index": 2, "Order ID": "260811_amazon_tester", "Bill Item ID": "101", "Item Name": "Thruster", "Vendor": "Amazon"}
    ]
    with patch("xlsx_manager.graph_get_order_rows", return_value=mock_order_rows), \
         patch("xlsx_manager.graph_update_order_item", return_value=True) as mock_update, \
         patch("xlsx_manager.read_items", return_value=[]):
        response = client.post("/orders/delete", data={"order_id": "260811_amazon_tester"}, follow_redirects=True)
        assert response.status_code == 200
        assert mock_update.called

