import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engage_bill_lookup import build_bill_url, find_line_number_in_bill_html, lookup_bill_item_locations


def test_build_bill_url_uses_engage_edit_pattern():
    assert build_bill_url("12345") == (
        "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/"
        "budgeting/requests#/edit/12345"
    )


def test_find_line_number_in_bill_html_matches_item_name():
    html = """
    <div>
      <a ng-click="editLineItem(lineItem)">First Item</a>
      <a ng-click="editLineItem(lineItem)">Valve Assembly</a>
      <a ng-click="editLineItem(lineItem)">Motor Controller</a>
    </div>
    """

    assert find_line_number_in_bill_html(html, "Valve Assembly") == 2
    assert find_line_number_in_bill_html(html, "missing item") is None


def test_find_line_number_in_bill_html_prioritizes_exact_over_substring():
    html = """
    <div>
      <a ng-click="editLineItem(lineItem)">USB Antenna adapter</a>
      <a ng-click="editLineItem(lineItem)">Antenna</a>
      <a ng-click="editLineItem(lineItem)">Toggle Switch</a>
    </div>
    """
    assert find_line_number_in_bill_html(html, "Antenna") == 2
    assert find_line_number_in_bill_html(html, "USB Antenna adapter") == 1
    assert find_line_number_in_bill_html(html, "Toggle Switch") == 3


def test_find_best_item_match_prevents_substring_hijacking():
    from engage_bill_lookup import find_best_item_match

    candidates = {
        "usb antenna adapter": {"section": "B06", "section_line_number": 31, "name": "usb antenna adapter"},
        "antenna": {"section": "B06", "section_line_number": 30, "name": "antenna"},
        "toggle switch": {"section": "B06", "section_line_number": 29, "name": "toggle switch"},
    }

    match_antenna = find_best_item_match("Antenna", candidates)
    match_usb = find_best_item_match("USB Antenna adapter", candidates)
    match_toggle = find_best_item_match("Toggle Switch", candidates)

    assert match_antenna["name"] == "antenna"
    assert match_antenna["section_line_number"] == 30
    assert match_usb["name"] == "usb antenna adapter"
    assert match_usb["section_line_number"] == 31
    assert match_toggle["name"] == "toggle switch"
    assert match_toggle["section_line_number"] == 29
