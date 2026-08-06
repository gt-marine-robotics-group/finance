"""
xlsx_manager.py - Read/write FY27_Bills_Budget.xlsx with rclone sync.

Pull before read, push after write. The xlsx on SharePoint is the source of truth.
"""

import os
import subprocess
import threading
from pathlib import Path
from openpyxl import load_workbook

# Config from environment
RCLONE_REMOTE = os.environ.get(
    "RCLONE_REMOTE",
    "onedrive:Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
)
LOCAL_XLSX = os.environ.get("LOCAL_XLSX_PATH", os.path.expanduser("~/mrg-finance/FY27_Bills_Budget.xlsx"))
SHEET_NAME = os.environ.get("XLSX_SHEET_NAME", "Bills")

# File lock to prevent concurrent reads/writes
_lock = threading.Lock()

# Column mapping (xlsx columns in the Bills sheet)
COLUMNS = [
    "Bill Item ID",
    "Bill No.",
    "Bill Title",
    "Item Name",
    "Status",
    "Budget Section",
    "Vendor",
    "Description",
    "Quantity",
    "Cost",
    "Total Cost",
    "Link",
    "File URL",
    "Person Requesting",
]


def _run_rclone(args: list[str]) -> bool:
    """Run an rclone command. Returns True on success."""
    try:
        result = subprocess.run(
            ["rclone"] + args,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"[rclone] Error: {result.stderr.strip()}")
            return False
        return True
    except FileNotFoundError:
        print("[rclone] rclone not found - skipping sync")
        return False
    except subprocess.TimeoutExpired:
        print("[rclone] Timeout during sync")
        return False


def sync_pull() -> bool:
    """Pull latest xlsx from SharePoint."""
    local_dir = str(Path(LOCAL_XLSX).parent)
    os.makedirs(local_dir, exist_ok=True)
    return _run_rclone(["copy", RCLONE_REMOTE, local_dir])


def sync_push() -> bool:
    """Push local xlsx back to SharePoint."""
    remote_dir = str(Path(RCLONE_REMOTE).parent) if "/" in RCLONE_REMOTE else RCLONE_REMOTE
    # For a file path remote, push the file to its parent directory
    parts = RCLONE_REMOTE.rsplit("/", 1)
    if len(parts) == 2:
        remote_dir = parts[0] + "/"
    else:
        remote_dir = RCLONE_REMOTE
    return _run_rclone(["copy", LOCAL_XLSX, remote_dir])


def read_items() -> list[dict]:
    """
    Read all items from the Bills sheet.
    Pulls latest from SharePoint first.
    Returns list of dicts with normalized keys.
    """
    with _lock:
        sync_pull()

        if not os.path.exists(LOCAL_XLSX):
            return []

        wb = load_workbook(LOCAL_XLSX, read_only=True, data_only=True)
        ws = wb[SHEET_NAME]

        # Find header row (first row with data)
        headers = []
        for cell in ws[1]:
            headers.append(str(cell.value).strip() if cell.value else "")

        items = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            item = {}
            for i, col in enumerate(headers):
                if i < len(row):
                    val = row[i]
                    # Normalize whitespace in strings
                    if isinstance(val, str):
                        val = " ".join(val.split())
                    item[col] = val if val is not None else ""
                else:
                    item[col] = ""
            # Only include rows that have an Item Name
            if item.get("Item Name"):
                items.append(item)

        wb.close()
        return items


def get_bills() -> list[str]:
    """Get list of unique bill titles (non-empty)."""
    items = read_items()
    titles = set()
    for item in items:
        title = str(item.get("Bill Title", "")).strip()
        if title:
            titles.add(title)
    return sorted(titles)


def get_items_by_bill(bill_title: str) -> list[dict]:
    """Get items for a specific bill."""
    items = read_items()
    return [i for i in items if str(i.get("Bill Title", "")).strip() == bill_title]


def get_backlog_items() -> list[dict]:
    """Get items with no bill title assigned."""
    items = read_items()
    return [i for i in items if not str(i.get("Bill Title", "")).strip()]


def _find_row_by_item_id(ws, item_id: str, headers: list[str]) -> int | None:
    """Find the row number for a given Bill Item ID."""
    id_col = None
    for i, h in enumerate(headers):
        if h == "Bill Item ID":
            id_col = i
            break
    if id_col is None:
        return None

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row_idx < 2:
            continue
        if id_col < len(row) and str(row[id_col]).strip() == str(item_id).strip():
            return row_idx
    return None


def _get_headers(ws) -> list[str]:
    """Get header row as list of strings."""
    return [str(cell.value).strip() if cell.value else "" for cell in ws[1]]


def _get_next_item_id(ws, headers: list[str]) -> int:
    """Get the next available Bill Item ID."""
    id_col = None
    for i, h in enumerate(headers):
        if h == "Bill Item ID":
            id_col = i
            break
    if id_col is None:
        return 1

    max_id = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if id_col < len(row) and row[id_col]:
            try:
                val = int(float(str(row[id_col])))
                max_id = max(max_id, val)
            except (ValueError, TypeError):
                pass
    return max_id + 1


def add_item(item_data: dict) -> bool:
    """
    Add a new item row to the xlsx.
    Pulls before write, pushes after.
    """
    with _lock:
        sync_pull()

        if not os.path.exists(LOCAL_XLSX):
            return False

        wb = load_workbook(LOCAL_XLSX)
        ws = wb[SHEET_NAME]
        headers = _get_headers(ws)

        # Assign next ID
        next_id = _get_next_item_id(ws, headers)
        item_data["Bill Item ID"] = next_id

        # Calculate Total Cost
        try:
            qty = float(item_data.get("Quantity", 1) or 1)
            cost = float(str(item_data.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
            item_data["Total Cost"] = qty * cost
        except (ValueError, TypeError):
            item_data["Total Cost"] = 0

        # Build row
        row_data = []
        for h in headers:
            row_data.append(item_data.get(h, ""))

        ws.append(row_data)
        wb.save(LOCAL_XLSX)
        wb.close()

        sync_push()
        return True


def update_item(item_id: str, updates: dict) -> bool:
    """
    Update an existing item by Bill Item ID.
    Only modifies specified fields.
    """
    with _lock:
        sync_pull()

        if not os.path.exists(LOCAL_XLSX):
            return False

        wb = load_workbook(LOCAL_XLSX)
        ws = wb[SHEET_NAME]
        headers = _get_headers(ws)

        row_idx = _find_row_by_item_id(ws, item_id, headers)
        if row_idx is None:
            wb.close()
            return False

        for key, value in updates.items():
            if key in headers:
                col_idx = headers.index(key) + 1  # openpyxl is 1-indexed
                ws.cell(row=row_idx, column=col_idx, value=value)

        # Recalculate Total Cost if qty or cost changed
        if "Quantity" in updates or "Cost" in updates:
            qty_col = headers.index("Quantity") + 1 if "Quantity" in headers else None
            cost_col = headers.index("Cost") + 1 if "Cost" in headers else None
            total_col = headers.index("Total Cost") + 1 if "Total Cost" in headers else None

            if qty_col and cost_col and total_col:
                qty = ws.cell(row=row_idx, column=qty_col).value or 1
                cost = ws.cell(row=row_idx, column=cost_col).value or 0
                try:
                    cost_val = float(str(cost).replace("$", "").replace(",", ""))
                    qty_val = float(qty)
                    ws.cell(row=row_idx, column=total_col, value=qty_val * cost_val)
                except (ValueError, TypeError):
                    pass

        wb.save(LOCAL_XLSX)
        wb.close()

        sync_push()
        return True


def delete_item(item_id: str) -> bool:
    """Delete an item row by Bill Item ID."""
    with _lock:
        sync_pull()

        if not os.path.exists(LOCAL_XLSX):
            return False

        wb = load_workbook(LOCAL_XLSX)
        ws = wb[SHEET_NAME]
        headers = _get_headers(ws)

        row_idx = _find_row_by_item_id(ws, item_id, headers)
        if row_idx is None:
            wb.close()
            return False

        ws.delete_rows(row_idx)
        wb.save(LOCAL_XLSX)
        wb.close()

        sync_push()
        return True
