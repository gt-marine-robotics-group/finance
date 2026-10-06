"""Regular-Chrome transport, fallback, packaging, and cross-platform discovery."""

import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from mrg_finance import regular_chrome, automation_screenshots
from mrg_finance.screenshot_capture import BrowserChallenge, capture_evidence, validate_evidence
from test_bill_evidence import browser, screenshot_workbook, URL


def test_bridge_pairs_only_authenticated_extension_and_returns_command_results(tmp_path):
    bridge = regular_chrome.ChromeBridge(tmp_path)
    headers = {"Authorization": "Bearer " + bridge.token, "Origin": "chrome-extension://" + "a" * 32}
    try:
        assert requests.get(bridge.url + "command", timeout=2).status_code == 403
        assert requests.post(bridge.url + "connect", json={"protocol": 1}, timeout=2).status_code == 403
        website = {**headers, "Origin": "https://vendor.example"}
        assert requests.post(bridge.url + "connect", headers=website, json={"protocol": 1}, timeout=2).status_code == 403
        assert requests.options(bridge.url + "connect", headers=website, timeout=2).status_code == 403
        assert requests.options(bridge.url + "connect", headers=headers, timeout=2).status_code == 204
        assert requests.get(bridge.url, headers={"Host": "attacker.example"}, timeout=2).status_code == 403
        assert requests.post(bridge.url + "connect", headers=headers, json={"protocol": 99}, timeout=2).status_code == 409
        assert requests.post(bridge.url + "connect", headers=headers, json={"protocol": 1}, timeout=2).status_code == 200
        other = {**headers, "Origin": "chrome-extension://" + "b" * 32}
        assert requests.post(bridge.url + "connect", headers=other, json={"protocol": 1}, timeout=2).status_code == 403
        received = []
        worker = threading.Thread(target=lambda: received.append(bridge.call("page")))
        worker.start()
        command = requests.get(bridge.url + "command", headers=headers, timeout=2).json()
        assert command["operation"] == "page"
        result = {"id": command["id"], "ok": True, "value": {"url": URL}}
        assert requests.post(bridge.url + "result", headers=headers, json=result, timeout=2).status_code == 200
        worker.join(2)
        assert not worker.is_alive()
        assert received == [{"url": URL}]
        assert not bridge.pending
    finally:
        bridge.close()


def test_extension_requests_without_origin_header_still_require_secret_and_id(tmp_path):
    bridge = regular_chrome.ChromeBridge(tmp_path)
    try:
        headers = {"Authorization": "Bearer " + bridge.token, "X-MRG-Extension": "a" * 32}
        assert requests.post(bridge.url + "connect", headers=headers, json={"protocol": 1}, timeout=2).status_code == 200
        assert bridge.connected.is_set()
        assert bridge.origin == "chrome-extension://" + "a" * 32
    finally:
        bridge.close()


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_chrome_discovery_on_all_platforms(monkeypatch, tmp_path, platform):
    executable = tmp_path / "google-chrome"
    executable.touch()
    monkeypatch.setattr(Path, "is_file", lambda self: self == executable)
    monkeypatch.setattr(regular_chrome.sys, "platform", platform)
    monkeypatch.setattr(regular_chrome.shutil, "which", lambda name: str(executable) if name == "google-chrome" else None)
    if platform == "win32":
        def absent(*args):
            raise OSError("No registry installation")
        monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
            HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, OpenKey=absent))
    assert regular_chrome.chrome_executable() == str(executable)


def test_extension_export_preserves_stable_folder_and_updates_changed_files(monkeypatch, tmp_path):
    monkeypatch.setattr("mrg_finance.browser_profiles.profile_root", lambda: tmp_path / "chrome")
    folder = regular_chrome.extension_folder()
    first = (folder / "background.js").stat().st_mtime_ns
    assert regular_chrome.extension_folder() == folder
    assert (folder / "background.js").stat().st_mtime_ns == first
    (folder / "background.js").write_text("obsolete")
    regular_chrome.extension_folder()
    assert "captureVisibleTab" in (folder / "background.js").read_text()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert "debugger" not in manifest["permissions"]


def test_regular_chrome_saves_png_and_does_not_quit_browser(tmp_path):
    driver = object.__new__(regular_chrome.RegularChrome)
    driver.bridge = MagicMock()
    png = b"\x89PNG\r\n\x1a\ncontents"
    driver.bridge.call.return_value = {"image": "data:image/png;base64," + base64.b64encode(png).decode()}
    path = tmp_path / "product.png"
    assert driver.save_screenshot(path)
    assert path.read_bytes() == png
    driver.quit()
    driver.bridge.close.assert_called_once()
    assert [call.args[0] for call in driver.bridge.call.call_args_list] == ["capture"]


def test_regular_chrome_challenge_cannot_be_promoted_to_bill_evidence(tmp_path):
    driver = browser()
    driver.is_regular_chrome = True
    driver.find_element.return_value.text = "Verify you are human"
    answers = iter(["", "cancel"])
    path = tmp_path / "product.png"
    with pytest.raises(BrowserChallenge):
        capture_evidence(driver, path, interactive=True, source_url=URL, prompt=lambda p: next(answers))
    assert not validate_evidence(path, source_url=URL)
    assert not path.exists()
    assert list((tmp_path / "challenges").glob("*.png"))


def test_regular_chrome_wrong_vendor_is_saved_only_as_a_diagnostic(tmp_path):
    driver = browser()
    driver.is_regular_chrome = True
    driver.current_url = "https://different.example/product"
    answers = iter(["", "cancel"])
    path = tmp_path / "product.png"
    with pytest.raises(BrowserChallenge):
        capture_evidence(driver, path, interactive=True, source_url=URL, prompt=lambda p: next(answers))
    assert not validate_evidence(path, source_url=URL)
    diagnostics = list((tmp_path / "challenges").glob("*.json"))
    assert "different vendor website" in json.loads(diagnostics[0].read_text())["reason"]


def test_screenshot_auto_fallback_rechecks_regular_browser_and_saves_quote(screenshot_workbook, monkeypatch, tmp_path):
    controlled = browser()
    controlled.find_element.return_value.text = "Verify you are human"
    regular = browser()
    regular.is_regular_chrome = True
    monkeypatch.setattr(automation_screenshots.webdriver, "Chrome", lambda **kwargs: controlled)
    monkeypatch.setattr(regular_chrome, "RegularChrome", lambda: regular)
    monkeypatch.setattr(automation_screenshots, "dismiss_popups", lambda d: None)
    monkeypatch.setattr(automation_screenshots, "extract_price_from_page", lambda *args: ("$100.00", "high"))
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr("sys.argv", ["screenshots", "--excel-path", str(screenshot_workbook), "--bill", "Test Bill"])
    assert automation_screenshots.main() == 1  # Fixture also has two invalid product URLs.
    assert validate_evidence(tmp_path / "shots/Test Bill/Part.png", source_url=URL)
    regular.get.assert_called_once_with(URL)
    controlled.quit.assert_called_once()
    regular.quit.assert_called_once()


def test_extension_operations_with_chrome_api_mocks():
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is needed to validate the packaged Chrome extension")
    test = Path(__file__).with_name("chrome_extension.test.cjs")
    subprocess.run([executable, "--test", str(test)], check=True, capture_output=True, text=True)
