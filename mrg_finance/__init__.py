"""
MRG Finance Package
Automated financial workflows, Engage submissions, and spreadsheet integrations
for the Georgia Tech Marine Robotics Group.
"""

__version__ = "0.2.7"

from . import (
    spreadsheet_utils,
    price_scraper,
    order_excel_builder,
    share_a_cart,
    engage_bill_lookup,
    automation,
    automation_purchase,
    automation_screenshots,
    review_server,
    cli,
)

__all__ = [
    "spreadsheet_utils",
    "price_scraper",
    "order_excel_builder",
    "share_a_cart",
    "engage_bill_lookup",
    "automation",
    "automation_purchase",
    "automation_screenshots",
    "review_server",
    "cli",
]
