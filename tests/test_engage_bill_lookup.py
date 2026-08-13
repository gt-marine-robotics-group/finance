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


def test_lookup_bill_item_locations_maps_section_and_line():
    class FakeElement:
        def __init__(self, text):
            self.text = text

    class FakeDriver:
        def __init__(self):
            self.page_url = None

        def get(self, url):
            self.page_url = url

        def find_elements(self, by, value):
            return [FakeElement("Hardware"), FakeElement("Software")]

    driver = FakeDriver()
    section = FakeElement("Hardware")
    section.find_element = lambda *args, **kwargs: FakeContainer([
        FakeElement("First Item"),
        FakeElement("Second Item"),
    ])

    class FakeContainer:
        def __init__(self, items):
            self.items = items
        def find_elements(self, by, value):
            return self.items

    result = lookup_bill_item_locations(driver, "376945", ["Second Item"])
    assert result == {}
