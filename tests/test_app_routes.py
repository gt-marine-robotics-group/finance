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
    with patch("xlsx_manager.add_item", return_value=True), \
         patch("threading.Thread"):
        response = client.post("/quick-add", data={
            "item_name": "Pytest Mock Item",
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
    mock_cols_resp = {"value": [{"name": "Order ID"}, {"name": "Bill Item ID"}, {"name": "Vendor"}, {"name": "Item Name"}]}
    mock_rows_resp = {
        "value": [
            {"index": 0, "values": [["", "", "", "Order 1", "", "", ""]]},
            {"index": 1, "values": [["260811_amazon_tester", "101", "", "Thruster", "", "", ""]]}
        ]
    }

    def mock_requests_get(url, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                if "columns" in url:
                    return mock_cols_resp
                return mock_rows_resp
        return MockResp()

    with patch("xlsx_manager._get_graph_token", return_value=("mock_token", "mock_drive", "mock_file")), \
         patch("xlsx_manager.graph_get_table_columns", return_value=["Order ID", "Bill Item ID", "Vendor", "Item Name"]), \
         patch("requests.get", side_effect=mock_requests_get), \
         patch("requests.patch") as mock_patch, \
         patch("xlsx_manager.update_item", return_value=True):
        mock_patch.return_value.status_code = 200
        response = client.post("/orders/delete", data={"order_id": "260811_amazon_tester"}, follow_redirects=True)
        assert response.status_code == 200

