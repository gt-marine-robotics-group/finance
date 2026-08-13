"""
screenshots.py - Screenshot serving and queuing routes.
"""

from flask import Blueprint, send_from_directory, redirect, url_for, flash, request
import xlsx_manager
import screenshot_worker
from routes.auth import login_required

screenshots_bp = Blueprint("screenshots", __name__)


@screenshots_bp.route("/screenshots/<path:filename>")
@login_required
def serve_screenshot(filename):
    """Serve screenshot files. Path can be bill_title/item_name.png"""
    return send_from_directory(screenshot_worker.SCREENSHOT_DIR, filename)


@screenshots_bp.route("/screenshot/queue/<item_id>", methods=["POST"])
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
    return redirect(request.referrer or url_for("dashboard.dashboard"))
