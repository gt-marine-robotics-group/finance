"""
app.py - MRG Purchasing web app entrypoint.

Mobile-friendly Flask app for managing purchase items and organizing them into bills.
Refactored into logical blueprints: auth, dashboard, items, bills, orders, screenshots.
"""

import os
import sys
from flask import Flask, render_template

# Add parent directory for price_scraper import
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.items import items_bp
from routes.bills import bills_bp
from routes.orders import orders_bp
from routes.screenshots import screenshots_bp

import screenshot_worker


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "mrg-purchasing-dev-key-change-me")

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(items_bp)
    app.register_blueprint(bills_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(screenshots_bp)

    # URL build error handler for legacy un-namespaced template url_for calls
    def handle_url_build_error(error, endpoint, values):
        from flask import url_for
        for ep in app.url_map._rules_by_endpoint.keys():
            if ep.endswith("." + endpoint):
                return url_for(ep, **values)
        raise error

    app.url_build_error_handlers.append(handle_url_build_error)

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("500.html", error_details=str(e)), 500

    return app


app = create_app()

if __name__ == "__main__":
    screenshot_worker.start_worker()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
