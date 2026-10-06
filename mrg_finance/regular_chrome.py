"""Evidence capture through an extension in the user's regular Chrome.

No WebDriver, remote-debugging flags, profile copying, or platform UI APIs.
The loopback bridge accepts only a paired extension and fixed read/capture
operations. Chrome and its other tabs are left open when a run finishes.
"""

import base64
import html
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By


PROTOCOL = 1


def extension_path_label():
    """Show a portable per-user location, with the resolved path available separately."""
    if sys.platform == "darwin":
        return "~/Library/Application Support/mrg-finance/evidence-extension"
    if sys.platform == "win32":
        base = "%LOCALAPPDATA%" if os.environ.get("LOCALAPPDATA") else r"%USERPROFILE%\AppData\Local"
        return base + r"\mrg-finance\evidence-extension"
    base = "$XDG_DATA_HOME" if os.environ.get("XDG_DATA_HOME") else "~/.local/share"
    return base + "/mrg-finance/evidence-extension"


def extension_folder():
    from mrg_finance.browser_profiles import profile_root
    target = profile_root().parent / "evidence-extension"
    source = Path(__file__).with_name("chrome_extension")
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            dest = target / path.name
            if not dest.exists() or dest.read_bytes() != path.read_bytes():
                shutil.copyfile(path, dest)
    return target


def chrome_executable():
    candidates = []
    if sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                      Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif sys.platform == "win32":
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    candidates.append(Path(winreg.QueryValue(key, None)))
            except OSError:
                pass
        for name in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            if os.environ.get(name):
                candidates.append(Path(os.environ[name]) / "Google/Chrome/Application/chrome.exe")
    for command in ("google-chrome", "google-chrome-stable", "chrome", "chrome.exe"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("Regular-Chrome capture requires Google Chrome installed. Install Chrome, "
                       "or use screenshots --browser selenium for the existing browser mode.")


class ChromeBridge:
    def __init__(self, folder):
        self.token = secrets.token_urlsafe(32)
        self.origin = None
        self.connected = threading.Event()
        self.commands = queue.Queue()
        self.pending = {}
        self.lock = threading.Lock()
        self.folder = folder
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # URLs and pairing secrets must not enter logs.

            def reply(self, status, value, *, page=False):
                data = value.encode() if page else json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8" if page else "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
                if bridge.origin and self.headers.get("Origin") == bridge.origin:
                    self.send_header("Access-Control-Allow-Origin", bridge.origin)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def valid_host(self):
                return self.headers.get("Host") == f"127.0.0.1:{bridge.server.server_port}"

            def authorized(self):
                origin = self.headers.get("Origin", "")
                if not origin:
                    origin = "chrome-extension://" + self.headers.get("X-MRG-Extension", "")
                parsed = urlparse(origin)
                extension = (parsed.scheme == "chrome-extension" and len(parsed.netloc) == 32
                             and all(c in "abcdefghijklmnop" for c in parsed.netloc))
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                return (self.valid_host() and extension and secrets.compare_digest(token, bridge.token)
                        and (bridge.origin is None or origin == bridge.origin))

            def do_GET(self):
                if not self.valid_host():
                    return self.reply(403, {"error": "Invalid host"})
                if self.path == "/":
                    return self.reply(200, bridge.pairing_page(), page=True)
                if not self.authorized() or not bridge.connected.is_set():
                    return self.reply(403, {"error": "Extension pairing required"})
                if self.path != "/command":
                    return self.reply(404, {})
                try:
                    command = bridge.commands.get(timeout=0.3)
                except queue.Empty:
                    command = None
                self.reply(200, command)

            def do_OPTIONS(self):
                origin = self.headers.get("Origin", "")
                parsed = urlparse(origin)
                valid = (parsed.scheme == "chrome-extension" and len(parsed.netloc) == 32
                         and all(c in "abcdefghijklmnop" for c in parsed.netloc))
                if not self.valid_host() or not valid or (bridge.origin and bridge.origin != origin):
                    return self.reply(403, {})
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Access-Control-Allow-Headers", "Authorization, X-MRG-Extension")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                if not self.authorized():
                    return self.reply(403, {"error": "Extension pairing required"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 24 * 1024 * 1024:
                        return self.reply(413, {})
                    value = json.loads(self.rfile.read(size))
                    if not isinstance(value, dict):
                        raise ValueError("Expected object")
                except (ValueError, TypeError):
                    return self.reply(400, {})
                if self.path == "/connect":
                    if value.get("protocol") != PROTOCOL:
                        return self.reply(409, {"error": "Reload the MRG Finance extension at chrome://extensions"})
                    with bridge.lock:
                        origin = self.headers.get("Origin") or "chrome-extension://" + self.headers["X-MRG-Extension"]
                        if bridge.origin and bridge.origin != origin:
                            return self.reply(403, {})
                        bridge.origin = origin
                        bridge.connected.set()
                    return self.reply(200, {"protocol": PROTOCOL})
                if self.path == "/result":
                    with bridge.lock:
                        request_id = value.get("id")
                        pending = bridge.pending.get(request_id) if isinstance(request_id, str) else None
                        if pending is not None:
                            pending[1].update(value)
                            pending[0].set()
                    return self.reply(200, {})
                self.reply(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def pairing_page(self):
        return f'''<!doctype html><html><head><title>MRG Finance Chrome connection</title>
        <meta name="mrg-finance-token" content="{self.token}">
        <meta name="mrg-finance-protocol" content="{PROTOCOL}"></head>
        <body style="font:18px system-ui;max-width:800px;margin:60px auto;padding:24px">
        <h1>Connect regular Chrome</h1><p id="status">Waiting for the MRG Finance Evidence extension.</p>
        <p>One-time setup on macOS, Windows, or Linux:</p><ol>
        <li>Open <b>chrome://extensions</b> in another tab.</li>
        <li>Enable <b>Developer mode</b>, choose <b>Load unpacked</b>, and select
        the extension folder for your account:<br>
        <code>{html.escape(extension_path_label())}</code>
        <p>The CLI creates this folder automatically. Its location follows your computer
        and user account; <code>~</code> means your home folder, and environment variables
        refer to your account's configured folders.</p>
        <details><summary>Show the full folder path on this computer</summary>
        <p>Copy this path into the folder chooser:<br>
        <code>{html.escape(str(self.folder))}</code></p></details></li>
        <li>Return here and reload this connection page, then return to the Terminal.</li></ol>
        <p>Already installed? Reload this page. After a CLI update, click Reload on the
        extension's card first. Keep this connection tab open during capture.</p>
        <p>The tool uses a separate product tab. Position the product name and price in view
        before each screenshot. Other tabs and Chrome remain open.</p></body></html>'''

    def call(self, operation, **arguments):
        request_id = secrets.token_hex(12)
        event, result = threading.Event(), {}
        with self.lock:
            self.pending[request_id] = (event, result)
        self.commands.put({"id": request_id, "operation": operation, **arguments})
        try:
            if not event.wait(45):
                raise WebDriverException("Chrome extension stopped responding. Keep the connection tab open; "
                                         "reload the extension and rerun screenshots.")
            if not result.get("ok"):
                raise WebDriverException(result.get("error", "Chrome capture failed"))
            return result.get("value")
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class PageElement:
    def __init__(self, record):
        self.record = record
        self.text = record["text"]

    def get_attribute(self, name):
        return self.record["attributes"].get(name)

    def is_displayed(self):
        return self.record["visible"]


class RegularChrome:
    is_regular_chrome = True

    def __init__(self, prompt=None):
        prompt = prompt or input
        executable = chrome_executable()
        folder = extension_folder()
        self.bridge = ChromeBridge(folder)
        try:
            print(f"Regular Chrome extension folder: {folder}\nConnection page: {self.bridge.url}")
            subprocess.Popen([executable, "--new-window", self.bridge.url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while not self.bridge.connected.wait(2):
                answer = prompt("Install/reload the MRG Finance extension as shown in Chrome, then Enter "
                                "(or 'cancel'): ").strip().lower()
                if answer in ("cancel", "quit", "q"):
                    raise RuntimeError("Regular Chrome connection cancelled; no evidence captured.")
            print("Connected to regular Chrome. Existing profile and extensions are retained.")
        except BaseException:
            self.bridge.close()
            raise

    def set_page_load_timeout(self, seconds):
        pass  # Navigation is asynchronous; capture_evidence waits for DOM readiness.

    def get(self, url):
        if urlparse(url).scheme not in ("https", "http"):
            raise ValueError("Product links must use HTTP(S)")
        self.bridge.call("navigate", url=url)

    @property
    def current_url(self):
        return self.bridge.call("page")["url"]

    @property
    def title(self):
        return self.bridge.call("page")["title"]

    @property
    def page_source(self):
        return self.bridge.call("page", include_html=True)["html"]

    def execute_script(self, script):
        if script.strip().rstrip(";") != "return document.readyState":
            raise NotImplementedError("Regular Chrome evidence only supports reading page readiness")
        return self.bridge.call("page")["ready"]

    def find_elements(self, by, selector):
        if by not in (By.CSS_SELECTOR, By.TAG_NAME):
            raise NotImplementedError("Regular Chrome evidence supports CSS/tag selectors")
        return [PageElement(record) for record in self.bridge.call("query", selector=selector)]

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if not elements:
            raise NoSuchElementException(selector)
        return elements[0]

    def execute_cdp_cmd(self, *args):
        raise NotImplementedError("Regular Chrome captures the visible product page, without a debugger")

    def save_screenshot(self, path):
        result = self.bridge.call("capture")
        data = base64.b64decode(result["image"].split(",", 1)[1], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Chrome did not return a PNG screenshot")
        Path(path).write_bytes(data)
        return True

    def quit(self):
        self.bridge.close()  # Never quit the user's Chrome or close personal tabs.
