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
    """Show all orders from OrderT grouped by Order ID with fallback metadata lookups."""
    order_rows = xlsx_manager.graph_get_order_rows()
    order_columns = xlsx_manager.graph_get_table_columns("OrderT")

    # Read items from Bills sheet for metadata cross-referencing
    all_bill_items = xlsx_manager.read_items()
    items_by_id = {str(i.get("Bill Item ID", "")).strip(): i for i in all_bill_items if i.get("Bill Item ID")}

    order_id_col = "Order ID"
    for col in order_columns:
        if "Order ID" in col:
            order_id_col = col
            break

    orders = {}
    for row in order_rows:
        b_id = str(row.get("Bill Item ID", "")).strip()
        bill_item = items_by_id.get(b_id) if b_id else None

        if bill_item:
            if not row.get("Item Name") or str(row.get("Item Name")).startswith("#"):
                row["Item Name"] = bill_item.get("Item Name", "")
            if not row.get("Vendor") or str(row.get("Vendor")).startswith("#"):
                row["Vendor"] = bill_item.get("Vendor", "")
            if not row.get("Description"):
                row["Description"] = bill_item.get("Description", "")

            # Calculate allocation fallback if formula cell is empty/uncalculated
            alloc_val = row.get("Allocation")
            if not alloc_val or str(alloc_val).startswith("#") or str(alloc_val) in ("0", "0.0"):
                try:
                    unit_cost = float(str(bill_item.get("Cost", 0) or 0).replace("$", "").replace(",", "") or 0)
                    qty = float(row.get("Quantity", 1) or 1)
                    row["Allocation"] = unit_cost * qty
                except (ValueError, TypeError):
                    pass

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
    """Delete all items in an order and clean up its order title header row."""
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

    rows_val = resp.json().get("value", [])
    order_columns = xlsx_manager.graph_get_table_columns("OrderT")
    order_id_col_name = next((c for c in order_columns if "Order ID" in c), "Order ID")
    oid_idx = order_columns.index(order_id_col_name) if order_id_col_name in order_columns else 0
    item_name_idx = order_columns.index("Item Name") if "Item Name" in order_columns else 3
    bill_item_col_idx = order_columns.index("Bill Item ID") if "Bill Item ID" in order_columns else 1

    to_clear_indices = []
    bill_items_to_reset = []

    for row in rows_val:
        vals = row["values"][0]
        row_oid = str(vals[oid_idx]).strip() if len(vals) > oid_idx and vals[oid_idx] else ""
        if row_oid == order_id:
            to_clear_indices.append(row["index"])
            b_id = str(vals[bill_item_col_idx]).strip() if len(vals) > bill_item_col_idx and vals[bill_item_col_idx] else ""
            if b_id:
                bill_items_to_reset.append(b_id)

    # Check for order title header row ("Order N") immediately above the first item row
    if to_clear_indices:
        first_item_idx = min(to_clear_indices)
        if first_item_idx > 0:
            prev_row = next((r for r in rows_val if r.get("index") == first_item_idx - 1), None)
            if prev_row:
                p_vals = prev_row["values"][0]
                p_oid = str(p_vals[oid_idx]).strip() if len(p_vals) > oid_idx and p_vals[oid_idx] else ""
                p_bid = str(p_vals[bill_item_col_idx]).strip() if len(p_vals) > bill_item_col_idx and p_vals[bill_item_col_idx] else ""
                p_name = str(p_vals[item_name_idx]).strip() if len(p_vals) > item_name_idx and p_vals[item_name_idx] else ""

                if p_name.startswith("Order") and not p_oid and not p_bid:
                    to_clear_indices.append(first_item_idx - 1)

    col_letters = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R']
    cleared = 0

    for idx in sorted(to_clear_indices):
        sheet_row = idx + 3
        try:
            # Clear input cells A, B, D, E, F, G, J without touching formula cells (C, H, I)
            for col_i in [0, 1, 3, 4, 5, 6, 9]:
                if col_i < len(col_letters):
                    col_let = col_letters[col_i]
                    cell_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{col_let}{sheet_row}')"
                    requests.patch(cell_url, headers=headers, json={"values": [[""]]}, timeout=10)
            cleared += 1
        except Exception as e:
            print(f"[order] ⚠️ Error clearing row {sheet_row}: {e}")

    for b_id in bill_items_to_reset:
        xlsx_manager.update_item(b_id, {"Status": "bill approved"})

    xlsx_manager.invalidate_orders_cache()
    flash(f"Deleted order '{order_id}' and title header ({cleared} rows cleared)", "success")
    return redirect(url_for("orders.view_orders"))


@orders_bp.route("/orders/delete-item", methods=["POST"])
@login_required
def delete_order_item():
    """Remove a single item from an order and clean up title header if order is empty."""
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
    col_letters = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R']

    try:
        # Clear input cells A, B, D, E, F, G, J for this item row
        for col_i in [0, 1, 3, 4, 5, 6, 9]:
            if col_i < len(col_letters):
                col_let = col_letters[col_i]
                cell_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{col_let}{sheet_row}')"
                requests.patch(cell_url, headers=headers, json={"values": [[""]]}, timeout=10)

        if bill_item_id:
            xlsx_manager.update_item(bill_item_id, {"Status": "bill approved"})

        # Check if any remaining items exist for this order_id
        order_rows = xlsx_manager._fetch_order_rows()
        remaining_items = [r for r in order_rows if str(r.get("Order ID (YYMMDD_vendor_gburdell3)", "") or r.get("Order ID", "")).strip() == order_id]

        if not remaining_items and order_id:
            # Order is now empty! Clean up the Order N title header row above if present
            target_idx = int(row_index)
            if target_idx > 0:
                rows_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/OrderT/rows"
                resp = requests.get(rows_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    rows_val = resp.json().get("value", [])
                    prev_row = next((r for r in rows_val if r.get("index") == target_idx - 1), None)
                    if prev_row:
                        p_vals = prev_row["values"][0]
                        p_name = str(p_vals[3]).strip() if len(p_vals) > 3 and p_vals[3] else ""
                        p_oid = str(p_vals[0]).strip() if len(p_vals) > 0 and p_vals[0] else ""
                        if p_name.startswith("Order") and not p_oid:
                            header_sheet_row = target_idx - 1 + 3
                            cell_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='D{header_sheet_row}')"
                            requests.patch(cell_url, headers=headers, json={"values": [[""]]}, timeout=10)

        xlsx_manager.invalidate_orders_cache()
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
    last_data_idx = -1
    existing_order_ids = set()
    existing_bill_item_map = {}  # bill_item_id -> (row_index, current_qty)
    max_order_num = 0

    bill_item_col_idx = order_columns.index("Bill Item ID") if "Bill Item ID" in order_columns else 1
    qty_col_idx = order_columns.index("Quantity") if "Quantity" in order_columns else 5

    try:
        resp = requests.get(rows_url, headers=headers, timeout=20)
        if resp.status_code == 200:
            rows_val = resp.json().get("value", [])
            for row in rows_val:
                vals = row["values"][0]
                if (vals[0] and str(vals[0]).strip()) or (vals[1] and str(vals[1]).strip()):
                    last_data_idx = row["index"]
                if vals[0] and str(vals[0]).strip():
                    existing_order_ids.add(str(vals[0]).strip())
                if len(vals) > bill_item_col_idx and vals[bill_item_col_idx]:
                    b_id = str(vals[bill_item_col_idx]).strip()
                    if b_id:
                        try:
                            q_val = float(vals[qty_col_idx]) if len(vals) > qty_col_idx and vals[qty_col_idx] else 1.0
                        except (ValueError, TypeError):
                            q_val = 1.0
                        existing_bill_item_map[b_id] = (row["index"], q_val)

                item_name = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ""
                if item_name.startswith("Order") and not vals[1]:
                    try:
                        num = int(item_name.replace("Order", "").strip())
                        if num > max_order_num:
                            max_order_num = num
                    except ValueError:
                        pass
    except requests.exceptions.RequestException as e:
        print(f"[order] ⚠️ Graph API request failed: {e}")
        flash("Microsoft Graph API request timed out — please try submitting again", "error")
        return redirect(url_for("orders.create_order"))

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
            sep_row = first_empty + 3
            item_name_col = order_columns.index("Item Name") if "Item Name" in order_columns else 3
            sep_col_letter = col_letters[item_name_col] if item_name_col < len(col_letters) else "D"
            sep_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{sep_col_letter}{sep_row}')"
            requests.patch(sep_url, headers=headers, json={"values": [[f"Order {max_order_num}"]]}, timeout=30)
            first_empty += 1

        for item in vendor_items:
            item_id = str(item.get("Bill Item ID", "")).strip()
            try:
                max_bill_qty = float(str(item.get("Quantity", 1) or 1).replace("$", "").replace(",", "") or 1)
            except (ValueError, TypeError):
                max_bill_qty = 999999.0

            # Read custom order quantity from form if provided
            custom_qty_raw = request.form.get(f"quantity_{item_id}", "").strip()
            if custom_qty_raw:
                try:
                    add_qty = float(custom_qty_raw)
                    if add_qty <= 0:
                        flash("Quantity must be greater than 0", "error")
                        return redirect(url_for("orders.create_order"))
                    if add_qty > max_bill_qty:
                        item_name = item.get("Item Name", "Item")
                        flash(f"Order quantity ({add_qty}) for '{item_name}' cannot exceed approved bill quantity ({max_bill_qty})", "error")
                        return redirect(url_for("orders.create_order"))
                except ValueError:
                    flash(f"Invalid quantity '{custom_qty_raw}'", "error")
                    return redirect(url_for("orders.create_order"))
            else:
                add_qty = min(max_bill_qty, 1.0) if max_bill_qty >= 1 else max_bill_qty

            # Deduplication: If item is ALREADY in an existing order on OrderT, update its quantity instead of creating a duplicate row!
            if item_id in existing_bill_item_map:
                row_idx, current_qty = existing_bill_item_map[item_id]
                new_qty = current_qty + add_qty
                sheet_row = row_idx + 3
                col_letter = col_letters[qty_col_idx] if qty_col_idx < len(col_letters) else "F"
                update_qty_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{col_letter}{sheet_row}')"
                try:
                    patch_resp = requests.patch(update_qty_url, headers=headers, json={"values": [[new_qty]]}, timeout=15)
                    if patch_resp.status_code == 200:
                        total_wrote += 1
                        existing_bill_item_map[item_id] = (row_idx, new_qty)
                        print(f"[order] ✅ Updated quantity for item {item_id}: {current_qty} -> {new_qty}")
                except Exception as e:
                    print(f"[order] ⚠️ Failed to update quantity for item {item_id}: {e}")
                continue

            sheet_row = first_empty + 3

            cells_to_patch = [
                ("Order ID (YYMMDD_vendor_gburdell3)", order_id),
                ("Order ID", order_id),
                ("Bill Item ID", int(float(item_id)) if item_id else ""),
                ("Purchaser", purchaser),
                ("Status", "pending purchase"),
                ("Quantity", add_qty),
            ]
            if not item_id:
                cells_to_patch.append(("Item Name", item.get("Item Name", "")))
                cells_to_patch.append(("Vendor", item.get("Vendor", "")))

            item_written = False
            for c_name, val in cells_to_patch:
                if c_name in order_columns:
                    c_idx = order_columns.index(c_name)
                    if c_idx < len(col_letters):
                        col_letter = col_letters[c_idx]
                        cell_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets('Ordering')/range(address='{col_letter}{sheet_row}')"
                        try:
                            r = requests.patch(cell_url, headers=headers, json={"values": [[val]]}, timeout=10)
                            if r.status_code == 200:
                                item_written = True
                        except Exception as e:
                            print(f"[order] ⚠️ Error writing cell {col_letter}{sheet_row}: {e}")

            if item_written:
                total_wrote += 1
                if item_id:
                    existing_bill_item_map[item_id] = (first_empty, add_qty)

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


@orders_bp.route("/orders/edit-item/<int:table_index>", methods=["GET", "POST"])
@login_required
def edit_order_item(table_index):
    """Edit a single order item in OrderT."""
    order_rows = xlsx_manager.graph_get_order_rows()
    item = None
    for r in order_rows:
        if r.get("_table_index") == table_index:
            item = r
            break

    if not item:
        flash("Order item not found", "error")
        return redirect(url_for("orders.view_orders"))

    bill_item_id = str(item.get("Bill Item ID", "")).strip()
    max_bill_qty = None
    if bill_item_id:
        all_bill_items = xlsx_manager.read_items()
        matching_b = next((bi for bi in all_bill_items if str(bi.get("Bill Item ID", "")).strip() == bill_item_id), None)
        if matching_b:
            try:
                max_bill_qty = float(str(matching_b.get("Quantity", 999999) or 999999).replace("$", "").replace(",", "") or 999999)
            except (ValueError, TypeError):
                max_bill_qty = None

    if request.method == "POST":
        updates = {}
        for field in ["Item Name", "Vendor", "Purchaser", "Status", "Quantity", "Notes"]:
            form_key = field.lower().replace(" ", "_").replace(".", "")
            val = request.form.get(form_key)
            if val is not None:
                updates[field] = val.strip()

        if "Quantity" in updates and updates["Quantity"]:
            try:
                q_val = float(updates["Quantity"])
                if q_val <= 0:
                    flash("Quantity must be greater than 0", "error")
                    return redirect(url_for("orders.edit_order_item", table_index=table_index))
                if max_bill_qty is not None and q_val > max_bill_qty:
                    flash(f"Quantity ({q_val}) cannot exceed approved bill quantity ({max_bill_qty})", "error")
                    return redirect(url_for("orders.edit_order_item", table_index=table_index))
                updates["Quantity"] = q_val
            except ValueError:
                flash(f"Invalid quantity '{updates['Quantity']}'", "error")
                return redirect(url_for("orders.edit_order_item", table_index=table_index))

        success = xlsx_manager.graph_update_order_item(table_index, updates)

        if bill_item_id and success:
            bill_updates = {}
            if "Item Name" in updates:
                bill_updates["Item Name"] = updates["Item Name"]
            if "Vendor" in updates:
                bill_updates["Vendor"] = updates["Vendor"]
            if "Quantity" in updates:
                bill_updates["Quantity"] = updates["Quantity"]
            if "Status" in updates:
                bill_updates["Status"] = updates["Status"]
            if bill_updates:
                xlsx_manager.update_item(bill_item_id, bill_updates)

        if success:
            flash("Order item updated", "success")
        else:
            flash("Failed to update order item", "error")
        return redirect(url_for("orders.view_orders"))

    return render_template("edit_order_item.html", item=item, table_index=table_index, max_bill_qty=max_bill_qty)


@orders_bp.route("/orders/edit/<order_id>", methods=["GET", "POST"])
@login_required
def edit_order(order_id):
    """Edit order details across all items in an order."""
    order_rows = xlsx_manager.graph_get_order_rows()
    order_items = [r for r in order_rows if str(r.get("Order ID (YYMMDD_vendor_gburdell3)", "") or r.get("Order ID", "")).strip() == order_id]

    if not order_items:
        flash("Order not found", "error")
        return redirect(url_for("orders.view_orders"))

    all_bill_items = xlsx_manager.read_items()
    items_by_id = {str(i.get("Bill Item ID", "")).strip(): i for i in all_bill_items if i.get("Bill Item ID")}

    current_vendor = price_scraper.normalize_vendor(order_items[0].get("Vendor", "")) if order_items else ""
    current_purchaser = order_items[0].get("Purchaser", "") if order_items else ""
    current_status = order_items[0].get("Status", "") if order_items else ""

    if request.method == "POST":
        global_vendor = request.form.get("global_vendor", "").strip()
        global_purchaser = request.form.get("global_purchaser", "").strip()
        global_status = request.form.get("global_status", "").strip()

        updated_count = 0
        for idx, item in enumerate(order_items):
            t_idx = item.get("_table_index")
            if t_idx is None:
                continue

            b_id = str(item.get("Bill Item ID", "")).strip()
            matching_b = items_by_id.get(b_id) if b_id else None
            max_b_qty = None
            if matching_b:
                try:
                    max_b_qty = float(str(matching_b.get("Quantity", 999999) or 999999).replace("$", "").replace(",", "") or 999999)
                except (ValueError, TypeError):
                    max_b_qty = None

            item_updates = {}
            item_name = request.form.get(f"item_name_{idx}", "").strip()
            item_vendor = request.form.get(f"vendor_{idx}", "").strip() or global_vendor
            item_purchaser = request.form.get(f"purchaser_{idx}", "").strip() or global_purchaser
            item_status = request.form.get(f"status_{idx}", "").strip() or global_status
            item_notes = request.form.get(f"notes_{idx}", "").strip()
            item_qty_raw = request.form.get(f"quantity_{idx}", "").strip()

            if item_name:
                item_updates["Item Name"] = item_name
            if item_vendor:
                item_updates["Vendor"] = item_vendor
            if item_purchaser:
                item_updates["Purchaser"] = item_purchaser
            if item_status:
                item_updates["Status"] = item_status
            if item_notes:
                item_updates["Notes"] = item_notes

            if item_qty_raw:
                try:
                    q_val = float(item_qty_raw)
                    if q_val <= 0:
                        flash(f"Quantity for item '{item_name}' must be greater than 0", "error")
                        return redirect(url_for("orders.edit_order", order_id=order_id))
                    if max_b_qty is not None and q_val > max_b_qty:
                        flash(f"Quantity for '{item_name}' ({q_val}) cannot exceed approved bill quantity ({max_b_qty})", "error")
                        return redirect(url_for("orders.edit_order", order_id=order_id))
                    item_updates["Quantity"] = q_val
                except ValueError:
                    flash(f"Invalid quantity '{item_qty_raw}' for item '{item_name}'", "error")
                    return redirect(url_for("orders.edit_order", order_id=order_id))

            if item_updates and xlsx_manager.graph_update_order_item(t_idx, item_updates):
                updated_count += 1
                if b_id:
                    b_up = {}
                    if "Item Name" in item_updates: b_up["Item Name"] = item_updates["Item Name"]
                    if "Vendor" in item_updates: b_up["Vendor"] = item_updates["Vendor"]
                    if "Quantity" in item_updates: b_up["Quantity"] = item_updates["Quantity"]
                    if "Status" in item_updates: b_up["Status"] = item_updates["Status"]
                    xlsx_manager.update_item(b_id, b_up)

        flash(f"Updated order '{order_id}' ({updated_count} line items updated)", "success")
        return redirect(url_for("orders.view_orders"))

    # Attach max_bill_qty to each order item for rendering
    for item in order_items:
        b_id = str(item.get("Bill Item ID", "")).strip()
        matching_b = items_by_id.get(b_id) if b_id else None
        if matching_b:
            try:
                item["_max_bill_qty"] = float(str(matching_b.get("Quantity", 999999) or 999999).replace("$", "").replace(",", "") or 999999)
            except (ValueError, TypeError):
                item["_max_bill_qty"] = None
        else:
            item["_max_bill_qty"] = None

    return render_template("edit_order.html", order_id=order_id, items=order_items, vendor=current_vendor, purchaser=current_purchaser, status=current_status)
