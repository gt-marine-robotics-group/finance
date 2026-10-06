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
6. Flask Web Dashboard Simulation (web-app/app.py)
7. Purchase CLI selection, workbook fallbacks, and cancellation (mrg_finance.cli)
"""

import os
import sys
from unittest.mock import MagicMock, patch
import pytest
import openpyxl
import pandas as pd

# Import package modules under test
from mrg_finance import (
    spreadsheet_utils,
    price_scraper,
    engage_bill_lookup,
    automation,
    automation_purchase,
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

    # URL Construction
    url = engage_bill_lookup.build_bill_url("376851")
    assert url == "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests#/edit/376851"


# ==============================================================================
# WORKFLOW SIMULATION 6: FLASK WEB DASHBOARD SIMULATION
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
    import xlsx_manager
    monkeypatch.setattr(xlsx_manager, "LOCAL_XLSX", ground_truth_workbook)
    monkeypatch.setattr(xlsx_manager, "_get_graph_token", lambda: None)
    monkeypatch.setattr(xlsx_manager, "sync_pull", lambda **kwargs: False)
    xlsx_manager.invalidate_all_caches()
    app = create_app()
    app.config["TESTING"] = True
    
    with app.test_client() as client:
        # 1. Unauthenticated access redirects
        r_unauth = client.get("/")
        assert r_unauth.status_code == 302
        assert "/login" in r_unauth.headers["Location"]
        
        # 2. Login
        login_pw = os.environ.get("LOGIN_PASSWORD", "dev-password")
        r_login = client.post("/login", data={"password": login_pw, "name": "Test Operator"}, follow_redirects=True)
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
# WORKFLOW SIMULATION 7: PURCHASE WORKBOOK FALLBACK & CANCELLATION
# ==============================================================================

def test_purchase_workbook_fallback_and_single_confirmation(tmp_path, monkeypatch, capsys):
    """
    Resolve uncalculated Ordering values from Bills and cancel before cart/login.
    Exercise the actual CLI-to-purchase dispatch to ensure there is only one confirmation.
    """
    # 1. Construct workbook with uncalculated Ordering row formulas
    wb = openpyxl.Workbook()
    ws_bills = wb.active
    ws_bills.title = "Bills"
    ws_bills.append(["FY27 BUDGET BILLS"])
    ws_bills.append(["Bill Item ID", "Bill No.", "Bill Title", "Item Name", "Vendor", "Cost", "Quantity", "Total Cost", "Status", "Link"])
    ws_bills.append(["501", "376851", "RobotX", "Brushless Thruster ESC", "Blue Robotics", 119.50, 2, 239.00, "Approved", "https://bluerobotics.com/store/test-esc"])

    ws_orders = wb.create_sheet(title="Ordering")
    ws_orders.append(["TOTALS", "", "", "", "", "", "", "", ""])
    ws_orders.append(["Order ID (YYMMDD_vendor_gburdell3)", "Bill Item ID", "Bill No.", "Item Name", "Vendor", "Cost", "Quantity", "Total Cost", "Allocation", "Status"])
    # Empty string values simulating uncalculated formulas
    ws_orders.append(["260929_bluerobotics_cray66", "501", "", "", "", "", 2, "", "", "pending purchase"])

    test_xlsx = str(tmp_path / "test_uncalc.xlsx")
    wb.save(test_xlsx)
    wb.close()

    monkeypatch.setenv("FINANCE_XLSX_PATH", test_xlsx)
    monkeypatch.setattr(cli, "XLSX_PATH", test_xlsx)
    monkeypatch.setattr(automation_purchase, "XLSX_PATH", test_xlsx)

    # 2. Test cmd_purchase listing with mock inputs
    from unittest.mock import MagicMock
    args = MagicMock()
    args.order = None
    args.fresh = False
    args.no_review = False
    args.cart_source = "automated"

    monkeypatch.setattr(automation_purchase, "USERNAME", "")
    monkeypatch.setattr(automation_purchase, "PASSWORD", "")
    monkeypatch.delenv("ENGAGE_USERNAME", raising=False)
    monkeypatch.delenv("ENGAGE_PASSWORD", raising=False)
    password = MagicMock(side_effect=AssertionError("Cancellation should not ask for credentials"))
    monkeypatch.setattr(automation_purchase.getpass, "getpass", password)
    cart = MagicMock(side_effect=AssertionError("Cancellation should not open a cart"))
    monkeypatch.setattr(automation_purchase, "prepare_cart", cart)
    def run_purchase(command):
        monkeypatch.setattr(sys, "argv", command[1:])
        with pytest.raises(SystemExit) as stopped:
            automation_purchase.main()
        return MagicMock(returncode=stopped.value.code)
    monkeypatch.setattr(cli.subprocess, "run", run_purchase)

    # Select order 1, then decline cart preparation before any credentials are requested.
    inputs = iter(["1", "n"])
    prompts = []
    def answer(prompt=""):
        prompts.append(prompt)
        return next(inputs)
    monkeypatch.setattr("builtins.input", answer)

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_purchase(args)
    assert exc_info.value.code == 0
    assert sum("verify" in prompt for prompt in prompts) == 1
    assert list(inputs) == []
    output = capsys.readouterr().out
    assert output.count("Pending Orders") == 1
    assert "Available Orders" not in output
    assert output.count("Purchase Request") == 1
    assert "$239.00" in output
    password.assert_not_called()
    cart.assert_not_called()
