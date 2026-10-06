import sys
import os
import pytest

# Add repo root, mrg_finance package dir, and web-app to sys.path for test discovery
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
pkg_dir = os.path.join(repo_root, "mrg_finance")
web_app_dir = os.path.join(repo_root, "web-app")

for p in [repo_root, pkg_dir, web_app_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def isolate_cart_browser_profiles(monkeypatch, tmp_path):
    # Browser-mocked tests must never copy or change the user's actual profile.
    monkeypatch.setattr("mrg_finance.browser_profiles.profile_root", lambda: tmp_path / "profiles")
