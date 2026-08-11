"""
bills.py - Bill management routes (create bill, view bill, export CSV, delete bill, remove from bill, copy to bill, review bill).
"""

import os
import io
import csv
import shutil
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
import xlsx_manager
import screenshot_worker
from routes.auth import login_required

bills_bp = Blueprint("bills", __name__)


def _copy_screenshot_to_bill(item_name: str, from_bill: str, to_bill: str):
    """Copy a screenshot from one bill folder to another (local + SharePoint)."""
    src_path = screenshot_worker.get_screenshot_path(item_name, from_bill)
    if not src_path:
        return

    safe_bill = screenshot_worker._safe_dirname(to_bill)
    safe_name = screenshot_worker._safe_filename(item_name)
    dest_dir = os.path.join(screenshot_worker.SCREENSHOT_DIR, safe_bill)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{safe_name}.png")
    try:
        shutil.copy2(src_path, dest_path)
    except Exception as e:
        print(f"[screenshot] Local copy error: {e}")

    screenshot_worker._upload_screenshot_to_sharepoint(to_bill, dest_path)


@bills_bp.route("/create-bill", methods=["GET", "POST"])
@login_required
def create_bill():
    """Select items from the queue (Test sheet) and move them to the Bills sheet."""
    if request.method == "POST":
        existing_bill = request.form.get("existing_bill", "").strip()
        new_bill_title = request.form.get("bill_title", "").strip()
        bill_title = existing_bill or new_bill_title
        is_new_bill = not existing_bill

        selected_indices = request.form.getlist("item_ids")

        if not bill_title:
            flash("Bill title is required", "error")
            return redirect(url_for("bills.create_bill"))

        if not selected_indices:
            flash("Select at least one item", "error")
            return redirect(url_for("bills.create_bill"))

        queue_items = xlsx_manager.read_queue_items()
        selected_items = [
            item for item in queue_items
            if str(item.get("_table_index", "")) in selected_indices
        ]

        if not selected_items:
            flash("No matching items found", "error")
            return redirect(url_for("bills.create_bill"))

        moved = xlsx_manager.move_to_bill(
            selected_items, bill_title, add_separator=is_new_bill, person=session.get("user_name", "")
        )

        for item in selected_items:
            name = str(item.get("Item Name", ""))
            if name:
                _copy_screenshot_to_bill(name, "_queue", bill_title)

        xlsx_manager.invalidate_all_caches()

        flash(f"Created bill '{bill_title}' with {moved} item(s)", "success")
        return redirect(url_for("dashboard.dashboard"))

    backlog = xlsx_manager.get_backlog_items()
    bills = xlsx_manager.get_bills()
    return render_template("create_bill.html", backlog=backlog, bills=bills)


@bills_bp.route("/bill/<path:bill_title>")
@login_required
def bill_view(bill_title):
    items = xlsx_manager.get_items_by_bill(bill_title)

    total = 0
    for item in items:
        try:
            cost = float(str(item.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
            qty = float(item.get("Quantity", 1) or 1)
            total += cost * qty
        except (ValueError, TypeError):
            pass

        name = str(item.get("Item Name", ""))
        item["_has_screenshot"] = screenshot_worker.has_screenshot(name, bill_title)
        full_path = screenshot_worker.get_screenshot_path(name, bill_title)
        if full_path:
            item["_screenshot_path"] = os.path.relpath(full_path, screenshot_worker.SCREENSHOT_DIR)
        else:
            item["_screenshot_path"] = ""

    return render_template("bill_view.html", bill_title=bill_title, items=items, total=total)


@bills_bp.route("/bill/<path:bill_title>/export")
@login_required
def export_csv(bill_title):
    items = xlsx_manager.get_items_by_bill(bill_title)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["Item Name", "Cost", "Quantity", "Total Cost", "Vendor", "Link", "Budget Section", "Description"],
    )
    writer.writeheader()
    for item in items:
        writer.writerow({k: item.get(k, "") for k in writer.fieldnames})

    response = Response(output.getvalue(), mimetype="text/csv")
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in bill_title)
    response.headers["Content-Disposition"] = f"attachment; filename={safe_title}.csv"
    return response


@bills_bp.route("/delete-bill/<path:bill_title>", methods=["POST"])
@login_required
def delete_bill(bill_title):
    """Delete all items in a bill (and its separator row) from BillsT."""
    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard.dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}"}

    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/BillsT/rows"
    resp = requests.get(rows_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        flash("Failed to read bills", "error")
        return redirect(url_for("dashboard.dashboard"))

    rows = resp.json().get("value", [])

    to_clear = []
    for r in rows:
        vals = r["values"][0]
        row_bill = str(vals[2]) if vals[2] else ""
        if row_bill == bill_title:
            to_clear.append(r["index"])

    if not to_clear:
        flash(f"No rows found for '{bill_title}'", "error")
        return redirect(url_for("dashboard.dashboard"))

    first_item_idx = min(to_clear)
    for r in rows:
        vals = r["values"][0]
        row_bill = str(vals[2]) if vals[2] else ""
        item_name = str(vals[3]) if vals[3] else ""
        if r["index"] == first_item_idx - 1 and row_bill.startswith("Request") and not item_name:
            to_clear.append(r["index"])
            break

    headers_ct = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    cleared = 0
    for idx in to_clear:
        sheet_row = idx + 2
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Bills')/range(address='B{sheet_row}:J{sheet_row}')"
        resp = requests.patch(url, headers=headers_ct, json={"values": [[""] * 9]}, timeout=10)
        url2 = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Bills')/range(address='L{sheet_row}:P{sheet_row}')"
        resp2 = requests.patch(url2, headers=headers_ct, json={"values": [[""] * 5]}, timeout=10)
        if resp.status_code == 200 and resp2.status_code == 200:
            cleared += 1

    xlsx_manager.invalidate_all_caches()

    flash(f"Deleted bill '{bill_title}' ({cleared} rows cleared)", "success")
    return redirect(url_for("dashboard.dashboard"))


@bills_bp.route("/remove-from-bill/<item_id>", methods=["POST"])
@login_required
def remove_from_bill(item_id):
    """Move item back to backlog (clear Bill Title, set status to New)."""
    success = xlsx_manager.update_item(item_id, {"Bill Title": "", "Status": "New"})
    if success:
        flash("Item moved to backlog", "success")
    else:
        flash("Failed to remove item from bill", "error")
    return redirect(request.referrer or url_for("dashboard.dashboard"))


@bills_bp.route("/copy-to-bill/<item_id>", methods=["GET", "POST"])
@login_required
def copy_to_bill(item_id):
    """Duplicate an item from one bill to another, copying the screenshot too."""
    if request.method == "POST":
        target_bill = request.form.get("bill_title", "").strip()
        if not target_bill:
            flash("Select a target bill", "error")
            return redirect(request.referrer or url_for("dashboard.dashboard"))

        items = xlsx_manager.read_items()
        source_item = None
        for item in items:
            if str(item.get("Bill Item ID", "")) == str(item_id):
                source_item = item
                break

        if not source_item:
            flash("Item not found", "error")
            return redirect(url_for("dashboard.dashboard"))

        bills_columns = xlsx_manager.graph_get_table_columns("BillsT")
        if not bills_columns:
            flash("Failed to get table columns", "error")
            return redirect(url_for("dashboard.dashboard"))

        item_data = dict(source_item)
        item_data["Bill Title"] = target_bill
        item_data["Status"] = "bill requested"
        item_data["Bill Item ID"] = ""

        try:
            qty = float(item_data.get("Quantity", 1) or 1)
            cost = float(str(item_data.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
            item_data["Total Cost"] = qty * cost
        except (ValueError, TypeError):
            item_data["Total Cost"] = 0

        FORMULA_COLUMNS = {"Bill Item ID", "Total Cost"}
        row_values = ["" if col in FORMULA_COLUMNS else (item_data.get(col, "") or "") for col in bills_columns]
        success = xlsx_manager.graph_add_row("BillsT", row_values)

        if success:
            name = str(source_item.get("Item Name", ""))
            source_bill = str(source_item.get("Bill Title", ""))
            if name:
                _copy_screenshot_to_bill(name, source_bill, target_bill)
            flash(f"Copied '{name}' to '{target_bill}'", "success")
        else:
            flash("Failed to copy item", "error")

        return redirect(url_for("bills.bill_view", bill_title=target_bill))

    items = xlsx_manager.read_items()
    source_item = None
    for item in items:
        if str(item.get("Bill Item ID", "")) == str(item_id):
            source_item = item
            break

    if not source_item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard.dashboard"))

    bills = xlsx_manager.get_bills()
    return render_template("copy_to_bill.html", item=source_item, bills=bills)


@bills_bp.route("/review/<path:bill_title>")
@login_required
def review_bill(bill_title):
    """Swipeable review page to quickly edit items and see screenshots."""
    items = xlsx_manager.get_items_by_bill(bill_title)
    for item in items:
        name = str(item.get("Item Name", ""))
        full_path = screenshot_worker.get_screenshot_path(name, bill_title)
        if full_path:
            item["_screenshot_path"] = os.path.relpath(full_path, screenshot_worker.SCREENSHOT_DIR)
        else:
            item["_screenshot_path"] = ""
    return render_template("review_bill.html", bill_title=bill_title, items=items)


@bills_bp.route("/review/<path:bill_title>/save", methods=["POST"])
@login_required
def review_save(bill_title):
    """Save edits from the review page."""
    item_id = request.form.get("item_id", "").strip()
    if item_id:
        updates = {}
        cost = request.form.get("cost", "").strip()
        quantity = request.form.get("quantity", "").strip()
        vendor = request.form.get("vendor", "").strip()
        budget_section = request.form.get("budget_section", "").strip()

        if cost:
            updates["Cost"] = cost
        if quantity:
            updates["Quantity"] = quantity
        if vendor:
            updates["Vendor"] = vendor
        if budget_section:
            updates["Budget Section"] = budget_section

        if updates:
            xlsx_manager.update_item(item_id, updates)

    flash("Saved", "success")
    return redirect(url_for("bills.review_bill", bill_title=bill_title))
