"""
dashboard.py - Main dashboard, system status, and force pull routes.
"""

import os
import json
import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
import xlsx_manager
import screenshot_worker
from routes.auth import login_required
from routes.bills import is_bill_locked

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
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

    locked_bills = {title: is_bill_locked(title) for title in bills}

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

    return render_template("dashboard.html", bills=bills, backlog=backlog, locked_bills=locked_bills)


@dashboard_bp.route("/force-pull", methods=["POST"])
@dashboard_bp.route("/sync-onedrive", methods=["POST"])
@login_required
def force_pull():
    """Force a fresh pull from SharePoint, bypassing all caches."""
    xlsx_manager.invalidate_all_caches()

    # Perform synchronous sync (without deleting existing file to prevent broken dashboard rendering)
    result = xlsx_manager.sync_pull(force=True)
    if result:
        if os.path.exists(xlsx_manager.LOCAL_XLSX):
            try:
                os.utime(xlsx_manager.LOCAL_XLSX, None)
            except OSError:
                pass
        flash("Synced from SharePoint", "success")
    else:
        flash("Sync failed — check rclone config", "error")

    # Redirect back to referring page (orders, bills, dashboard, etc.)
    next_page = request.referrer or url_for("dashboard.dashboard")
    return redirect(next_page)


@dashboard_bp.route("/status")
@login_required
def system_status():
    """Check token and sync status."""
    status = {"token": "unknown", "sync": "unknown"}

    # Check token
    creds = xlsx_manager._get_graph_token()
    if creds:
        access_token, drive_id, file_id = creds
        try:
            resp = requests.get(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                status["token"] = "ok"
            elif resp.status_code == 401:
                status["token"] = "expired"
            else:
                status["token"] = f"error ({resp.status_code})"
        except Exception:
            status["token"] = "request error"
    else:
        status["token"] = "missing"

    # Check sync
    if os.path.exists(xlsx_manager.LOCAL_XLSX):
        import time
        age = time.time() - os.path.getmtime(xlsx_manager.LOCAL_XLSX)
        if age < 60:
            status["sync_age"] = "Synced just now"
        elif age < 3600:
            status["sync_age"] = f"Synced {int(age/60)}m ago"
        else:
            status["sync_age"] = f"Synced {int(age/3600)}h ago"
        status["sync"] = status["sync_age"]
    else:
        status["sync"] = "no local file"
        status["sync_age"] = "No sync"

    return jsonify(status)
