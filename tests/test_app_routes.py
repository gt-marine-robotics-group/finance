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
