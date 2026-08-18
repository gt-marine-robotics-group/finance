"""
tests/test_xlsx_manager.py - Unit tests for xlsx_manager module.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../web-app")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import xlsx_manager


def test_column_mapping():
    assert "Bill Item ID" in xlsx_manager.COLUMNS
    assert "Item Name" in xlsx_manager.COLUMNS
    assert "Vendor" in xlsx_manager.COLUMNS
    assert "Total Cost" in xlsx_manager.COLUMNS


def test_cache_invalidation():
    xlsx_manager._cached_items = [{"Item Name": "Test"}]
    xlsx_manager._cached_items_time = 12345
    xlsx_manager._cached_queue = [{"Item Name": "Queue Test"}]
    xlsx_manager._cached_queue_time = 67890

    xlsx_manager.invalidate_all_caches()

    assert xlsx_manager._cached_items == []
    assert xlsx_manager._cached_items_time == 0
    assert xlsx_manager._cached_queue == []
    assert xlsx_manager._cached_queue_time == 0


def test_get_bills_empty():
    # Mock read_items returning empty or sample items
    def mock_read_items():
        return [
            {"Bill Title": "Bill Alpha", "Item Name": "Item 1"},
            {"Bill Title": "Bill Beta", "Item Name": "Item 2"},
            {"Bill Title": "Bill Alpha", "Item Name": "Item 3"},
            {"Bill Title": "", "Item Name": "Item 4"},
        ]

    original_read_items = xlsx_manager.read_items
    try:
        xlsx_manager.read_items = mock_read_items
        bills = xlsx_manager.get_bills()
        assert bills == ["Bill Alpha", "Bill Beta"]
        items_alpha = xlsx_manager.get_items_by_bill("Bill Alpha")
        assert len(items_alpha) == 2
    finally:
        xlsx_manager.read_items = original_read_items


from unittest.mock import patch, MagicMock


def test_sync_pull_rclone_success(tmp_path):
    target_xlsx = tmp_path / "test.xlsx"
    target_xlsx.write_text("test")
    with patch("xlsx_manager.LOCAL_XLSX", str(target_xlsx)), \
         patch("xlsx_manager._run_rclone", return_value=True) as mock_rclone:
        res = xlsx_manager.sync_pull(force=True)
        assert res is True
        assert mock_rclone.called


def test_sync_pull_graph_api_fallback(tmp_path):
    target_xlsx = tmp_path / "test.xlsx"
    target_xlsx.write_text("test")
    with patch("xlsx_manager.LOCAL_XLSX", str(target_xlsx)), \
         patch("xlsx_manager._run_rclone", return_value=False), \
         patch("xlsx_manager._download_xlsx_via_graph_api", return_value=True) as mock_graph:
        res = xlsx_manager.sync_pull(force=True)
        assert res is True
        assert mock_graph.called

