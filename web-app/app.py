"""
app.py - MRG Purchasing web app.

Mobile-friendly Flask app for managing purchase items and organizing them into bills.
"""

import os
import csv
import io
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
    Response,
)
from dotenv import load_dotenv

load_dotenv()

import xlsx_manager
import screenshot_worker

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mrg-purchasing-dev-key-change-me")

# Config
LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD", "boats0519")


# --- Auth ---


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        if password == LOGIN_PASSWORD:
            session["logged_in"] = True
            session["user_name"] = name
            session.permanent = True
            return redirect(url_for("dashboard"))
        else:
            flash("Wrong password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Dashboard ---


@app.route("/")
@login_required
def dashboard():
    items = xlsx_manager.read_items()

    # Group by bill title
    bills = {}

    for item in items:
        title = str(item.get("Bill Title", "")).strip()
        if title:
            if title not in bills:
                bills[title] = []
            bills[title].append(item)

    # Get queue items from Test sheet
    backlog = xlsx_manager.get_backlog_items()

    # Add screenshot status to bill items
    for item in items:
        name = str(item.get("Item Name", ""))
        bill = str(item.get("Bill Title", ""))
        item["_has_screenshot"] = screenshot_worker.has_screenshot(name, bill)
        item["_screenshot_status"] = screenshot_worker.get_status(name)
        full_path = screenshot_worker.get_screenshot_path(name, bill)
        if full_path:
            item["_screenshot_path"] = os.path.relpath(full_path, screenshot_worker.SCREENSHOT_DIR)
        else:
            item["_screenshot_path"] = ""

    # Add screenshot status to queue items
    for item in backlog:
        name = str(item.get("Item Name", ""))
        item["_has_screenshot"] = screenshot_worker.has_screenshot(name, "_queue")
        item["_screenshot_status"] = screenshot_worker.get_status(name)
        full_path = screenshot_worker.get_screenshot_path(name, "_queue")
        if full_path:
            item["_screenshot_path"] = os.path.relpath(full_path, screenshot_worker.SCREENSHOT_DIR)
        else:
            item["_screenshot_path"] = ""

    return render_template("dashboard.html", bills=bills, backlog=backlog)


# --- Add Item ---


@app.route("/quick-add", methods=["POST"])
@login_required
def quick_add():
    """Quick add — just name and optional link. Goes to backlog."""
    import threading

    item_name = request.form.get("item_name", "").strip()
    link = request.form.get("link", "").strip()
    if link and not link.startswith("http"):
        link = "https://" + link

    if not item_name:
        flash("Item name required", "error")
        return redirect(url_for("dashboard"))

    item_data = {
        "Item Name": item_name,
        "Link": link,
        "Cost": "",
        "Quantity": "1",
        "Vendor": "",
        "Description": "",
        "Budget Section": "",
        "Bill Title": "",
        "Person Requesting": session.get("user_name", ""),
    }

    def _do_background(name, url):
        """Background: queue screenshot only."""
        if url:
            import time
            time.sleep(2)
            screenshot_worker.queue_screenshot(name, url, "_queue")

    # Write to SharePoint synchronously so the item shows up immediately
    success = xlsx_manager.add_item(item_data)
    if success:
        flash(f"Added: {item_name}", "success")
        # Queue screenshot in background
        if link:
            threading.Thread(target=_do_background, args=(item_name, link), daemon=True).start()
    else:
        flash("Failed to add", "error")

    return redirect(url_for("dashboard"))


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        item_data = {
            "Item Name": request.form.get("item_name", "").strip(),
            "Cost": request.form.get("cost", "").strip(),
            "Quantity": request.form.get("quantity", "1").strip(),
            "Link": request.form.get("link", "").strip(),
            "Vendor": request.form.get("vendor", "").strip(),
            "Description": request.form.get("description", "").strip(),
            "Budget Section": request.form.get("budget_section", "").strip(),
            "Bill Title": request.form.get("bill_title", "").strip(),
        }

        if item_data["Link"] and not item_data["Link"].startswith("http"):
            item_data["Link"] = "https://" + item_data["Link"]

        if not item_data["Item Name"]:
            flash("Item Name is required", "error")
            return render_template("add_item.html", bills=xlsx_manager.get_bills())

        # Save to queue (Test sheet)
        success = xlsx_manager.add_item(item_data)
        if success:
            flash(f"Added to queue: {item_data['Item Name']}", "success")
            # Queue screenshot if URL provided (save to _queue folder)
            if item_data["Link"]:
                screenshot_worker.queue_screenshot(
                    item_data["Item Name"], item_data["Link"], "_queue"
                )
        else:
            flash("Failed to save item", "error")

        return redirect(url_for("dashboard"))

    return render_template("add_item.html", bills=xlsx_manager.get_bills())


# --- Edit Item ---


@app.route("/edit/<item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    if request.method == "POST":
        updates = {}
        for field in ["Item Name", "Cost", "Quantity", "Link", "Vendor",
                      "Description", "Budget Section", "Bill Title",
                      "Person Requesting", "Status"]:
            form_key = field.lower().replace(" ", "_").replace(".", "")
            value = request.form.get(form_key)
            if value is not None:
                updates[field] = value.strip()

        # Auto-set status when moving to/from a bill
        if "Bill Title" in updates:
            # If status wasn't explicitly changed by the user, auto-set it
            current_status = request.form.get("status", "").strip()
            if updates["Bill Title"] and current_status in ("", "New"):
                updates["Status"] = "bill requested"
            elif not updates["Bill Title"] and current_status == "bill requested":
                updates["Status"] = "New"

        success = xlsx_manager.update_item(item_id, updates)
        if success:
            flash("Item updated", "success")
            # Re-queue screenshot if link changed
            if "Link" in updates and updates["Link"]:
                name = updates.get("Item Name", "")
                bill = updates.get("Bill Title", "")
                if not name:
                    # Get current name and bill
                    items = xlsx_manager.read_items()
                    for i in items:
                        if str(i.get("Bill Item ID", "")) == str(item_id):
                            name = str(i.get("Item Name", ""))
                            if not bill:
                                bill = str(i.get("Bill Title", ""))
                            break
                if name:
                    screenshot_worker.queue_screenshot(name, updates["Link"], bill)
        else:
            flash("Failed to update item", "error")

        return redirect(url_for("dashboard"))

    # GET - load item data
    items = xlsx_manager.read_items()
    item = None
    for i in items:
        if str(i.get("Bill Item ID", "")) == str(item_id):
            item = i
            break

    if not item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard"))

    return render_template("edit_item.html", item=item, bills=xlsx_manager.get_bills())


# --- Delete Item ---


@app.route("/edit-queue/<int:table_index>", methods=["GET", "POST"])
@login_required
def edit_queue_item(table_index):
    """Edit a queue item by its TestTable row index."""
    import requests as _requests

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    if request.method == "POST":
        # Get columns
        columns = xlsx_manager.graph_get_table_columns("TestTable")
        if not columns:
            flash("Failed to get columns", "error")
            return redirect(url_for("dashboard"))

        # Build updated row values
        row_values = []
        for col in columns:
            form_key = col.lower().replace(" ", "_").replace(".", "")
            value = request.form.get(form_key, "")
            row_values.append(value)

        # Update via Graph API - PATCH the row
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows/itemAt(index={table_index})"
        resp = _requests.patch(url, headers=headers, json={"values": [row_values]}, timeout=10)

        if resp.status_code == 200:
            flash("Item updated", "success")
            xlsx_manager._cached_queue_time = 0  # Reset cache
            flash("Item updated", "success")
        else:
            flash(f"Update failed: {resp.status_code}", "error")

        return redirect(url_for("dashboard"))

    # GET - load item data
    queue_items = xlsx_manager.read_queue_items()
    item = None
    for i in queue_items:
        if i.get("_table_index") == table_index:
            item = i
            break

    if not item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard"))

    return render_template("edit_queue_item.html", item=item, table_index=table_index)


@app.route("/delete-queue/<int:table_index>", methods=["POST"])
@login_required
def delete_queue_item_route(table_index):
    """Delete a queue item by its TestTable row index."""
    import requests as _requests

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}"}

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows/itemAt(index={table_index})"
    resp = _requests.delete(url, headers=headers, timeout=10)

    if resp.status_code == 204:
        flash("Item deleted from queue", "success")
        xlsx_manager._cached_queue = []
        xlsx_manager._cached_queue_time = 0
    else:
        flash(f"Delete failed: {resp.status_code}", "error")

    return redirect(url_for("dashboard"))


@app.route("/delete/<item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    success = xlsx_manager.delete_item(item_id)
    if success:
        flash("Item deleted", "success")
    else:
        flash("Failed to delete item", "error")
    return redirect(request.referrer or url_for("dashboard"))


# --- Remove from Bill ---


@app.route("/delete-bill/<path:bill_title>", methods=["POST"])
@login_required
def delete_bill(bill_title):
    """Delete all items in a bill (and its separator row) from BillsT."""
    import requests as _requests

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}"}

    # Get all rows
    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/BillsT/rows"
    resp = _requests.get(rows_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        flash("Failed to read bills", "error")
        return redirect(url_for("dashboard"))

    rows = resp.json().get("value", [])

    # Find rows matching this bill title
    to_clear = []
    for r in rows:
        vals = r["values"][0]
        row_bill = str(vals[2]) if vals[2] else ""
        if row_bill == bill_title:
            to_clear.append(r["index"])

    if not to_clear:
        flash(f"No rows found for '{bill_title}'", "error")
        return redirect(url_for("dashboard"))

    # Also find the "Request N" separator row immediately before this bill's items
    first_item_idx = min(to_clear)
    for r in rows:
        vals = r["values"][0]
        row_bill = str(vals[2]) if vals[2] else ""
        item_name = str(vals[3]) if vals[3] else ""
        # Separator: has "Request N" in Bill Title, no Item Name, and is right before our items
        if r["index"] == first_item_idx - 1 and row_bill.startswith("Request") and not item_name:
            to_clear.append(r["index"])
            break

    # Clear these rows (blank the non-formula cells) instead of deleting
    # This preserves table structure and formulas
    headers_ct = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    cleared = 0
    for idx in to_clear:
        sheet_row = idx + 2  # table starts at row 2
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Bills')/range(address='B{sheet_row}:J{sheet_row}')"
        resp = _requests.patch(url, headers=headers_ct, json={"values": [[""] * 9]}, timeout=10)
        url2 = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Bills')/range(address='L{sheet_row}:P{sheet_row}')"
        resp2 = _requests.patch(url2, headers=headers_ct, json={"values": [[""] * 5]}, timeout=10)
        if resp.status_code == 200 and resp2.status_code == 200:
            cleared += 1

    # Reset caches
    xlsx_manager._cached_items = []
    xlsx_manager._cached_items_time = 0
    xlsx_manager._last_pull_time = 0

    flash(f"Deleted bill '{bill_title}' ({cleared} rows cleared)", "success")
    return redirect(url_for("dashboard"))


@app.route("/remove-from-bill/<item_id>", methods=["POST"])
@login_required
def remove_from_bill(item_id):
    """Move item back to backlog (clear Bill Title, set status to New)."""
    success = xlsx_manager.update_item(item_id, {"Bill Title": "", "Status": "New"})
    if success:
        flash("Item moved to backlog", "success")
    else:
        flash("Failed to remove item from bill", "error")
    return redirect(request.referrer or url_for("dashboard"))


# --- Create Bill ---


@app.route("/create-bill", methods=["GET", "POST"])
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
            return redirect(url_for("create_bill"))

        if not selected_indices:
            flash("Select at least one item", "error")
            return redirect(url_for("create_bill"))

        # Get queue items and filter to selected ones
        queue_items = xlsx_manager.read_queue_items()
        selected_items = [
            item for item in queue_items
            if str(item.get("_table_index", "")) in selected_indices
        ]

        if not selected_items:
            flash("No matching items found", "error")
            return redirect(url_for("create_bill"))

        # Move from Test sheet to Bills sheet
        moved = xlsx_manager.move_to_bill(selected_items, bill_title, add_separator=is_new_bill, person=session.get("user_name", ""))

        # Copy screenshots from _queue/ to bill folder (local + SharePoint)
        for item in selected_items:
            name = str(item.get("Item Name", ""))
            if name:
                _copy_screenshot_to_bill(name, "_queue", bill_title)

        # Reset caches so dashboard shows fresh data
        xlsx_manager._cached_items = []
        xlsx_manager._cached_items_time = 0
        xlsx_manager._cached_queue = []
        xlsx_manager._cached_queue_time = 0
        xlsx_manager._last_pull_time = 0

        flash(f"Created bill '{bill_title}' with {moved} item(s)", "success")
        return redirect(url_for("dashboard"))

    # GET — show queue items to select from
    backlog = xlsx_manager.get_backlog_items()
    bills = xlsx_manager.get_bills()
    return render_template("create_bill.html", backlog=backlog, bills=bills)


# --- Bill View ---


@app.route("/bill/<path:bill_title>")
@login_required
def bill_view(bill_title):
    items = xlsx_manager.get_items_by_bill(bill_title)

    # Calculate total
    total = 0
    for item in items:
        try:
            cost = float(str(item.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
            qty = float(item.get("Quantity", 1) or 1)
            total += cost * qty
        except (ValueError, TypeError):
            pass
        # Add screenshot info
        name = str(item.get("Item Name", ""))
        item["_has_screenshot"] = screenshot_worker.has_screenshot(name, bill_title)
        full_path = screenshot_worker.get_screenshot_path(name, bill_title)
        if full_path:
            item["_screenshot_path"] = os.path.relpath(full_path, screenshot_worker.SCREENSHOT_DIR)
        else:
            item["_screenshot_path"] = ""

    return render_template("bill_view.html", bill_title=bill_title, items=items, total=total)


# --- Export CSV ---


@app.route("/bill/<path:bill_title>/export")
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


# --- Create Order ---


@app.route("/create-order", methods=["GET"])
@login_required
def create_order():
    """Show approved items grouped by vendor for order creation."""
    items = xlsx_manager.read_items()

    # Filter to items that are approved/ready to purchase
    orderable_statuses = {"bill approved", "pending purchase"}
    orderable = [i for i in items if str(i.get("Status", "")).strip().lower() in orderable_statuses]

    # Group by vendor
    vendors = {}
    for item in orderable:
        vendor = str(item.get("Vendor", "")).strip() or "Unknown"
        if vendor not in vendors:
            vendors[vendor] = []
        vendors[vendor].append(item)

    return render_template("create_order.html", vendors=vendors)


@app.route("/create-order/submit", methods=["POST"])
@login_required
def submit_order():
    """Write selected items to the OrderT table."""
    import requests as _requests
    from datetime import datetime

    selected_ids = request.form.getlist("item_ids")
    vendor = request.form.get("vendor", "").strip()
    purchaser = session.get("user_name", "")

    if not selected_ids:
        flash("Select at least one item", "error")
        return redirect(url_for("create_order"))

    # Generate Order ID: YYMMDD_vendor_name
    date_str = datetime.now().strftime("%y%m%d")
    safe_vendor = vendor.lower().replace(" ", "").replace("-", "")[:10]
    safe_name = purchaser.lower().replace(" ", "")[:10] if purchaser else "unknown"
    order_id = f"{date_str}_{safe_vendor}_{safe_name}"

    # Get the items data
    items = xlsx_manager.read_items()
    selected_items = [i for i in items if str(i.get("Bill Item ID", "")) in selected_ids]

    if not selected_items:
        flash("No matching items found", "error")
        return redirect(url_for("create_order"))

    # Write to OrderT
    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("create_order"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # Get OrderT columns
    order_columns = xlsx_manager.graph_get_table_columns("OrderT")
    if not order_columns:
        flash("Could not read OrderT columns", "error")
        return redirect(url_for("create_order"))

    # Find first empty row in OrderT
    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/OrderT/rows"
    resp = _requests.get(rows_url, headers=headers, timeout=15)
    first_empty = 0
    if resp.status_code == 200:
        for row in resp.json().get("value", []):
            vals = row["values"][0]
            if any(str(v).strip() for v in vals if v):
                first_empty = row["index"] + 1

    # Write each item - only fill Order ID and Bill Item ID (formulas handle the rest)
    wrote = 0
    order_id_col = order_columns.index("Order ID (YYMMDD_vendor_gburdell3)") if "Order ID (YYMMDD_vendor_gburdell3)" in order_columns else 0
    bill_item_id_col = order_columns.index("Bill Item ID") if "Bill Item ID" in order_columns else 1
    purchaser_col = order_columns.index("Purchaser") if "Purchaser" in order_columns else None
    status_col = order_columns.index("Status") if "Status" in order_columns else None

    for item in selected_items:
        sheet_row = first_empty + 3  # OrderT header is row 2, data starts row 3
        item_id = str(item.get("Bill Item ID", ""))

        # Write Order ID
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{chr(65 + order_id_col)}{sheet_row}')"
        _requests.patch(url, headers=headers, json={"values": [[order_id]]}, timeout=10)

        # Write Bill Item ID
        url2 = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{chr(65 + bill_item_id_col)}{sheet_row}')"
        _requests.patch(url2, headers=headers, json={"values": [[int(float(item_id)) if item_id else ""]]}, timeout=10)

        # Write Purchaser
        if purchaser_col is not None:
            url3 = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{chr(65 + purchaser_col)}{sheet_row}')"
            _requests.patch(url3, headers=headers, json={"values": [[purchaser]]}, timeout=10)

        # Write Status
        if status_col is not None:
            url4 = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{chr(65 + status_col)}{sheet_row}')"
            _requests.patch(url4, headers=headers, json={"values": [["pending purchase"]]}, timeout=10)

        wrote += 1
        first_empty += 1

    # Update status on BillsT items to "pending purchase"
    for item in selected_items:
        item_id = str(item.get("Bill Item ID", ""))
        if item_id:
            xlsx_manager.update_item(item_id, {"Status": "pending purchase"})

    # Generate Amazon cart link if applicable
    amazon_link = _generate_amazon_cart(selected_items)

    xlsx_manager._cached_items = []
    xlsx_manager._cached_items_time = 0

    flash(f"Order '{order_id}' created with {wrote} item(s)", "success")

    if amazon_link:
        flash(f'<a href="{amazon_link}" target="_blank">Open Amazon Cart</a>', "success")

    return redirect(url_for("create_order"))


def _generate_amazon_cart(items: list[dict]) -> str:
    """Generate an Amazon add-to-cart URL from items with Amazon links."""
    import re

    amazon_items = []
    for item in items:
        link = str(item.get("Link", ""))
        if "amazon" not in link.lower():
            continue
        # Extract ASIN from URL
        asin_match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', link)
        if asin_match:
            asin = asin_match.group(1)
            qty = int(float(str(item.get("Quantity", 1)) or 1))
            amazon_items.append((asin, qty))

    if not amazon_items:
        return ""

    # Build cart URL
    params = []
    for i, (asin, qty) in enumerate(amazon_items, 1):
        params.append(f"ASIN.{i}={asin}&Quantity.{i}={qty}")

    return "https://www.amazon.com/gp/aws/cart/add.html?" + "&".join(params)


@app.route("/create-order/check-prices", methods=["POST"])
@login_required
def check_prices():
    """Re-scrape current prices for selected items and return comparison."""
    import json as _json
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    selected_ids = request.form.getlist("item_ids")
    if not selected_ids:
        return _json.dumps({"error": "No items selected"}), 400

    items = xlsx_manager.read_items()
    selected = [i for i in items if str(i.get("Bill Item ID", "")) in selected_ids]

    if not selected:
        return _json.dumps({"error": "No matching items"}), 400

    # Set up headless browser once for all items
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"

    results = []
    driver = None
    try:
        service = Service("/snap/chromium/current/usr/lib/chromium-browser/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)

        for item in selected:
            link = str(item.get("Link", ""))
            allocated = 0
            try:
                allocated = float(str(item.get("Cost", 0)).replace("$", "").replace(",", "") or 0)
            except (ValueError, TypeError):
                pass

            current_price = None
            if link and link.startswith("http"):
                try:
                    driver.get(link)
                except Exception:
                    pass
                import time
                time.sleep(3)
                price_text = screenshot_worker._scrape_price(driver)
                current_price = screenshot_worker.parse_price(price_text)

            delta = None
            if current_price is not None and allocated > 0:
                delta = round(current_price - allocated, 2)

            results.append({
                "name": item.get("Item Name", ""),
                "bill_item_id": str(item.get("Bill Item ID", "")),
                "allocated": allocated,
                "current": current_price,
                "delta": delta,
                "warning": delta is not None and delta > 0,
            })

    except Exception as e:
        return _json.dumps({"error": str(e)}), 500
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return _json.dumps({"results": results})


# --- Bill Review ---


@app.route("/review/<path:bill_title>")
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


@app.route("/review/<path:bill_title>/save", methods=["POST"])
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
    return redirect(url_for("review_bill", bill_title=bill_title))


# --- Screenshot Helpers ---


def _copy_screenshot_to_bill(item_name: str, from_bill: str, to_bill: str):
    """Copy a screenshot from one bill folder to another (local + SharePoint)."""
    import shutil

    src_path = screenshot_worker.get_screenshot_path(item_name, from_bill)
    if not src_path:
        return

    # Copy locally
    safe_bill = screenshot_worker._safe_dirname(to_bill)
    safe_name = screenshot_worker._safe_filename(item_name)
    dest_dir = os.path.join(screenshot_worker.SCREENSHOT_DIR, safe_bill)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{safe_name}.png")
    shutil.copy2(src_path, dest_path)

    # Upload to SharePoint
    screenshot_worker._upload_screenshot_to_sharepoint(to_bill, dest_path)


# --- Copy Item to Bill ---


@app.route("/copy-to-bill/<item_id>", methods=["GET", "POST"])
@login_required
def copy_to_bill(item_id):
    """Duplicate an item from one bill to another, copying the screenshot too."""
    if request.method == "POST":
        target_bill = request.form.get("bill_title", "").strip()
        if not target_bill:
            flash("Select a target bill", "error")
            return redirect(request.referrer or url_for("dashboard"))

        # Find the source item
        items = xlsx_manager.read_items()
        source_item = None
        for item in items:
            if str(item.get("Bill Item ID", "")) == str(item_id):
                source_item = item
                break

        if not source_item:
            flash("Item not found", "error")
            return redirect(url_for("dashboard"))

        # Add to target bill via Graph API
        bills_columns = xlsx_manager.graph_get_table_columns("BillsT")
        if not bills_columns:
            flash("Failed to get table columns", "error")
            return redirect(url_for("dashboard"))

        item_data = dict(source_item)
        item_data["Bill Title"] = target_bill
        item_data["Status"] = "bill requested"
        item_data["Bill Item ID"] = ""  # Will be auto-assigned

        # Calculate Total Cost
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
            # Copy screenshot to new bill folder
            name = str(source_item.get("Item Name", ""))
            source_bill = str(source_item.get("Bill Title", ""))
            if name:
                _copy_screenshot_to_bill(name, source_bill, target_bill)
            flash(f"Copied '{name}' to '{target_bill}'", "success")
        else:
            flash("Failed to copy item", "error")

        return redirect(url_for("bill_view", bill_title=target_bill))

    # GET — show bill selection
    items = xlsx_manager.read_items()
    source_item = None
    for item in items:
        if str(item.get("Bill Item ID", "")) == str(item_id):
            source_item = item
            break

    if not source_item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard"))

    bills = xlsx_manager.get_bills()
    return render_template("copy_to_bill.html", item=source_item, bills=bills)


# --- Screenshot endpoints ---


@app.route("/screenshots/<path:filename>")
@login_required
def serve_screenshot(filename):
    """Serve screenshot files. Path can be bill_title/item_name.png"""
    return send_from_directory(screenshot_worker.SCREENSHOT_DIR, filename)


@app.route("/screenshot/queue/<item_id>", methods=["POST"])
@login_required
def queue_screenshot(item_id):
    """Manually trigger a screenshot for an item."""
    items = xlsx_manager.read_items()
    for item in items:
        if str(item.get("Bill Item ID", "")) == str(item_id):
            name = str(item.get("Item Name", ""))
            url = str(item.get("Link", ""))
            bill = str(item.get("Bill Title", ""))
            if name and url:
                screenshot_worker.queue_screenshot(name, url, bill)
                flash(f"Screenshot queued for {name}", "success")
            else:
                flash("Item has no URL", "error")
            break
    return redirect(request.referrer or url_for("dashboard"))


# --- Link Scraper (auto-fill) ---


@app.route("/scrape-link", methods=["POST"])
@login_required
def scrape_link():
    """Scrape a URL for title and price to auto-fill the add item form."""
    import json
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    url = request.form.get("url", "").strip()
    if not url:
        return json.dumps({"error": "No URL"}), 400

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"

    try:
        service = Service("/snap/chromium/current/usr/lib/chromium-browser/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(20)

        try:
            driver.get(url)
        except Exception:
            pass  # Page may partially load — still try to scrape

        import time
        time.sleep(3)

        title = driver.title or ""
        price_text = screenshot_worker._scrape_price(driver)
        price = screenshot_worker.parse_price(price_text)

        # Try to detect vendor from domain
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        vendor = ""
        if "amazon" in domain:
            vendor = "Amazon"
        elif "mcmaster" in domain:
            vendor = "McMaster-Carr"
        elif "digikey" in domain:
            vendor = "DigiKey"
        elif "mouser" in domain:
            vendor = "Mouser"
        elif "adafruit" in domain:
            vendor = "Adafruit"
        elif "sparkfun" in domain:
            vendor = "SparkFun"
        elif "pololu" in domain:
            vendor = "Pololu"

        driver.quit()

        return json.dumps({
            "title": title,
            "price": price,
            "vendor": vendor,
        })

    except Exception as e:
        return json.dumps({"error": str(e)}), 500


# --- Start app ---


@app.route("/force-pull", methods=["POST"])
@login_required
def force_pull():
    """Force a fresh pull from SharePoint, bypassing all caches."""
    import xlsx_manager as xm
    xm._last_pull_time = 0
    xm._cached_items = []
    xm._cached_items_time = 0
    xm._cached_queue = []
    xm._cached_queue_time = 0
    # Delete local file so rclone is forced to re-download
    if os.path.exists(xm.LOCAL_XLSX):
        os.remove(xm.LOCAL_XLSX)
    result = xm.sync_pull()
    if result:
        flash("Synced from SharePoint", "success")
    else:
        flash("Sync failed — check rclone config", "error")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    screenshot_worker.start_worker()
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
