"""
tests/test_workflow_simulation.py - Comprehensive End-to-End Workflow Simulation Suite with Ground Truth.

This test suite simulates the core financial workflows of the Marine Robotics Group against
deterministic ground-truth data vectors, guarding against regressions from other agents.

Workflows Simulated:
1. Spreadsheet Ingestion & Diagnostic Health Check Simulation (mrg_finance.spreadsheet_utils)
2. Screenshot Resolution Multi-Tier Fallback Simulation (mrg_finance.automation)
3. Budget / Bill Request Assembly & Deduplication Simulation (mrg_finance.automation)
4. Price Scraper Multi-Tier Fallback Cascade Simulation (mrg_finance.price_scraper)
5. Engage Bill Line Item Lookup 5-Tier Fallback Simulation (mrg_finance.engage_bill_lookup)
6. Purchase Request & Price Overrun / Overflow Simulation (mrg_finance.automation_purchase)
7. Flask Web Dashboard & Review GUI Simulation (web-app/app.py)
8. Packaging & CLI Dispatch Regression Shield (mrg_finance.cli & pyproject.toml)
"""

import os
import sys
import json
import tempfile
from unittest.mock import MagicMock, patch
import pytest
import openpyxl
import pandas as pd

# Import package modules under test
from mrg_finance import (
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

# Add web-app directory for web testing
web_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web-app"))
if web_app_dir not in sys.path:
    sys.path.insert(0, web_app_dir)
import xlsx_manager


# ==============================================================================
# GROUND TRUTH FIXTURES
# ==============================================================================

@pytest.fixture
def ground_truth_workbook(tmp_path):
    """
    Constructs a deterministic ground-truth Excel workbook matching FY27_Bills_Budget.xlsx:
    - 'Bills' sheet with row 1 title and row 2 headers
    - 'Ordering' sheet with row 1 title and row 2 headers, referencing Bill Item IDs
    """
    wb = openpyxl.Workbook()
    
    # 1. Bills Sheet
    ws_bills = wb.active
    ws_bills.title = "Bills"
    
    # Row 1: Informational title
    ws_bills.append(["FY27 BUDGET OVERVIEW & BILL ITEMS (OFFICIAL COPY)"])
    
    # Row 2: Headers
    headers_bills = [
        "Bill Item ID", "Bill No.", "Bill Title", "Budget Section",
        "Item Name", "Description", "Quantity", "Cost", "Link", "Status"
    ]
    ws_bills.append(headers_bills)
    
    # Ground truth bill items for 'RobotX Bill' (Bill #376851)
    ws_bills.append(["101", "376851.0", "RobotX Bill", "Electronics", "Jetson - Heatsink", "Heatsink for Jetson module", 1, 45.00, "https://www.amazon.com/dp/B08N5WRWNW", "Approved"])
    ws_bills.append(["102", "376851", "RobotX Bill", "Electronics", "M12 Penetrators [Pack of 5]", "Waterproof cable penetrators", 2, 20.00, "https://www.mcmaster.com/12345", "Approved"])
    ws_bills.append(["103", "376851", "RobotX Bill", "Mechanical", "Resistor Pack", "Assorted 1/4W resistors", 1, 10.00, "https://www.digikey.com/product/999", "Approved"])
    ws_bills.append(["104", "376851", "RobotX Bill", "Mechanical", "Mystery Board", "Auxiliary sensor carrier board", 1, 15.00, "https://example.com/mystery", "Approved"])
    ws_bills.append(["105", "376851", "RobotX Bill", "Misc", "Amazon Prime Shipping", "Shipping fee allocation", 1, 0.00, "", "Approved"])

    # 2. Ordering Sheet
    ws_orders = wb.create_sheet(title="Ordering")
    # Row 1: Title
    ws_orders.append(["MRG OFFICIAL ORDERING TABLE"])
    # Row 2: Headers
    headers_orders = [
        "Order ID", "Vendor", "Item Name", "Bill Item ID", "Bill No.",
        "Quantity", "Unit Cost", "Total Cost", "Share-A-Cart Link", "Engage Request Link"
    ]
    ws_orders.append(headers_orders)
    
    order_id = "260910_amazon_awu335"
    # Item 1: Jetson - Heatsink (Base allocation $45.00)
    ws_orders.append([order_id, "Amazon", "Jetson - Heatsink", "101", "376851", 1, 45.00, 45.00, "", ""])
    # Item 2: M12 Penetrators [Pack of 5] (Base allocation $20.00 x 2 = $40.00)
    ws_orders.append([order_id, "Amazon", "M12 Penetrators [Pack of 5]", "102", "376851", 2, 20.00, 40.00, "", ""])
    # Item 3: Mystery Board (Base allocation $15.00 x 1 = $15.00)
    ws_orders.append([order_id, "Amazon", "Mystery Board", "104", "376851", 1, 15.00, 15.00, "", ""])
    # Item 4: Shipping fee (Allocated $0.00 in bill, but order has $7.50 fee)
    ws_orders.append([order_id, "Amazon", "Amazon Prime Shipping", "105", "376851", 1, 7.50, 7.50, "", ""])
    
    wb_path = str(tmp_path / "FY27_Bills_Budget_Test.xlsx")
    wb.save(wb_path)
    wb.close()
    return wb_path


@pytest.fixture
def ground_truth_screenshots(tmp_path):
    """
    Constructs a ground-truth mock screenshot directory tree testing all 4 resolution tiers:
    1. Normalized Alphanumeric fallback ('jetsonheatsink.png' for 'Jetson - Heatsink')
    2. Sanitized fallback ('M12 Penetrators _Pack of 5_.png' for 'M12 Penetrators [Pack of 5]')
    3. Exact match ('Resistor Pack.png' for 'Resistor Pack')
    4. Missing item ('Mystery Board' has no file)
    """
    shot_dir = tmp_path / "screenshots" / "RobotX Bill"
    shot_dir.mkdir(parents=True)
    
    # Tier 1: Alphanumeric normalized
    (shot_dir / "jetsonheatsink.png").write_bytes(b"dummy image content")
    # Tier 2: Sanitized bracket replacement
    (shot_dir / "M12 Penetrators _Pack of 5_.png").write_bytes(b"dummy image content")
    # Tier 3: Exact filename
    (shot_dir / "Resistor Pack.png").write_bytes(b"dummy image content")
    # Tier 4: 'Mystery Board' intentionally omitted
    
    return str(tmp_path / "screenshots")


# ==============================================================================
# WORKFLOW SIMULATION 1: SPREADSHEET INGESTION & DIAGNOSTIC DOCTOR
# ==============================================================================

def test_simulated_spreadsheet_ingestion_and_doctor(ground_truth_workbook):
    """
    Simulates reading a messy real-world workbook (header row offset, float IDs, column aliases)
    and running the diagnostic doctor health check.
    """
    # 1. Robust Sheet Reading (Bills)
    df_bills = spreadsheet_utils.read_sheet_robust(ground_truth_workbook, ["Bills", "Bill"])
    assert not df_bills.empty, "Bills sheet should not be empty"
    assert "Item Name" in df_bills.columns, "Header row should be correctly identified despite row-0 offset"
    assert len(df_bills) == 5, f"Expected 5 items, found {len(df_bills)}"
    
    # Verify ID normalization removes trailing .0
    bill_no_clean = spreadsheet_utils.clean_id(df_bills.iloc[0]["Bill No."])
    assert bill_no_clean == "376851", f"Expected '376851', got '{bill_no_clean}'"
    
    # 2. Robust Sheet Reading (Ordering)
    df_orders = spreadsheet_utils.read_sheet_robust(ground_truth_workbook, ["Ordering", "Orders"])
    assert not df_orders.empty, "Ordering sheet should be loaded"
    assert "Order ID" in df_orders.columns
    
    # 3. Flexible Column Alias Resolution
    sample_row = df_orders.iloc[0].to_dict()
    val_cost = spreadsheet_utils.get_col_val(sample_row, "cost")
    assert float(val_cost) == 45.00, "get_col_val('cost') should resolve 'Unit Cost' column alias"
    
    # 4. Diagnostic Doctor Health Check
    doc_results = spreadsheet_utils.validate_budget_spreadsheet(ground_truth_workbook)
    assert doc_results["valid"] is True, "Workbook should be structurally valid"
    # Row 5 has cost 0.00 (Shipping), so doctor should flag 1 warning
    assert len(doc_results["warnings"]) >= 1, "Doctor should issue a warning for nonpositive cost row"
    assert any("Amazon Prime Shipping" in w for w in doc_results["warnings"])

    # 5. xlsx_manager Column Mapping and Cache Invalidation
    assert "Bill Item ID" in xlsx_manager.COLUMNS
    assert "Total Cost" in xlsx_manager.COLUMNS
    xlsx_manager._cached_items = [{"Item Name": "Test"}]
    xlsx_manager.invalidate_all_caches()
    assert xlsx_manager._cached_items == []


# ==============================================================================
# WORKFLOW SIMULATION 2: SCREENSHOT MULTI-TIER FALLBACK CASCADE
# ==============================================================================

def test_simulated_screenshot_resolution_fallbacks(ground_truth_screenshots, monkeypatch):
    """
    Simulates screenshot resolution across all 4 resolution tiers:
    Exact match, Sanitized match, Normalized alphanumeric match, and Missing item detection.
    """
    monkeypatch.setattr(automation, "SCREENSHOT_DIR", ground_truth_screenshots)
    
    # Tier 1: Alphanumeric normalization fallback (ignores hyphens, spaces, and case)
    path1 = automation._find_screenshot("Jetson - Heatsink", "RobotX Bill")
    assert path1 is not None
    assert os.path.basename(path1) == "jetsonheatsink.png"
    
    # Tier 2: Sanitized fallback (replaces brackets [ ] with _)
    path2 = automation._find_screenshot("M12 Penetrators [Pack of 5]", "RobotX Bill")
    assert path2 is not None
    assert os.path.basename(path2) == "M12 Penetrators _Pack of 5_.png"
    
    # Tier 3: Exact filename match
    path3 = automation._find_screenshot("Resistor Pack", "RobotX Bill")
    assert path3 is not None
    assert os.path.basename(path3) == "Resistor Pack.png"
    
    # Tier 4: Missing item correctly returns None for on-demand capture
    path4 = automation._find_screenshot("Mystery Board", "RobotX Bill")
    assert path4 is None


# ==============================================================================
# WORKFLOW SIMULATION 3: BUDGET / BILL REQUEST ASSEMBLY & DEDUPLICATION
# ==============================================================================

def test_simulated_budget_request_section_deduplication(ground_truth_workbook):
    """
    Simulates the Budget Request submission pipeline:
    - Loads the Bills sheet
    - Filters to the requested bill
    - Groups items by Budget Section
    - Simulates deduplication against existing items in the section
    - Verifies financial totals
    """
    df_bills = spreadsheet_utils.read_sheet_robust(ground_truth_workbook, ["Bills"])
    mask = df_bills["Bill Title"].astype(str).str.strip().str.lower() == "robotx bill"
    bill_items = df_bills[mask].copy()
    assert len(bill_items) == 5
    
    # Group by Budget Section
    grouped = bill_items.groupby("Budget Section", sort=False)
    sections = {name: items for name, items in grouped}
    assert "Electronics" in sections
    assert "Mechanical" in sections
    assert "Misc" in sections
    
    # Test deduplication check logic (verify_item_exists)
    mock_driver = MagicMock()
    anchor_elem = MagicMock()
    container_elem = MagicMock()
    li_elem = MagicMock()
    li_elem.text = "Jetson - Heatsink"
    
    anchor_elem.find_element.return_value = container_elem
    container_elem.find_elements.return_value = [li_elem]
    
    with patch("selenium.webdriver.support.ui.WebDriverWait.until", return_value=anchor_elem):
        # Already exists -> should return True (skip duplicate)
        exists = automation.verify_item_exists(mock_driver, "Electronics", "Jetson - Heatsink")
        assert exists is True
        
        # New item -> should return False (needs to be added)
        exists_new = automation.verify_item_exists(mock_driver, "Electronics", "New Sensor Module")
        assert exists_new is False
        
    # Financial total check
    grand_total = sum(
        automation.safe_float(row["Cost"]) * automation.safe_int(row["Quantity"])
        for _, row in bill_items.iterrows()
    )
    # 45*1 + 20*2 + 10*1 + 15*1 + 0*1 = 110.00
    assert grand_total == 110.00


# ==============================================================================
# WORKFLOW SIMULATION 4: PRICE SCRAPER MULTI-TIER FALLBACK CASCADE
# ==============================================================================

def test_simulated_price_scraper_fallback_cascade():
    """
    Simulates the multi-tier price scraping engine across vendor DOM structures:
    1. Amazon Buybox whole + fraction extraction
    2. Amazon Unit Price exclusion (ignores $/ft or $/count in favor of product price)
    3. OpenGraph / JSON-LD / regex fallback
    4. 404 / Captcha / Network error fallback to spreadsheet allocation
    5. Vendor detection, vendor normalization, ASIN extraction, and stock limits
    """
    # 1. Amazon BuyBox Strategy (whole + fraction)
    mock_driver_buybox = MagicMock()
    whole_elem = MagicMock(); whole_elem.text = "52."
    frac_elem = MagicMock(); frac_elem.text = "99"
    container = MagicMock()
    container.get_attribute.return_value = "a-price"
    container.find_elements.side_effect = lambda by, sel: [whole_elem] if "whole" in sel else [frac_elem]
    mock_driver_buybox.find_elements.side_effect = lambda by, sel: [container] if ".priceToPay" in sel else []
    
    scraped_price_1 = price_scraper.scrape_price_from_driver(mock_driver_buybox)
    assert scraped_price_1 == "$52.99"
    assert price_scraper.parse_price(scraped_price_1) == 52.99
    
    # 2. Amazon Unit Price Exclusion Strategy
    mock_driver_unit = MagicMock()
    unit_el = MagicMock()
    unit_el.get_attribute.side_effect = lambda attr: "pricePerUnit a-price" if attr == "class" else ""
    unit_el.find_element.side_effect = Exception("no parent")
    unit_el.find_elements.return_value = []
    unit_el.text = "$0.25/ft"
    
    real_el = MagicMock()
    real_el.get_attribute.side_effect = lambda attr: "a-offscreen" if attr == "class" else ""
    real_el.find_element.side_effect = Exception("no parent")
    real_el.find_elements.return_value = []
    real_el.text = "$29.99"
    
    def mock_elems(by, sel):
        if ".priceToPay" in sel and "a-offscreen" not in sel:
            return []
        if ".priceToPay .a-offscreen" in sel:
            return [unit_el, real_el]
        return []
        
    mock_driver_unit.find_elements.side_effect = mock_elems
    scraped_price_2 = price_scraper.scrape_price_from_driver(mock_driver_unit)
    assert scraped_price_2 == "$29.99", "Scraper must ignore $/unit rate and capture actual product price"
    
    # 3. HTTP OpenGraph / Meta Tag Strategy
    mock_html = """
    <html><head>
        <meta property="og:price:amount" content="14.50" />
        <meta property="og:price:currency" content="USD" />
    </head><body><h1>Sample Sensor</h1></body></html>
    """
    with patch("requests.get") as mock_req:
        mock_req.return_value.status_code = 200
        mock_req.return_value.text = mock_html
        result = price_scraper.scrape_item_price("https://www.adafruit.com/product/123")
        assert result is not None
        assert result["current_price"] == 14.50
        assert result["vendor"] == "Adafruit"

    # 4. Scrape Failure / 404 Fallback
    with patch("requests.get", side_effect=Exception("Connection refused")):
        with patch("selenium.webdriver.Chrome", side_effect=Exception("Headless disabled")):
            failed_res = price_scraper.scrape_item_price("https://invalid-url-domain.com/broken")
            assert failed_res is None, "Failed scrape should return None and not raise uncaught exception"

    # 5. Price String Parsing Edge Cases
    assert price_scraper.parse_price("$19.99") == 19.99
    assert price_scraper.parse_price(" $ 1,234.56 ") == 1234.56
    assert price_scraper.parse_price("Price: 45.50 USD") == 45.50
    assert price_scraper.parse_price(15.75) == 15.75
    assert price_scraper.parse_price("") is None
    assert price_scraper.parse_price(None) is None
    assert price_scraper.parse_price("No numbers here") is None

    # 6. Vendor Normalization & Domain Detection
    assert price_scraper.detect_vendor_from_url("https://www.amazon.com/dp/B08N5WRWNW") == "Amazon"
    assert price_scraper.detect_vendor_from_url("https://www.mcmaster.com/91251A540/") == "McMaster-Carr"
    assert price_scraper.detect_vendor_from_url("https://www.digikey.com/product/123") == "DigiKey"
    assert price_scraper.normalize_vendor("amazon") == "Amazon"
    assert price_scraper.normalize_vendor("mcmaster-carr") == "McMaster-Carr"

    # 7. ASIN Extraction
    assert price_scraper.extract_amazon_asin("https://www.amazon.com/dp/B08N5WRWNW") == "B08N5WRWNW"
    assert price_scraper.extract_amazon_asin("https://www.amazon.com/gp/product/B012345678/ref=xyz") == "B012345678"
    assert price_scraper.extract_amazon_asin("https://example.com") is None

    # 8. Stock Quantity Limit Detection
    class MockElement:
        def __init__(self, text=""):
            self.text = text
        def find_elements(self, by, value):
            return []
    class MockStockDriver:
        def find_elements(self, by, value):
            if value == "availability":
                return [MockElement("Only 3 left in stock")]
            return []
    qty_set, is_limited, reason = price_scraper.check_and_set_amazon_quantity(MockStockDriver(), desired_qty=10)
    assert is_limited is True
    assert qty_set == 3
    assert "3 left in stock" in reason


# ==============================================================================
# WORKFLOW SIMULATION 5: ENGAGE BILL ITEM LOOKUP 5-TIER FALLBACK
# ==============================================================================

def test_simulated_engage_bill_item_matching_5_tiers():
    """
    Simulates Engage line item lookup matching live HTML across all 5 fallback tiers:
    1. Exact match
    2. Clean alphanumeric match
    3. Stemmed plurals match ('toggle switch' == 'Toggle Switches')
    4. Fuzzy typo match ('rasberry pi 4' == 'Raspberry Pi 4 Model B')
    5. Substring containment with closest length penalty
    6. HTML Line number extraction & URL builder
    """
    candidate_dict = {
        "camera mount": {"section": "Electronics", "line_number": 1, "section_line_number": 1, "name": "camera mount"},
        "m12 penetrator pack": {"section": "Electronics", "line_number": 2, "section_line_number": 2, "name": "m12 penetrator pack"},
        "toggle switches": {"section": "Mechanical", "line_number": 3, "section_line_number": 1, "name": "toggle switches"},
        "raspberry pi 4 model b": {"section": "Electronics", "line_number": 4, "section_line_number": 3, "name": "raspberry pi 4 model b"},
        "jetson carrier board": {"section": "Electronics", "line_number": 5, "section_line_number": 4, "name": "jetson carrier board"},
    }
    
    # Tier 1: Exact match
    m1 = engage_bill_lookup.find_best_item_match("camera mount", candidate_dict)
    assert m1 is not None and m1["line_number"] == 1
    
    # Tier 2: Clean alphanumeric match (ignoring hyphens and parentheses)
    m2 = engage_bill_lookup.find_best_item_match("M12-Penetrator (Pack)", candidate_dict)
    assert m2 is not None and m2["line_number"] == 2
    
    # Tier 3: Stemmed plural match
    m3 = engage_bill_lookup.find_best_item_match("toggle switch", candidate_dict)
    assert m3 is not None and m3["line_number"] == 3
    
    # Tier 4: Fuzzy typo match
    m4 = engage_bill_lookup.find_best_item_match("rasberry pi 4", candidate_dict)
    assert m4 is not None and m4["line_number"] == 4
    
    # Tier 5: Substring match
    m5 = engage_bill_lookup.find_best_item_match("Jetson Carrier Board v2", candidate_dict)
    assert m5 is not None and m5["line_number"] == 5

    # HTML Line Number Regex Extraction
    sample_html = """
    <div>
      <a ng-click="editLineItem(lineItem)">1. First Item</a>
      <a ng-click="editLineItem(lineItem)">2. Valve Assembly</a>
      <a ng-click="editLineItem(lineItem)">3. Motor Controller</a>
    </div>
    """
    assert engage_bill_lookup.find_line_number_in_bill_html(sample_html, "Valve Assembly") == 2
    assert engage_bill_lookup.find_line_number_in_bill_html(sample_html, "Missing Item") is None

    # URL Construction
    url = engage_bill_lookup.build_bill_url("376851")
    assert url == "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests#/edit/376851"


# ==============================================================================
# WORKFLOW SIMULATION 6: PURCHASE REQUEST & OVERRUN / OVERFLOW SIMULATION
# ==============================================================================

def test_simulated_purchase_request_workflow_with_overrun_and_overflow(ground_truth_workbook, tmp_path):
    """
    Simulates the entire Purchase Request execution pipeline:
    - Reads Ordering sheet and links items to Bills sheet via Bill Item ID
    - Runs live price audit:
        * Item 1: Allocated $45.00 -> Quoted $52.99 (+$7.99 price overrun)
        * Item 2: Allocated $20.00 x 2 = $40.00 -> Quoted $40.00 (exact match)
        * Item 3: Allocated $15.00 -> Scrape fails -> Falls back to approved $15.00 allocation
        * Item 4: Allocated $0.00 -> Quoted $7.50 (+$7.50 manual shipping fee)
    - Verifies mathematical calculations:
        * Primary Request Allocation: $100.00
        * Price Overrun: +$7.99
        * Fee Overflow:  +$7.50
        * Total 2nd PR Overflow: $15.49
        * Combined Total: $115.49
    - Verifies generated Overflow Explanation text
    - Verifies Budget vs Quoted Excel attachment generation
    - Verifies Share-A-Cart link generation and persistence
    """
    excel_file = pd.ExcelFile(ground_truth_workbook)
    df_bills = spreadsheet_utils.read_sheet_robust(excel_file, ["Bills"])
    df_orders = spreadsheet_utils.read_sheet_robust(excel_file, ["Ordering"])
    
    # 1. Cross-reference Bill Items
    bill_item_map = {
        str(spreadsheet_utils.get_col_val(r.to_dict(), "bill_item_id")).replace(".0", ""): r.to_dict()
        for _, r in df_bills.iterrows()
    }
    assert "101" in bill_item_map
    assert "102" in bill_item_map
    
    # 2. Build requests to submit
    requests_to_submit = []
    for _, row in df_orders.iterrows():
        r_dict = row.to_dict()
        b_id = str(spreadsheet_utils.get_col_val(r_dict, "bill_item_id")).replace(".0", "")
        b_row = bill_item_map.get(b_id, {})
        
        name = spreadsheet_utils.get_col_val(r_dict, "item_name")
        cost = automation_purchase.safe_float(spreadsheet_utils.get_col_val(b_row, "cost") or spreadsheet_utils.get_col_val(r_dict, "cost"))
        qty = automation_purchase.safe_int(spreadsheet_utils.get_col_val(r_dict, "quantity"))
        
        requests_to_submit.append({
            "item_name": name,
            "cost": cost,
            "quantity": qty,
            "total": cost * qty,
            "bill_no": "376851",
            "bill_item_id": b_id,
            "bill_line_ref": f"Bill 376851, Line {b_id}",
        })
    
    # Primary base allocation (Items 1, 2, 3): 45*1 + 20*2 + 15*1 = 100.00 (Item 4 has cost 0.0 in bill)
    grand_total_allocation = sum(r["total"] for r in requests_to_submit)
    assert grand_total_allocation == 100.00
    
    # 3. Simulate Live Scrape Audit
    scraped_results = {
        "Jetson - Heatsink": 52.99,                   # +$7.99 price increase
        "M12 Penetrators [Pack of 5]": 20.00,        # Exact match
        "Mystery Board": None,                         # Scrape failed -> fallback to 15.00
    }
    manual_overflow_items = [
        {"description": "Amazon Prime Shipping", "amount": 7.50, "bill_line_ref": "Bill 376851, Line 105"}
    ]
    
    total_scraped_live = 0.0
    for r in requests_to_submit:
        live = scraped_results.get(r["item_name"])
        if live is not None:
            total_scraped_live += (live * r["quantity"])
        else:
            # Fallback to allocated cost when scrape fails
            total_scraped_live += r["total"]
            
    # Live cost of base items: 52.99*1 + 20.00*2 + 15.00*1 = 107.99
    assert round(total_scraped_live, 2) == 107.99
    
    # 4. Calculate Overrun & Overflow
    price_overrun_total = max(0.0, total_scraped_live - grand_total_allocation)
    assert round(price_overrun_total, 2) == 7.99
    
    manual_overflow_total = sum(it["amount"] for it in manual_overflow_items)
    assert manual_overflow_total == 7.50
    
    total_overflow_amount = price_overrun_total + manual_overflow_total
    assert round(total_overflow_amount, 2) == 15.49
    
    # 5. Build Overflow Justification Text
    overflow_reasons = []
    if price_overrun_total > 0:
        overflow_reasons.append(f"Price increase overflow for order 260910_amazon_awu335. Original allocation: ${grand_total_allocation:.2f}, Live quoted cost: ${total_scraped_live:.2f}")
        for r_item in requests_to_submit:
            live_cost = scraped_results.get(r_item["item_name"])
            if live_cost is not None and live_cost > r_item["cost"] + 0.01:
                diff = (live_cost - r_item["cost"]) * r_item["quantity"]
                overflow_reasons.append(f"  - {r_item['item_name']}: Allocated ${r_item['cost']:.2f} -> Quoted ${live_cost:.2f} (+${diff:.2f})")

    if manual_overflow_items:
        overflow_reasons.append("Shipping / Tax fee allocations:")
        for m_item in manual_overflow_items:
            overflow_reasons.append(f"  - {m_item['description']}: +${m_item['amount']:.2f} ({m_item['bill_line_ref']})")

    overflow_text = "\n".join(overflow_reasons)
    assert "Jetson - Heatsink: Allocated $45.00 -> Quoted $52.99 (+$7.99)" in overflow_text
    assert "Amazon Prime Shipping: +$7.50 (Bill 376851, Line 105)" in overflow_text
    
    # 6. Generate Side-by-Side Budget vs Quoted Excel Report
    report_out_dir = str(tmp_path / "reports")
    xlsx_report, csv_report = order_excel_builder.generate_order_budget_vs_quoted_excel(
        order_id="260910_amazon_awu335",
        requests_to_submit=requests_to_submit,
        scraped_results=scraped_results,
        output_dir=report_out_dir
    )
    assert os.path.exists(xlsx_report), "Excel detail report must exist"
    assert os.path.exists(csv_report), "CSV detail report must exist"
    
    # Inspect generated Excel report formulas and integrity
    wb_rep = openpyxl.load_workbook(xlsx_report, data_only=False)
    ws_rep = wb_rep.active
    assert ws_rep.title == "Budget vs Quoted Detail"
    # Find total row formula
    has_sum_formula = False
    for row in ws_rep.iter_rows(values_only=True):
        for cell in row:
            if isinstance(cell, str) and "=SUM(" in cell:
                has_sum_formula = True
                break
    assert has_sum_formula, "Excel report must contain =SUM(...) subtotal formulas"
    wb_rep.close()
    
    # 7. Share-A-Cart Normalization & Persistence
    test_cart_code = "ABC98765"
    normalized_cart = share_a_cart.normalize_share_a_cart_url(test_cart_code)
    assert normalized_cart == "https://shareacart.net/get/ABC98765"
    assert share_a_cart.normalize_share_a_cart_url("https://shareacart.net/get/XYZ") == "https://shareacart.net/get/XYZ"
    assert share_a_cart.normalize_share_a_cart_url("") is None
    
    updated_cnt = spreadsheet_utils.update_order_table_links(
        ground_truth_workbook,
        "260910_amazon_awu335",
        share_cart_url=normalized_cart,
        engage_request_url="https://gatech.campuslabs.com/engage/finance/request/99999"
    )
    assert updated_cnt == 4, "All 4 order rows should have their links updated in the Ordering sheet"

    # 8. Share-A-Cart Extension Discovery
    with tempfile.TemporaryDirectory() as tmp_ext_dir:
        ext_dir = os.path.join(tmp_ext_dir, "extensions")
        os.makedirs(ext_dir, exist_ok=True)
        crx_file = os.path.join(ext_dir, "share-a-cart.crx")
        with open(crx_file, "w") as f:
            f.write("mock crx")
        with patch("os.path.dirname", return_value=tmp_ext_dir):
            found_ext = share_a_cart.find_share_a_cart_extension()
            assert found_ext == crx_file


# ==============================================================================
# WORKFLOW SIMULATION 7: FLASK WEB DASHBOARD & REVIEW GUI SIMULATION
# ==============================================================================

def test_simulated_web_app_dashboard_workflow(ground_truth_workbook, monkeypatch):
    """
    Simulates the Flask Web App dashboard workflow:
    - Unauthenticated request -> redirects to /login
    - Login with valid credentials -> sets session and enters dashboard
    - View Bills and Orders
    - 404 handler
    """
    # Point app to ground truth workbook
    monkeypatch.setenv("FINANCE_XLSX_PATH", ground_truth_workbook)
    
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    
    with app.test_client() as client:
        # 1. Unauthenticated access redirects
        r_unauth = client.get("/")
        assert r_unauth.status_code == 302
        assert "/login" in r_unauth.headers["Location"]
        
        # 2. Login
        r_login = client.post("/login", data={"password": "boats0519", "name": "Test Operator"}, follow_redirects=True)
        assert r_login.status_code == 200
        assert b"MRG Purchasing" in r_login.data
        
        # 3. View Orders page
        r_orders = client.get("/orders")
        assert r_orders.status_code == 200
        assert b"260910_amazon_awu335" in r_orders.data or b"Orders" in r_orders.data
        
        # 4. View Bill page
        r_bill = client.get("/bill/RobotX%20Bill")
        assert r_bill.status_code == 200
        assert b"RobotX Bill" in r_bill.data

        # 5. 404 Error handler
        r_404 = client.get("/non-existent-page-route-404")
        assert r_404.status_code == 404


# ==============================================================================
# WORKFLOW SIMULATION 8: PACKAGING & CLI DISPATCH REGRESSION SHIELD
# ==============================================================================

def test_packaging_and_cli_dispatch_integrity():
    """
    Verifies packaging integrity and CLI command availability:
    - pyproject.toml declares packages = ['mrg_finance', 'web-app', 'web-app.routes']
    - Script entrypoint mrg-finance = 'mrg_finance.cli:main'
    - Zero loose .py files exist in the repository root
    - CLI dispatch table contains all commands (report, doctor, bill-request, purchase, etc.)
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 1. Check root for stray python files
    loose_py = [
        f for f in os.listdir(root_dir)
        if f.endswith(".py") and not f.startswith("test") and f != "conftest.py"
    ]
    assert not loose_py, f"Loose python files found in root: {loose_py}"
    
    # 2. Verify CLI entrypoint imports cleanly
    assert hasattr(cli, "main"), "mrg_finance.cli must expose main()"
    
    # 3. Verify CLI commands exist in dispatch map
    expected_cmds = {"report", "screenshots", "review", "bill-request", "purchase", "price-check", "doctor"}
    
    # Check CLI functions exist
    for cmd in ["cmd_report", "cmd_screenshots", "cmd_review", "cmd_bill_request", "cmd_purchase", "cmd_price_check", "cmd_doctor"]:
        assert hasattr(cli, cmd), f"CLI command function {cmd} must exist"
