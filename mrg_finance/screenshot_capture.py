"""Capture usable evidence and keep browser challenges out of quote attachments."""

import base64
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


class BrowserChallenge(RuntimeError):
    pass


def evidence_metadata_path(path):
    return Path(str(Path(path)) + ".evidence.json")


def invalidate_evidence(path):
    """Remove the old capture and its proof before attempting a new capture."""
    Path(path).unlink(missing_ok=True)
    metadata = evidence_metadata_path(path)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    # Keep a newer failure marker so an older cloud copy cannot restore its
    # previous successful proof during the next --fresh download.
    metadata.write_text(json.dumps({"status": "invalidated",
        "invalidated_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")


def validate_evidence(path, *, source_url=None):
    """Require a checked capture, its original source, and unchanged image bytes."""
    path = Path(path)
    try:
        record = json.loads(evidence_metadata_path(path).read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            return False
        return (record.get("status") == "captured"
                and (source_url is None or record.get("source_url") == source_url)
                and record.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest())
    except (OSError, ValueError, TypeError):
        return False


def challenge_reason(driver):
    """Inspect rendered text and visible widgets, not hidden CAPTCHA scripts."""
    url = (driver.current_url or "").lower()
    title = (driver.title or "").lower()
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    for phrase in (
        "enter the characters you see below", "verify you are human",
        "verify that you're not a robot", "robot check", "unusual traffic",
        "checking your browser", "access denied", "confirm you are human",
        "verify you're human", "complete the captcha", "security verification",
        "verifying you are human", "verifying your browser",
        "checking if the site connection is secure",
        "enable javascript and cookies to continue", "403 forbidden",
        "sorry, we just need to make sure you're not a robot",
    ):
        if phrase in body or phrase in title:
            return phrase
    if "just a moment" in title:
        return "browser verification page"
    if "validatecaptcha" in url or "/captcha" in url:
        return "CAPTCHA URL"
    for element in driver.find_elements(
        By.CSS_SELECTOR,
        "input#captchacharacters, iframe[src*='recaptcha'][title*='challenge'], "
        "iframe[src*='hcaptcha'], iframe[src*='challenges.cloudflare.com'], "
        ".g-recaptcha, .h-captcha, #challenge-running",
    ):
        if element.is_displayed():
            return "visible CAPTCHA widget"
    return None


def save_page_screenshot(driver, path, full_page=True):
    """Try full-page Chrome capture; fall back to a viewport on unsupported drivers."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if full_page:
        try:
            metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
            size = metrics.get("cssContentSize") or metrics["contentSize"]
            result = driver.execute_cdp_cmd("Page.captureScreenshot", {
                "format": "png", "captureBeyondViewport": True,
                "clip": {"x": 0, "y": 0, "width": size["width"],
                         "height": size["height"], "scale": 1},
            })
            data = base64.b64decode(result["data"], validate=True)
            if not data:
                raise ValueError("Empty screenshot")
            path.write_bytes(data)
            return str(path)
        except Exception:
            pass
    if not driver.save_screenshot(str(path)):
        raise RuntimeError(f"Screenshot capture failed: {path}")
    return str(path)


def capture_evidence(driver, path, *, interactive=False, prompt=None, source_url=None, settle_timeout=5):
    """Save challenge diagnostics, notify the operator, and optionally wait for solving."""
    path = Path(path).resolve()
    prompt = prompt or input
    source_url = source_url or driver.current_url
    invalidate_evidence(path)
    try:
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )
    except TimeoutException:
        print("  Page load timed out; checking the rendered page.")
    while True:
        reason = challenge_reason(driver)
        if settle_timeout and reason in (
            "checking your browser", "security verification", "verifying your browser",
            "checking if the site connection is secure",
            "browser verification page",
        ):
            # Let the site's own non-interactive verification finish normally.
            # No clicks, tokens, or browser-fingerprint changes are attempted.
            try:
                WebDriverWait(driver, settle_timeout).until(lambda d: not challenge_reason(d))
                reason = None
            except TimeoutException:
                reason = challenge_reason(driver)
        if not reason:
            screenshot = save_page_screenshot(driver, path)
            # A challenge can replace the product during screenshot capture.
            reason = challenge_reason(driver)
            if not reason:
                evidence_metadata_path(path).write_text(json.dumps({
                    "status": "captured", "source_url": source_url,
                    "resolved_url": driver.current_url,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }, indent=2), encoding="utf-8")
                return screenshot
        diagnostics = path.parent / "challenges"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        challenge_path = diagnostics / f"{path.stem}_{stamp}.png"
        save_page_screenshot(driver, challenge_path, full_page=False)
        challenge_path.with_suffix(".json").write_text(json.dumps({
            "status": "challenge", "reason": reason, "url": driver.current_url,
            "captured_at": stamp, "screenshot": str(challenge_path),
        }, indent=2), encoding="utf-8")
        # A previous successful screenshot must not be mistaken for this run's evidence.
        invalidate_evidence(path)
        print(f"\a  CAPTCHA / browser challenge: {reason}\n"
              f"  Page: {driver.current_url}\n  Diagnostic screenshot: {challenge_path}")
        if not interactive:
            raise BrowserChallenge(f"Solve the challenge in a visible browser: {challenge_path}")
        if prompt("  Solve it in the browser, then Enter to retry (or 'cancel'): ").strip().lower() in ("skip", "cancel", "q", "quit"):
            raise BrowserChallenge(f"Challenge unresolved: {challenge_path}")


def navigate_for_evidence(driver, url):
    """A navigation timeout can still leave a useful page or challenge to capture."""
    try:
        driver.get(url)
    except TimeoutException:
        print(f"  Navigation timed out: {url}; inspecting the page.")
