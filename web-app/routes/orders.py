"""
orders.py - Order management routes (view orders, mark purchased, apply formatting, delete order, create order, batch submit order, check prices).
"""

import sys
import os
import json
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import price_scraper
import xlsx_manager
import screenshot_worker
from routes.auth import login_required

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/orders")
@login_required
def view_orders():
    """Show all orders from OrderT grouped by Order ID."""
    order_rows = xlsx_manager.graph_get_order_rows()
    order_columns = xlsx_manager.graph_get_table_columns("OrderT")

    order_id_col = "Order ID"
    for col in order_columns:
        if "Order ID" in col:
            order_id_col = col
            break

    orders = {}
    for row in order_rows:
        oid = str(row.get(order_id_col, "")).strip()
        if not oid:
            oid = f"ungrouped_{row.get('Bill Item ID', 'unknown')}"
        if oid not in orders:
            orders[oid] = {
                "order_id": oid,
                "items": [],
                "vendor": "",
                "total_allocation": 0.0,
                "status": "",
                "purchaser": "",
            }
        orders[oid]["items"].append(row)

        vendor = price_scraper.normalize_vendor(str(row.get("Vendor", "")).strip())
        if vendor and not orders[oid]["vendor"]:
            orders[oid]["vendor"] = vendor

        try:
            alloc = float(str(row.get("Allocation", 0) or row.get("Total Cost", 0)).replace("$", "").replace(",", "") or 0)
            orders[oid]["total_allocation"] += alloc
        except (ValueError, TypeError):
            pass

        status = str(row.get("Status", "")).strip()
        if status and not orders[oid]["status"]:
            orders[oid]["status"] = status

        purchaser = str(row.get("Purchaser", "")).strip()
        if purchaser and not orders[oid]["purchaser"]:
            orders[oid]["purchaser"] = purchaser

    for oid, order in orders.items():
        if not order["vendor"] and "_" in oid:
            parts = oid.split("_")
            if len(parts) >= 2:
                order["vendor"] = price_scraper.normalize_vendor(parts[1])

    sorted_orders = dict(sorted(orders.items(), key=lambda x: x[0], reverse=True))

    return render_template("orders.html", orders=sorted_orders, order_id_col=order_id_col)


@orders_bp.route("/orders/mark-purchased", methods=["POST"])
@login_required
def mark_order_purchased():
    """Mark all items in an order as purchased."""
    order_id = request.form.get("order_id", "").strip()
    purchasing_method = request.form.get("purchasing_method", "purchased - SOFO").strip()

    if not order_id:
        flash("No order ID provided", "error")
        return redirect(url_for("orders.view_orders"))

    order_columns = xlsx_manager.graph_get_table_columns("OrderT")

    order_id_col = "Order ID"
    for col in order_columns:
        if "Order ID" in col:
            order_id_col = col
            break

    success = xlsx_manager.graph_update_order_status(order_id_col, order_id, purchasing_method, order_columns)

    if success:
        flash(f"Marked order '{order_id}' as {purchasing_method}", "success")
    else:
        flash(f"Failed to update order '{order_id}'", "error")

    return redirect(url_for("orders.view_orders"))


@orders_bp.route("/orders/apply-formatting", methods=["POST"])
@login_required
def apply_order_formatting():
    """Apply pink conditional formatting to spacer rows on the Ordering sheet."""
    success = xlsx_manager.graph_apply_spacer_formatting()
    if success:
        flash("Applied pink formatting to spacer rows", "success")
    else:
        flash("Failed to apply formatting — see docs for manual method", "error")
    return redirect(url_for("orders.view_orders"))


@orders_bp.route("/orders/delete", methods=["POST"])
@login_required
def delete_order():
    """Delete all items in an order (clear rows on OrderT)."""
    order_id = request.form.get("order_id", "").strip()
    if not order_id:
        flash("No order specified", "error")
        return redirect(url_for("orders.view_orders"))

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("orders.view_orders"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/OrderT/rows"
    resp = requests.get(rows_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        flash("Failed to read orders", "error")
        return redirect(url_for("orders.view_orders"))

    order_columns = xlsx_manager.graph_get_table_columns("OrderT")
    order_id_col_name = next((c for c in order_columns if "Order ID" in c), "Order ID")

    to_clear = []
    for row in resp.json().get("value", []):
        vals = row["values"][0]
        oid_idx = order_columns.index(order_id_col_name)
        row_oid = str(vals[oid_idx]).strip() if vals[oid_idx] else ""
        if row_oid == order_id:
            to_clear.append(row["index"])

    cleared = 0
    for idx in to_clear:
        sheet_row = idx + 3
        try:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='A{sheet_row}:R{sheet_row}')"
            requests.patch(url, headers=headers, json={"values": [[""] * 18]}, timeout=30)
            cleared += 1
        except Exception:
            pass

    for row in resp.json().get("value", []):
        vals = row["values"][0]
        oid_idx = order_columns.index(order_id_col_name)
        row_oid = str(vals[oid_idx]).strip() if vals[oid_idx] else ""
        if row_oid == order_id:
            bill_item_id = str(vals[order_columns.index("Bill Item ID")]).strip() if "Bill Item ID" in order_columns else ""
            if bill_item_id:
                xlsx_manager.update_item(bill_item_id, {"Status": "bill approved"})

    flash(f"Deleted order '{order_id}' ({cleared} rows)", "success")
    return redirect(url_for("orders.view_orders"))


@orders_bp.route("/orders/delete-item", methods=["POST"])
@login_required
def delete_order_item():
    """Remove a single item from an order."""
    order_id = request.form.get("order_id", "").strip()
    row_index = request.form.get("row_index", "").strip()
    bill_item_id = request.form.get("bill_item_id", "").strip()

    if not row_index:
        flash("No item specified", "error")
        return redirect(url_for("orders.view_orders"))

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("orders.view_orders"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    sheet_row = int(row_index) + 3
    try:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='A{sheet_row}:R{sheet_row}')"
        requests.patch(url, headers=headers, json={"values": [[""] * 18]}, timeout=30)

        if bill_item_id:
            xlsx_manager.update_item(bill_item_id, {"Status": "bill approved"})

        flash("Item removed from order", "success")
    except Exception as e:
        flash(f"Failed to remove item: {e}", "error")

    return redirect(url_for("orders.view_orders"))


@orders_bp.route("/create-order", methods=["GET"])
@login_required
def create_order():
    """Show approved items grouped by vendor or bill for order creation."""
    items = xlsx_manager.read_items()
    group_by = request.args.get("group", "vendor")
    filter_vendor = request.args.get("filter_vendor", "").strip()

    orderable_statuses = {"bill approved", "pending purchase"}
    orderable = [i for i in items if str(i.get("Status", "")).strip().lower() in orderable_statuses]

    if filter_vendor:
        orderable = [i for i in orderable if str(i.get("Vendor", "")).strip().lower() == filter_vendor.lower()]

    groups = {}
    for item in orderable:
        if group_by == "bill":
            key = str(item.get("Bill Title", "")).strip() or "Unknown"
        else:
            raw_vendor = str(item.get("Vendor", "")).strip() or "Unknown"
            key = price_scraper.normalize_vendor(raw_vendor)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    return render_template("create_order.html", vendors=groups, group_by=group_by)


@orders_bp.route("/create-order/submit", methods=["POST"])
@login_required
def submit_order():
    """Write selected items to the OrderT table, auto-grouping by vendor."""
    selected_ids = request.form.getlist("item_ids")
    purchaser = session.get("user_name", "")

    if not selected_ids:
        flash("Select at least one item", "error")
        return redirect(url_for("orders.create_order"))

    items = xlsx_manager.read_items()
    selected_items = [i for i in items if str(i.get("Bill Item ID", "")) in selected_ids]

    if not selected_items:
        flash("No matching items found", "error")
        return redirect(url_for("orders.create_order"))

    vendor_groups = {}
    for item in selected_items:
        vendor = price_scraper.normalize_vendor(str(item.get("Vendor", "")).strip()) or "Unknown"
        if vendor not in vendor_groups:
            vendor_groups[vendor] = []
        vendor_groups[vendor].append(item)

    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable — token may have expired", "error")
        return redirect(url_for("orders.create_order"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    order_columns = xlsx_manager.graph_get_table_columns("OrderT")
    if not order_columns:
        flash("Could not read OrderT columns", "error")
        return redirect(url_for("orders.create_order"))

    rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/OrderT/rows"
    resp = requests.get(rows_url, headers=headers, timeout=15)
    last_data_idx = -1
    existing_order_ids = set()
    max_order_num = 0

    if resp.status_code == 200:
        rows_val = resp.json().get("value", [])
        for row in rows_val:
            vals = row["values"][0]
            if (vals[0] and str(vals[0]).strip()) or (vals[1] and str(vals[1]).strip()):
                last_data_idx = row["index"]
            if vals[0] and str(vals[0]).strip():
                existing_order_ids.add(str(vals[0]).strip())
            item_name = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ""
            if item_name.startswith("Order") and not vals[1]:
                try:
                    num = int(item_name.replace("Order", "").strip())
                    if num > max_order_num:
                        max_order_num = num
                except ValueError:
                    pass

    first_empty = last_data_idx + 1
    date_str = datetime.now().strftime("%y%m%d")
    total_wrote = 0
    order_ids = []

    col_letters = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R']

    for vendor, vendor_items in vendor_groups.items():
        safe_vendor = vendor.lower().replace(" ", "").replace("-", "")[:10]
        gt_id = session.get("user_name", "unknown").lower().replace(" ", "")
        order_id = f"{date_str}_{safe_vendor}_{gt_id}"
        order_ids.append(order_id)

        if order_id not in existing_order_ids:
            max_order_num += 1
            first_empty += 1
            sep_row = first_empty + 3
            item_name_col = order_columns.index("Item Name") if "Item Name" in order_columns else 3
            sep_col_letter = col_letters[item_name_col] if item_name_col < len(col_letters) else "D"
            sep_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{sep_col_letter}{sep_row}')"
            requests.patch(sep_url, headers=headers, json={"values": [[f"Order {max_order_num}"]]}, timeout=30)
            first_empty += 1

        for item in vendor_items:
            sheet_row = first_empty + 3
            item_id = str(item.get("Bill Item ID", ""))
            qty = item.get("Quantity", 1)

            # Optimization: Build single row range PATCH instead of 5 separate API calls per item
            row_data = [""] * len(order_columns)
            for c_name, val in [
                ("Order ID (YYMMDD_vendor_gburdell3)", order_id),
                ("Order ID", order_id),
                ("Bill Item ID", int(float(item_id)) if item_id else ""),
                ("Purchaser", purchaser),
                ("Status", "pending purchase"),
                ("Quantity", qty),
            ]:
                if c_name in order_columns:
                    c_idx = order_columns.index(c_name)
                    row_data[c_idx] = val

            start_col = col_letters[0]
            end_col = col_letters[min(len(order_columns) - 1, len(col_letters) - 1)]
            batch_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{start_col}{sheet_row}:{end_col}{sheet_row}')"
            
            try:
                batch_resp = requests.patch(batch_url, headers=headers, json={"values": [row_data[:len(order_columns)]]}, timeout=30)
                if batch_resp.status_code == 200:
                    total_wrote += 1
                else:
                    print(f"[order] ⚠️ Batch row write status: {batch_resp.status_code}")
            except Exception as e:
                print(f"[order] ⚠️ Failed to write item {item_id}: {e}")

            first_empty += 1

    for item in selected_items:
        item_id = str(item.get("Bill Item ID", ""))
        if item_id:
            xlsx_manager.update_item(item_id, {"Status": "pending purchase"})

    amazon_link = price_scraper.generate_amazon_cart_url(selected_items)
    xlsx_manager.invalidate_items_cache()

    order_str = ", ".join(order_ids)
    flash(f"Created order(s): {order_str} ({total_wrote} items)", "success")

    if amazon_link:
        flash(f'<a href="{amazon_link}" target="_blank">Open Amazon Cart</a>', "success")

    return redirect(url_for("orders.create_order"))


@orders_bp.route("/create-order/check-prices", methods=["POST"])
@login_required
def check_prices():
    """Re-scrape current prices for selected items, streaming results."""
    selected_ids = request.form.getlist("item_ids")
    if not selected_ids:
        return json.dumps({"error": "No items selected"}), 400

    items = xlsx_manager.read_items()
    selected = [i for i in items if str(i.get("Bill Item ID", "")) in selected_ids]

    if not selected:
        return json.dumps({"error": "No matching items"}), 400

    def generate():
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        import time

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"

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
                    time.sleep(3)
                    price_text = price_scraper.scrape_price_from_driver(driver)
                    current_price = price_scraper.parse_price(price_text)

                delta = None
                if current_price is not None and allocated > 0:
                    delta = round(current_price - allocated, 2)

                result = {
                    "name": item.get("Item Name", ""),
                    "bill_item_id": str(item.get("Bill Item ID", "")),
                    "allocated": allocated,
                    "current": current_price,
                    "delta": delta,
                    "warning": delta is not None and delta > 0,
                }
                yield f"data: {json.dumps(result)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            yield "data: {\"done\": true}\n\n"

    return Response(generate(), mimetype="text/event-stream")
