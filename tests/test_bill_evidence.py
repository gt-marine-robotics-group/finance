"""Bill requests must stop before Engage when screenshot proof is missing."""

from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import pytest

from mrg_finance import automation
from mrg_finance.screenshot_capture import (
    BrowserChallenge, capture_evidence, evidence_metadata_path, validate_evidence,
)


URL = "https://www.digikey.com/en/products/detail/raspberry-pi/SC0194-9/10258781"


def browser():
    driver = MagicMock()
    driver.current_url = URL
    driver.title = "SC0194(9) Raspberry Pi"
    driver.find_element.return_value.text = "Raspberry Pi $100.00 Add to Cart"
    driver.find_elements.return_value = []
    driver.execute_script.return_value = "complete"
    driver.execute_cdp_cmd.side_effect = RuntimeError("No CDP")
    driver.save_screenshot.side_effect = lambda p: Path(p).write_bytes(b"product image") or True
    return driver


def test_bill_reuses_only_checked_source_and_unchanged_image(monkeypatch, tmp_path):
    monkeypatch.setattr(automation, "SCREENSHOT_DIR", str(tmp_path))
    path = tmp_path / "Test Bill" / "Part.png"
    capture_evidence(browser(), path, source_url=URL)
    automation.require_bill_evidence([("Part", URL)], "Test Bill")
    assert automation._verified_screenshot("Part", "Test Bill", URL) == str(path)
    assert not validate_evidence(path, source_url="https://www.amazon.com/dp/B012345678")
    path.write_bytes(b"replaced with challenge image")
    with pytest.raises(ValueError, match="before Engage"):
        automation.require_bill_evidence([("Part", URL)], "Test Bill")


def test_challenge_during_capture_invalidates_image_and_previous_proof(tmp_path):
    path = tmp_path / "Part.png"
    driver = browser()
    capture_evidence(driver, path)
    assert validate_evidence(path, source_url=URL)
    def screenshot(p):
        Path(p).write_bytes(b"challenge image")
        driver.title = "Robot check"
        driver.find_element.return_value.text = "Verify you are human"
        return True
    driver.save_screenshot.side_effect = screenshot
    with pytest.raises(BrowserChallenge):
        capture_evidence(driver, path)
    assert not path.exists()
    assert not validate_evidence(path, source_url=URL)
    assert evidence_metadata_path(path).exists()
    assert list((tmp_path / "challenges").glob("*.png"))
    path.write_bytes(b"product image")  # older image restored by a cloud download
    assert not validate_evidence(path, source_url=URL)


def test_noninteractive_verification_can_finish_before_screenshot(tmp_path):
    driver = browser()
    driver.title = "DigiKey"
    # Initial challenge, then the vendor's own verification finishes naturally.
    driver.find_element.side_effect = [
        MagicMock(text="Performing security verification"),
        MagicMock(text="Raspberry Pi $100.00"),
        MagicMock(text="Raspberry Pi $100.00"),
    ]
    path = tmp_path / "Part.png"
    capture_evidence(driver, path, settle_timeout=1)
    assert validate_evidence(path, source_url=URL)
    assert not (tmp_path / "challenges").exists()


@pytest.mark.parametrize("capture", [False, True])
def test_bill_main_stops_before_engage_if_capture_declined_or_blocked(monkeypatch, tmp_path, capture):
    path = tmp_path / "bill.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bills"
    ws.append(["Bill Title", "Bill No.", "Item Name", "Link", "Cost", "Quantity"])
    ws.append(["Test Bill", "344042", "Part", URL, 63.35, 5])
    wb.save(path)
    wb.close()
    monkeypatch.setattr(automation, "SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setattr(automation, "USERNAME", "test-only")
    monkeypatch.setattr(automation, "PASSWORD", "test-only")
    monkeypatch.setattr(automation, "BILL_NO", "")
    monkeypatch.setattr(automation, "BILL_URL", "")
    monkeypatch.setattr("sys.argv", ["bill-request", "--bill", "Test Bill", "--excel-path", str(path)])
    monkeypatch.setattr("builtins.input", lambda p: "y" if capture else "n")
    monkeypatch.setattr(automation.time, "sleep", lambda *a: None)
    chrome = MagicMock(return_value=browser())
    monkeypatch.setattr(automation.webdriver, "Chrome", chrome)
    monkeypatch.setattr("selenium.webdriver.chrome.service.Service", MagicMock())
    from mrg_finance import screenshot_capture
    monkeypatch.setattr(screenshot_capture, "capture_evidence", MagicMock(side_effect=BrowserChallenge("Unresolved challenge")))
    # automation.py's direct-module imports are used by the CLI subprocess.
    import price_scraper, automation_screenshots as direct_screenshots
    monkeypatch.setattr(price_scraper, "dismiss_popups_and_interstitials", lambda d: None)
    monkeypatch.setattr(direct_screenshots, "sync_screenshots_to_sharepoint", lambda: None)
    with pytest.raises(ValueError, match="before Engage"):
        automation.main()
    assert chrome.call_count == int(capture)  # capture browser only; no Engage browser
    if capture:
        chrome.return_value.quit.assert_called_once()
        assert any(a.startswith("--user-data-dir=") for a in chrome.call_args.kwargs["options"].arguments)


def test_legacy_image_without_proof_is_not_bill_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(automation, "SCREENSHOT_DIR", str(tmp_path))
    folder = tmp_path / "Test Bill"
    folder.mkdir()
    (folder / "Part.png").write_bytes(b"unchecked older image")
    assert automation._find_screenshot("Part", "Test Bill")
    assert automation._verified_screenshot("Part", "Test Bill", URL) is None
    with pytest.raises(ValueError, match="Part"):
        automation.require_bill_evidence([("Part", URL)], "Test Bill")
