"""
items.py - Item management routes (quick add, add, edit, delete, queue management, link scraping).
"""

import sys
import os
import json
import threading
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import price_scraper
import xlsx_manager
import screenshot_worker
from routes.auth import login_required

items_bp = Blueprint("items", __name__)


@items_bp.route("/quick-add", methods=["POST"])
@login_required
def quick_add():
    """Quick add — just name and optional link. Goes to backlog."""
    item_name = request.form.get("item_name", "").strip()
    link = request.form.get("link", "").strip()
    if link and not link.startswith("http"):
        link = "https://" + link

    if not item_name:
        flash("Item name required", "error")
        return redirect(url_for("dashboard.dashboard"))

    vendor = price_scraper.detect_vendor_from_url(link) if link else ""

    item_data = {
        "Item Name": item_name,
        "Link": link,
        "Cost": "",
        "Quantity": "1",
        "Vendor": vendor,
        "Description": "",
        "Budget Section": "",
        "Bill Title": "",
        "Person Requesting": session.get("user_name", ""),
    }

    def _do_background(name, url):
        if url:
            import time
            time.sleep(2)
            screenshot_worker.queue_screenshot(name, url, "_queue")

    success = xlsx_manager.add_item(item_data)
    if success:
        flash(f"Added: {item_name}", "success")
        if link:
            threading.Thread(target=_do_background, args=(item_name, link), daemon=True).start()
    else:
        flash("Failed to add", "error")

    return redirect(url_for("dashboard.dashboard"))


@items_bp.route("/add", methods=["GET", "POST"])
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

        if not item_data["Vendor"] and item_data["Link"]:
            item_data["Vendor"] = price_scraper.detect_vendor_from_url(item_data["Link"])

        if not item_data["Item Name"]:
            flash("Item Name is required", "error")
            return render_template("add_item.html", bills=xlsx_manager.get_bills())

        success = xlsx_manager.add_item(item_data)
        if success:
            flash(f"Added to queue: {item_data['Item Name']}", "success")
            if item_data["Link"]:
                screenshot_worker.queue_screenshot(
                    item_data["Item Name"], item_data["Link"], "_queue"
                )
        else:
            flash("Failed to save item", "error")

        return redirect(url_for("dashboard.dashboard"))

    return render_template("add_item.html", bills=xlsx_manager.get_bills())


LOCKED_STATUSES = {
    "bill submitted",
    "bill approved",
    "pending purchase",
    "purchased - sofo",
    "purchased - cash",
    "purchased - awaiting reimbursement",
    "arrived",
    "approved",
    "submitted",
}


@items_bp.route("/edit/<item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = xlsx_manager.get_item(item_id)
    if item and str(item.get("Status", "")).strip().lower() in LOCKED_STATUSES:
        flash("Cannot edit an item from an approved or submitted bill.", "error")
        return redirect(request.referrer or url_for("dashboard.dashboard"))
    if request.method == "POST":
        updates = {}
        for field in [
            "Item Name", "Cost", "Quantity", "Link", "Vendor",
            "Description", "Budget Section", "Bill Title",
            "Person Requesting", "Status"
        ]:
            form_key = field.lower().replace(" ", "_").replace(".", "")
            value = request.form.get(form_key)
            if value is not None:
                updates[field] = value.strip()

        if "Bill Title" in updates:
            current_status = request.form.get("status", "").strip()
            if updates["Bill Title"] and current_status in ("", "New"):
                updates["Status"] = "bill requested"
            elif not updates["Bill Title"] and current_status == "bill requested":
                updates["Status"] = "New"

        success = xlsx_manager.update_item(item_id, updates)
        if success:
            flash("Item updated", "success")
            if "Link" in updates and updates["Link"]:
                name = updates.get("Item Name", "")
                bill = updates.get("Bill Title", "")
                if not name:
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

        return redirect(url_for("dashboard.dashboard"))

    items = xlsx_manager.read_items()
    item = None
    for i in items:
        if str(i.get("Bill Item ID", "")) == str(item_id):
            item = i
            break

    if not item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard.dashboard"))

    return render_template("edit_item.html", item=item, bills=xlsx_manager.get_bills())


@items_bp.route("/edit-queue/<int:table_index>", methods=["GET", "POST"])
@login_required
def edit_queue_item(table_index):
    """Edit a queue item by its TestTable row index."""
    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard.dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    if request.method == "POST":
        columns = xlsx_manager.graph_get_table_columns("TestTable")
        if not columns:
            flash("Failed to get columns", "error")
            return redirect(url_for("dashboard.dashboard"))

        row_values = []
        for col in columns:
            form_key = col.lower().replace(" ", "_").replace(".", "")
            value = request.form.get(form_key, "")
            row_values.append(value)

        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows/itemAt(index={table_index})"
        resp = requests.patch(url, headers=headers, json={"values": [row_values]}, timeout=10)

        if resp.status_code == 200:
            flash("Item updated", "success")
            xlsx_manager.invalidate_queue_cache()
        else:
            flash(f"Update failed: {resp.status_code}", "error")

        return redirect(url_for("dashboard.dashboard"))

    queue_items = xlsx_manager.read_queue_items()
    item = None
    for i in queue_items:
        if i.get("_table_index") == table_index:
            item = i
            break

    if not item:
        flash("Item not found", "error")
        return redirect(url_for("dashboard.dashboard"))

    return render_template("edit_queue_item.html", item=item, table_index=table_index)


@items_bp.route("/delete-queue/<int:table_index>", methods=["POST"])
@login_required
def delete_queue_item_route(table_index):
    """Delete a queue item by its TestTable row index."""
    creds = xlsx_manager._get_graph_token()
    if not creds:
        flash("Graph API unavailable", "error")
        return redirect(url_for("dashboard.dashboard"))

    access_token, drive_id, file_id = creds
    headers = {"Authorization": f"Bearer {access_token}"}

    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/tables/TestTable/rows/itemAt(index={table_index})"
    resp = requests.delete(url, headers=headers, timeout=10)

    if resp.status_code == 204:
        flash("Item deleted from queue", "success")
        xlsx_manager.invalidate_queue_cache()
    else:
        flash(f"Delete failed: {resp.status_code}", "error")

    return redirect(url_for("dashboard.dashboard"))


@items_bp.route("/delete/<item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    item = xlsx_manager.get_item(item_id)
    if item and str(item.get("Status", "")).strip().lower() in LOCKED_STATUSES:
        flash("Cannot delete an item from an approved or submitted bill.", "error")
        return redirect(request.referrer or url_for("dashboard.dashboard"))
    success = xlsx_manager.delete_item(item_id)
    if success:
        flash("Item deleted", "success")
    else:
        flash("Failed to delete item", "error")
    return redirect(request.referrer or url_for("dashboard.dashboard"))


@items_bp.route("/scrape-link", methods=["POST"])
@login_required
def scrape_link():
    """Scrape a URL for title and price to auto-fill the add item form."""
    url = request.form.get("url", "").strip()
    if not url:
        return json.dumps({"error": "No URL"}), 400

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

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
            pass

        import time
        time.sleep(3)

        title = driver.title or ""
        price_text = price_scraper.scrape_price_from_driver(driver)
        price = price_scraper.parse_price(price_text)
        vendor = price_scraper.detect_vendor_from_url(url)

        driver.quit()

        return json.dumps({
            "title": title,
            "price": price,
            "vendor": vendor,
        })

    except Exception as e:
        return json.dumps({"error": str(e)}), 500
