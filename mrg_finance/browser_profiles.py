"""Stable, dedicated cart profiles with one-time migration from older releases."""

import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def profile_root():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mrg-finance" / "chrome"


def cart_profile(vendor):
    key = re.sub(r"[^a-z0-9_-]", "_", vendor.lower())
    target = profile_root() / key
    if target.exists():
        return target
    legacy_root = Path.cwd() / ".mrg-finance-browser"
    legacy = legacy_root / "digikey" if key == "digikey" else legacy_root
    migrate = key in ("amazon", "digikey") and (
        (legacy / "Default").exists() or (legacy / "Local State").exists())
    if migrate:
        lock = legacy / "SingletonLock"
        if lock.exists() or lock.is_symlink():
            raise ValueError("Close the previous MRG cart Chrome window, then retry. "
                             "Its extension/session profile must be copied while Chrome is closed.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Keep the original profile as a backup. Publish the copy only when
        # complete, so an interrupted migration cannot become the active profile.
        with tempfile.TemporaryDirectory(prefix=".migration-", dir=target.parent) as staging:
            copy = Path(staging) / "profile"
            shutil.copytree(legacy, copy, ignore=shutil.ignore_patterns(
                "Singleton*", "DevToolsActivePort", "digikey", "evidence",
                "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache"))
            copy.rename(target)
        print(f"Copied existing {vendor} cart profile; installed extensions are retained.")
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target
