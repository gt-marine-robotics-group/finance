"""Interactive vendor quote evidence for purchases without product pages."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shlex
import shutil

from .purchase_validation import money, require_matching_total
from .screenshot_capture import evidence_metadata_path, validate_evidence


def prompt_quote_attachment(folder, name="vendor_quote", *, source_url=""):
    """Copy a reviewed PDF/image into evidence storage, preserving its source."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    existing = next((folder / (name + ext) for ext in (".pdf", ".png", ".jpg", ".jpeg")
                     if validate_evidence(folder / (name + ext), source_url=source_url or None)), None)
    while True:
        default = f" (Enter to reuse {existing})" if existing else ""
        raw = input(f"Quote PDF/image file path{default}, or 'cancel': ").strip()
        if raw.lower() in ("cancel", "q", "quit"):
            raise ValueError("Quote attachment cancelled; no Engage request was prepared.")
        path = Path(raw.strip("\"'")).expanduser() if raw else existing
        if path and not path.is_file() and raw:
            # macOS drag-and-drop escapes spaces; Windows paths retain backslashes.
            try:
                parts = shlex.split(raw)
                if len(parts) == 1:
                    path = Path(parts[0]).expanduser()
            except ValueError:
                pass
        if not path or not path.is_file():
            print("File not found. Paste or drag in an existing quote PDF, PNG or JPEG.")
            continue
        signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
        with path.open("rb") as file:
            header = file.read(8)
        if path.suffix.lower() not in signatures or not header.startswith(signatures[path.suffix.lower()]):
            print("Use a PDF, PNG or JPEG quote file, not a web link or another file type.")
            continue
        if input("Does this quote show the correct item(s), quantities and current price, including fees? [Y/n]: ").strip().lower() not in ("", "y", "yes"):
            continue
        target = folder / (name + path.suffix.lower())
        if path.resolve() != target.resolve():
            shutil.copy2(path, target)
        evidence_metadata_path(target).write_text(json.dumps({
            "status": "captured", "method": "manually_reviewed_quote", "source_url": source_url,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }, indent=2), encoding="utf-8")
        print(f"Saved quote attachment: {target.resolve()}")
        return str(target.resolve())


def prepare_quote(items, vendor, folder):
    from .purchase_cart import prompt_money
    print(f"\n{vendor}: using a saved quote because this order has no complete product URL.\n"
          "No vendor cart or Share-A-Cart is needed. Review your quote, then attach it below.\n"
          "Enter the quoted amount including taxes/fees; approved allocations are not live prices.")
    attachment = prompt_quote_attachment(folder)
    subtotal = Decimal("0")
    for item in items:
        prompt = (f"Total shown on the quote for {item['item_name']}, including taxes/fees: $"
                  if len(items) == 1 and item["quantity"] == 1 else
                  f"{item['item_name']} — quote price for ONE unit (quantity {item['quantity']}), including fees: $")
        unit = prompt_money(prompt)
        item["quoted_unit_cost"] = float(unit)
        item["quoted_total"] = float(unit * item["quantity"])
        subtotal += money(item["quoted_total"])
    total = subtotal if len(items) == 1 and items[0]["quantity"] == 1 else prompt_money(
        f"Total shown on the quote (expected ${subtotal}; or 'cancel'): $")
    while total != subtotal:
        print(f"Quoted line amounts add to ${subtotal}. The attachment total must match before continuing.")
        total = prompt_money("Correct total shown on the quote (or 'cancel'): $")
    return {"mode": "quote", "driver": None, "folder": Path(folder), "screenshot": attachment,
            "share_url": None, "subtotal": subtotal, "shipping": Decimal("0"), "tax": Decimal("0"),
            "total": total, "snapshot": None, "vendor_key": "quote",
            "quote_basis": "Manually reviewed quote; entered prices include taxes and fees",
            "evidence_sha256": hashlib.sha256(Path(attachment).read_bytes()).hexdigest()}


def recheck_quote(cart, items):
    from .purchase_cart import prompt_money
    path = Path(cart["screenshot"])
    if (not validate_evidence(path) or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != cart["evidence_sha256"]):
        raise ValueError("Quote attachment changed or is missing. Restore it or rerun before uploading.")
    subtotal = sum((money(item["quoted_unit_cost"]) * item["quantity"] for item in items), Decimal("0"))
    require_matching_total(subtotal, cart["total"])
    print(f"Quote attachment: {path}\nManually reviewed quote total: ${cart['total']}")
    confirmed = prompt_money(f"Confirm the current quote total before upload (Enter for ${cart['total']}, or 'cancel'): $",
                             default=cart["total"])
    require_matching_total(cart["total"], confirmed)
